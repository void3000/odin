"""
Odin FastAPI Server.

Exposes the query pipeline as a REST endpoint.
The orchestrator runs query processing in a thread to avoid blocking the event loop.
"""

import asyncio
import argparse
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.llm_client import LLMClient
from src.llm.nl_to_ir import NaturalLanguageToIR
from src.schema.extractor import SQLiteSchemaExtractor
from src.orchestrator import QueryOrchestrator
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


class QueryRequest(BaseModel):
    question: str


def create_app(
    db_url: str,
    llm_base_url: str = "http://localhost:1234/v1",
    llm_api_key: str = "lmstudio",
    llm_model: str = "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
    temperature: float = 0.1,
    default_limit: int = 100,
) -> FastAPI:
    """Create and configure the FastAPI app with an orchestrator."""
    global orchestrator

    schema_extractor = SQLiteSchemaExtractor(db_url)
    schema = schema_extractor.extract_schema()

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
    )

    return app


@app.post("/v1/query")
async def query(request: QueryRequest) -> Dict[str, Any]:
    result = await asyncio.to_thread(orchestrator.process_query, request.question)
    return result


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
