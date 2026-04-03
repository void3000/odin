"""
Odin FastAPI Server.

Exposes the query pipeline as a REST endpoint.
The orchestrator runs query processing in a thread to avoid blocking the event loop.
"""

import asyncio
import argparse
import json
import time
import uuid
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.db import create_schema_extractor
from src.llm_client import LLMClient
from src.llm.nl_to_ir import NaturalLanguageToIR
from src.orchestrator import QueryOrchestrator
from src.session import SessionManager
from src.graph import create_graph
from src.logging_config import get_component_logger, get_uvicorn_log_config, request_id_var

logger = get_component_logger("server")


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
session_manager: Optional[SessionManager] = None
graph = None


class QueryRequest(BaseModel):
    input: str
    session_id: Optional[str] = None


class SessionMiddleware(BaseHTTPMiddleware):
    """Handles session lifecycle as before/after hooks on /v1/query.

    Before: reads session_id from request body, resolves conversation
    history, and injects it into request.state.
    After: appends the turn to session history and injects session_id
    into the response body.
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

        # Before: resolve session and inject history into request state
        request.state.conversation_history = None
        request.state.session_id = session_id

        if session_id:
            session = session_manager.get(session_id)
            if session is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": "Session not found or expired"},
                )
            request.state.conversation_history = session_manager.get_history(session_id)

        response = await call_next(request)

        # After: no session — pass through unchanged
        if not session_id:
            return response

        # Read response body to modify it
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

        # Append turn on success
        input_text = body.get("input", "")
        if result.get("success"):
            summary = result.get("summary") or result.get("message", "")
            session_manager.add_turn(session_id, question=input_text, summary=summary)

        # Inject session_id
        result["session_id"] = session_id

        return JSONResponse(content=result, status_code=response.status_code)


app = FastAPI(title="Odin", description="LLM-to-SQL Pipeline")
app.add_middleware(SessionMiddleware)
app.add_middleware(RequestIdMiddleware)


def create_app(
    db_url: str,
    llm_base_url: str = "http://localhost:1234/v1",
    llm_api_key: str = "lmstudio",
    llm_model: str = "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
    temperature: float = 0.1,
    default_limit: int = 100,
) -> FastAPI:
    """Create and configure the FastAPI app with an orchestrator."""
    global orchestrator, session_manager, graph

    schema_extractor = create_schema_extractor(db_url)
    schema = schema_extractor.extract_schema()
    search_path = getattr(schema_extractor, "schemas", None)

    llm_client = LLMClient(
        base_url=llm_base_url,
        api_key=llm_api_key,
        model=llm_model,
        temperature=temperature,
    )

    nl_converter = NaturalLanguageToIR(api_key=llm_api_key)
    system_prompt = nl_converter._build_system_prompt(schema)

    validator_schema = {
        table.name: {
            "columns": {col.name: {"type": col.type} for col in table.columns}
        }
        for table in schema.tables
    }

    orchestrator = QueryOrchestrator(
        db_url=db_url,
        llm_client=llm_client,
        system_prompt=system_prompt,
        schema=validator_schema,
        default_limit=default_limit,
        search_path=search_path,
    )

    session_manager = SessionManager()

    graph = create_graph(
        orchestrator=orchestrator,
        llm_client=llm_client,
        system_prompt=system_prompt,
    )

    return app


@app.post("/v1/sessions", status_code=201)
async def create_session():
    session = session_manager.create()
    return {"session_id": session.session_id}


@app.delete("/v1/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    if not session_manager.delete(session_id):
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found or expired"},
        )


@app.post("/v1/query")
async def query(request: Request, body: QueryRequest):
    conversation_history = getattr(request.state, "conversation_history", None)

    graph_result = await asyncio.to_thread(
        graph.invoke,
        {"input": body.input, "conversation_history": conversation_history},
    )

    result = graph_result["result"]
    status_code = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status_code)


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Odin API Server")
    parser.add_argument("--db", required=True, help="Database connection string")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--llm-url", default="http://localhost:1234/v1", help="LLM API base URL")
    parser.add_argument("--llm-key", default="lmstudio", help="LLM API key")
    parser.add_argument("--llm-model", default="qwen3.5-27b-claude-4.6-opus-reasoning-distilled", help="LLM model name")
    parser.add_argument("--temperature", type=float, default=0.1, help="LLM temperature")
    parser.add_argument("--default-limit", type=int, default=100, help="Default row limit")
    args = parser.parse_args()

    create_app(
        db_url=args.db,
        llm_base_url=args.llm_url,
        llm_api_key=args.llm_key,
        llm_model=args.llm_model,
        temperature=args.temperature,
        default_limit=args.default_limit,
    )

    uvicorn.run(app, host=args.host, port=args.port, log_config=get_uvicorn_log_config())
