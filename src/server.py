"""
Odin FastAPI Server.

Exposes the query pipeline as a REST endpoint.
The orchestrator runs query processing in a thread to avoid blocking the event loop.
"""

import asyncio
import json
import logging
import time
import uuid
import uvicorn
from typing import Optional, Set

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings_from_cli
from src.llm_client import LLMClient
from src.llm.nl_to_ir import NaturalLanguageToIR
from src.orchestrator import QueryOrchestrator
from src.sources.config import create_source_from_db_url, load_sources_from_config
from src.sources.registry import SourceRegistry
from src.sources.base import SourceSchema
from src.schema.schema import DatabaseSchema, TableDef, ColumnDef
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from src.graph import create_graph
from src.logging_config import get_component_logger, get_uvicorn_log_config, request_id_var, setup_logging
from src.web.routes import router as web_router

logger = get_component_logger("server")


def _source_schema_to_database_schema(source_schema: SourceSchema) -> DatabaseSchema:
    """Convert a SourceSchema to a DatabaseSchema for LLM prompt compatibility."""
    tables = []
    for collection in source_schema.collections:
        columns = [
            ColumnDef(name=f.name, type=f.type)
            for f in collection.fields
        ]
        tables.append(TableDef(name=collection.name, columns=columns))
    return DatabaseSchema(tables=tables)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns a unique request ID and logs request lifecycle."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)

        logger.info(f"{request.method} {request.url.path}")
        start = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed_ms:.0f}ms)")

        response.headers["X-Request-ID"] = request_id
        return response


orchestrator: Optional[QueryOrchestrator] = None
sessions: Set[str] = set()
graph = None


class QueryRequest(BaseModel):
    input: str
    session_id: Optional[str] = None


class SessionMiddleware(BaseHTTPMiddleware):
    """Handles session validation and response enrichment on /v1/query.

    Before: validates session_id exists in sessions set.
    After: injects session_id into the response body and sets status code.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path != "/v1/query" or request.method != "POST":
            return await call_next(request)

        # Read and cache the request body (needed for re-reading in endpoint)
        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, ValueError):
            return await call_next(request)

        session_id = body.get("session_id")

        # Validate session exists
        if session_id and session_id not in sessions:
            return JSONResponse(
                status_code=404,
                content={"error": "Session not found or expired"},
            )

        request.state.session_id = session_id

        response = await call_next(request)

        # Read response body
        response_body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                response_body += chunk.encode()
            else:
                response_body += chunk

        try:
            result = json.loads(response_body)
        except (json.JSONDecodeError, ValueError):
            return Response(content=response_body, status_code=response.status_code,
                            headers=dict(response.headers), media_type=response.media_type)

        # Inject session_id into response if provided
        if session_id:
            result["session_id"] = session_id

        # Set status code based on result (only for graph responses, not validation errors)
        if "type" in result:
            status_code = 200 if result.get("success") else 500
        else:
            status_code = response.status_code
        return JSONResponse(content=result, status_code=status_code)


app = FastAPI(title="Odin", description="LLM-to-SQL Pipeline")
app.add_middleware(SessionMiddleware)
app.add_middleware(RequestIdMiddleware)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "web" / "static")), name="static")
app.include_router(web_router)


def create_app(
    db_url: str | None = None,
    llm_base_url: str = "http://localhost:1234/v1",
    llm_api_key: str = "lmstudio",
    llm_model: str = "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
    temperature: float = 0.1,
    default_limit: int = 100,
    config_path: str | None = None,
) -> FastAPI:
    """Create and configure the FastAPI app with an orchestrator.

    Accepts individual parameters for backwards compatibility.
    Prefer create_app_from_settings() for new code.
    """
    global orchestrator, sessions, graph

    # Build source registry from config file and/or --db URL
    registry = SourceRegistry()
    if config_path:
        registry = load_sources_from_config(config_path)
    if db_url:
        source = create_source_from_db_url(db_url)
        if not config_path:
            registry.register("default", source)
        else:
            # Add as fallback if not already registered
            try:
                registry.get("default")
            except KeyError:
                registry.register("default", source)

    source = registry.get_default()

    # Extract schema from the source
    source.connect()
    try:
        source_schema = source.get_schema()
    finally:
        source.disconnect()

    # Convert SourceSchema to DatabaseSchema for LLM prompt compatibility
    db_schema = _source_schema_to_database_schema(source_schema)

    llm_client = LLMClient(
        base_url=llm_base_url,
        api_key=llm_api_key,
        model=llm_model,
        temperature=temperature,
    )

    nl_converter = NaturalLanguageToIR(api_key=llm_api_key)
    system_prompt = nl_converter._build_system_prompt(db_schema)

    validator_schema = {
        collection.name: {
            "columns": {f.name: {"type": f.type} for f in collection.fields}
        }
        for collection in source_schema.collections
    }

    orchestrator = QueryOrchestrator(
        source=source,
        llm_client=llm_client,
        system_prompt=system_prompt,
        schema=validator_schema,
        default_limit=default_limit,
    )

    sessions = set()

    checkpointer = InMemorySaver()
    graph = create_graph(
        orchestrator=orchestrator,
        llm_client=llm_client,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )

    return app


def create_app_from_settings(settings) -> FastAPI:
    """Create and configure the FastAPI app from a ServerSettings instance."""
    return create_app(
        db_url=settings.db,
        llm_base_url=settings.llm_url,
        llm_api_key=settings.llm_key,
        llm_model=settings.llm_model,
        temperature=settings.temperature,
        default_limit=settings.default_limit,
        config_path=settings.config,
    )


@app.post("/v1/sessions", status_code=201)
async def create_session():
    session_id = str(uuid.uuid4())
    sessions.add(session_id)
    return {"session_id": session_id}


@app.delete("/v1/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    if session_id not in sessions:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found or expired"},
        )
    sessions.discard(session_id)


@app.post("/v1/query")
async def query(request: Request, body: QueryRequest):
    session_id = getattr(request.state, "session_id", None)
    config = None
    if session_id:
        config = {"configurable": {"thread_id": session_id}}

    graph_result = await asyncio.to_thread(
        graph.invoke,
        {"messages": [HumanMessage(content=body.input)]},
        config,
    )

    return graph_result["result"]


if __name__ == "__main__":
    # Ensure 'import src.server' returns this module, not a second copy
    import sys
    sys.modules.setdefault("src.server", sys.modules[__name__])

    settings = settings_from_cli()
    setup_logging(
        log_level=logging.getLevelName(settings.log_level.upper()),
        log_file=settings.log_file,
    )
    create_app_from_settings(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_config=get_uvicorn_log_config(log_file=settings.log_file),
    )
