"""
Odin FastAPI Server.

Exposes the query pipeline as a REST endpoint.
The orchestrator runs query processing in a thread to avoid blocking the event loop.
"""

import asyncio
import argparse
import time
import uuid
from typing import Optional

from fastapi import Depends, FastAPI, Request, Response
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


app = FastAPI(title="Odin", description="LLM-to-SQL Pipeline")
app.add_middleware(RequestIdMiddleware)


orchestrator: Optional[QueryOrchestrator] = None
session_manager: Optional[SessionManager] = None
graph = None


class QueryRequest(BaseModel):
    input: str
    session_id: Optional[str] = None


class SessionContext:
    """Resolved session state for a request."""

    def __init__(self, session_id: Optional[str] = None, conversation_history: Optional[list] = None):
        self.session_id = session_id
        self.conversation_history = conversation_history


async def get_session_context(request: Request) -> SessionContext:
    """FastAPI dependency that resolves session state from the request body."""
    from fastapi import HTTPException

    body = await request.json()
    session_id = body.get("session_id")

    if not session_id:
        return SessionContext()

    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    history = session_manager.get_history(session_id)
    return SessionContext(session_id=session_id, conversation_history=history)


async def process_query(request: Request, session: SessionContext = Depends(get_session_context)) -> dict:
    """FastAPI dependency that handles the full query lifecycle.

    Uses SessionContext for session state. The endpoint receives
    only the final result dict.
    """
    from fastapi import HTTPException

    body = await request.json()
    input_text = body.get("input")
    if input_text is None:
        raise HTTPException(status_code=422, detail="Field 'input' is required")

    # Invoke graph
    graph_result = await asyncio.to_thread(
        graph.invoke,
        {"input": input_text, "conversation_history": session.conversation_history},
    )
    result = graph_result["result"]

    # Post-process session
    if session.session_id:
        if result.get("success"):
            summary = result.get("summary") or result.get("message", "")
            session_manager.add_turn(session.session_id, question=input_text, summary=summary)
        result["session_id"] = session.session_id

    return result


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
async def query(result: dict = Depends(process_query)):
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
