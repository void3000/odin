# Auto-Limit Workflow + FastAPI Server Design

Two features: a LimitWorkflow that applies a default row limit, and a FastAPI server that exposes the pipeline as a REST endpoint.

## Feature 1: LimitWorkflow

A new workflow step inserted between Validate and Build. If `query_ir.limit` is `None`, sets it to a configurable default. If the user's query already specified a limit, leaves it alone.

### LimitWorkflow (`src/workflows/limit.py`)

```python
class LimitWorkflow(Workflow):
    name = "limit"

    def __init__(self, default_limit: int = 100):
        self.default_limit = default_limit

    def run(self, context: PipelineContext) -> PipelineContext:
        if context.query_ir and context.query_ir.limit is None:
            context.query_ir.limit = self.default_limit
        return context
```

### Orchestrator Change

The steps list becomes:

```python
self.steps: List[Workflow] = [
    ParseWorkflow(parser),
    ValidateWorkflow(),
    LimitWorkflow(default_limit=100),
    BuildWorkflow(),
    ExecuteWorkflow(db_path),
    SummarizeWorkflow(summarizer),
]
```

The `default_limit` parameter is passed through `QueryOrchestrator.__init__()`.

## Feature 2: FastAPI Server

### Endpoint

```
POST /query
Content-Type: application/json

Request:  {"question": "Show me all artists"}
Response: {"success": true, "summary": "...", "error": null, "metadata": {...}}
```

### Architecture

- FastAPI app in `src/server.py`
- Orchestrator initialized once at startup using the same setup as `main.py` (env vars / CLI args for db_path, LLM config)
- Query processing runs in a thread via `asyncio.to_thread(orchestrator.process_query, question)` so the event loop is not blocked by LLM calls or DB queries
- Pydantic request model for validation

### Server Implementation (`src/server.py`)

```python
import asyncio
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Odin")
orchestrator: QueryOrchestrator = None  # set by create_app()


class QueryRequest(BaseModel):
    question: str


def create_app(db_path: str, llm_base_url: str = "http://localhost:1234/v1",
               llm_api_key: str = "lmstudio", llm_model: str = "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
               temperature: float = 0.1, default_limit: int = 100) -> FastAPI:
    """Create and configure the FastAPI app with an orchestrator."""
    global orchestrator

    # Same setup as main.py
    schema_extractor = SQLiteSchemaExtractor(db_path)
    schema = schema_extractor.extract_schema()
    llm_client = LLMClient(base_url=llm_base_url, api_key=llm_api_key,
                           model=llm_model, temperature=temperature)
    nl_converter = NaturalLanguageToIR(api_key=llm_api_key)
    system_prompt = nl_converter._build_system_prompt(schema)
    validator_schema = {
        table.name: {"columns": {col.name: {"type": col.type} for col in table.columns}}
        for table in schema.tables
    }

    orchestrator = QueryOrchestrator(
        db_path=db_path, llm_client=llm_client,
        system_prompt=system_prompt, schema=validator_schema,
        default_limit=default_limit,
    )
    return app


@app.post("/query")
async def query(request: QueryRequest):
    result = await asyncio.to_thread(orchestrator.process_query, request.question)
    return result
```

### CLI Entry Point

```bash
python -m src.server --db /path/to/db.sqlite
# Starts uvicorn on 0.0.0.0:8000
```

The server module has an `if __name__ == "__main__"` block using argparse + `uvicorn.run()`.

### Dependencies

Add `fastapi` and `uvicorn[standard]` to `pyproject.toml` dependencies.

## File Layout

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/workflows/limit.py` | LimitWorkflow |
| Create | `src/server.py` | FastAPI app + create_app factory |
| Create | `tests/test_workflow_limit.py` | LimitWorkflow tests |
| Create | `tests/test_server.py` | Server endpoint tests (using FastAPI TestClient) |
| Modify | `src/orchestrator.py` | Add default_limit param, insert LimitWorkflow |
| Modify | `src/workflows/__init__.py` | Export LimitWorkflow |
| Modify | `pyproject.toml` | Add fastapi, uvicorn deps |

## Testing Strategy

- `test_workflow_limit.py`: test limit applied when None, test limit not overridden when set
- `test_server.py`: use FastAPI `TestClient` with mocked orchestrator to test POST /query success and error responses
