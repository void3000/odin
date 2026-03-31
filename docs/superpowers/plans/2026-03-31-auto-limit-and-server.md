# Auto-Limit + FastAPI Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a LimitWorkflow that auto-applies a default row limit to queries, and expose the pipeline as a FastAPI REST endpoint with the orchestrator running in a thread.

**Architecture:** LimitWorkflow inserts between Validate and Build, setting `query_ir.limit` to a default (100) when not already set. A FastAPI app wraps the orchestrator with a `POST /query` endpoint, using `asyncio.to_thread` for non-blocking execution. A `create_app()` factory handles setup.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, Pydantic, pytest, httpx (TestClient)

**Spec:** `docs/superpowers/specs/2026-03-31-auto-limit-and-server-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/workflows/limit.py` | LimitWorkflow — apply default row limit |
| Create | `tests/test_workflow_limit.py` | LimitWorkflow tests |
| Modify | `src/workflows/__init__.py` | Export LimitWorkflow |
| Modify | `src/orchestrator.py` | Add default_limit param, insert LimitWorkflow |
| Create | `src/server.py` | FastAPI app, create_app factory, POST /query |
| Create | `tests/test_server.py` | Server endpoint tests |
| Modify | `pyproject.toml` | Add fastapi, uvicorn deps |

---

### Task 1: LimitWorkflow

**Files:**
- Create: `src/workflows/limit.py`
- Test: `tests/test_workflow_limit.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workflow_limit.py
from src.ir.models import QueryIR, TableSource, FieldExpr
from src.workflows.base import PipelineContext
from src.workflows.limit import LimitWorkflow


def _make_context(limit=None) -> PipelineContext:
    ctx = PipelineContext(
        natural_language="Show me all users",
        db_path="/tmp/test.db",
        schema={},
    )
    ctx.query_ir = QueryIR(
        operation="SELECT",
        source=TableSource(table="users"),
        fields=[FieldExpr(field="id")],
        limit=limit,
    )
    return ctx


class TestLimitWorkflow:
    def test_applies_default_limit_when_none(self):
        workflow = LimitWorkflow(default_limit=100)
        ctx = workflow.run(_make_context(limit=None))
        assert ctx.query_ir.limit == 100

    def test_does_not_override_existing_limit(self):
        workflow = LimitWorkflow(default_limit=100)
        ctx = workflow.run(_make_context(limit=10))
        assert ctx.query_ir.limit == 10

    def test_custom_default_limit(self):
        workflow = LimitWorkflow(default_limit=50)
        ctx = workflow.run(_make_context(limit=None))
        assert ctx.query_ir.limit == 50

    def test_no_error_set(self):
        workflow = LimitWorkflow(default_limit=100)
        ctx = workflow.run(_make_context(limit=None))
        assert ctx.error is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_limit.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.workflows.limit'`

- [ ] **Step 3: Implement LimitWorkflow**

```python
# src/workflows/limit.py
"""LimitWorkflow — applies a default row limit to queries."""

from src.workflows.base import Workflow, PipelineContext


class LimitWorkflow(Workflow):
    name = "limit"

    def __init__(self, default_limit: int = 100):
        self.default_limit = default_limit

    def run(self, context: PipelineContext) -> PipelineContext:
        if context.query_ir and context.query_ir.limit is None:
            context.query_ir.limit = self.default_limit
        return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_limit.py -v`
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/workflows/limit.py tests/test_workflow_limit.py
git commit -m "feat: add LimitWorkflow to auto-apply default row limit"
```

---

### Task 2: Integrate LimitWorkflow into Orchestrator

**Files:**
- Modify: `src/workflows/__init__.py`
- Modify: `src/orchestrator.py`

- [ ] **Step 1: Update `src/workflows/__init__.py` to export LimitWorkflow**

```python
# src/workflows/__init__.py
from src.workflows.base import Workflow, PipelineContext
from src.workflows.parse import ParseWorkflow
from src.workflows.validate import ValidateWorkflow
from src.workflows.limit import LimitWorkflow
from src.workflows.build import BuildWorkflow
from src.workflows.execute import ExecuteWorkflow
from src.workflows.summarize import SummarizeWorkflow

__all__ = [
    "Workflow",
    "PipelineContext",
    "ParseWorkflow",
    "ValidateWorkflow",
    "LimitWorkflow",
    "BuildWorkflow",
    "ExecuteWorkflow",
    "SummarizeWorkflow",
]
```

- [ ] **Step 2: Update orchestrator to accept `default_limit` and insert LimitWorkflow**

In `src/orchestrator.py`, update the `__init__` signature and steps list:

```python
# In the import block, add LimitWorkflow:
from src.workflows import (
    Workflow,
    PipelineContext,
    ParseWorkflow,
    ValidateWorkflow,
    LimitWorkflow,
    BuildWorkflow,
    ExecuteWorkflow,
    SummarizeWorkflow,
)

# In __init__, add default_limit parameter:
def __init__(
    self,
    db_path: str,
    llm_client: Any,
    system_prompt: str,
    schema: Dict[str, Any],
    default_limit: int = 100,
):
    self.db_path = db_path
    self.schema = schema

    parser = IRParser(llm_client, system_prompt)
    summarizer = ResultSummarizer(llm_client)

    self.steps: List[Workflow] = [
        ParseWorkflow(parser),
        ValidateWorkflow(),
        LimitWorkflow(default_limit=default_limit),
        BuildWorkflow(),
        ExecuteWorkflow(db_path),
        SummarizeWorkflow(summarizer),
    ]

    logger.info(f"QueryOrchestrator initialized for database: {db_path}")
    logger.debug(f"Schema contains {len(schema)} tables")
```

- [ ] **Step 3: Run all existing tests to verify nothing broke**

Run: `pytest tests/test_workflow_*.py tests/test_orchestrator_workflows.py -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/workflows/__init__.py src/orchestrator.py
git commit -m "feat: integrate LimitWorkflow into orchestrator pipeline"
```

---

### Task 3: Add Dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add fastapi and uvicorn to pyproject.toml**

In `pyproject.toml`, update the `dependencies` list:

```toml
dependencies = [
    "langgraph",
    "langchain-openai",
    "pydantic>=2.0.0",
    "fastapi",
    "uvicorn[standard]",
]
```

- [ ] **Step 2: Install dependencies**

Run: `pip install fastapi uvicorn[standard]`
Expected: successful installation

- [ ] **Step 3: Verify imports work**

Run: `python -c "import fastapi; import uvicorn; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add fastapi and uvicorn dependencies"
```

---

### Task 4: FastAPI Server

**Files:**
- Create: `src/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_server.py
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.server import app, QueryRequest


class TestQueryEndpoint:
    def setup_method(self):
        """Mock the orchestrator before each test."""
        import src.server as server_module
        self.mock_orchestrator = MagicMock()
        self._original = server_module.orchestrator
        server_module.orchestrator = self.mock_orchestrator
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.orchestrator = self._original

    def test_successful_query(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 artists.",
            "error": None,
            "metadata": {"stage": "complete", "timings": {"total_ms": 150}},
        }

        response = self.client.post("/query", json={"question": "Show me all artists"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["summary"] == "Found 3 artists."
        self.mock_orchestrator.process_query.assert_called_once_with("Show me all artists")

    def test_failed_query(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
            "metadata": {"stage": "parse", "timings": {"parse_ms": 50, "total_ms": 50}},
        }

        response = self.client.post("/query", json={"question": "bad query"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Parse failed"

    def test_missing_question_returns_422(self):
        response = self.client.post("/query", json={})
        assert response.status_code == 422

    def test_empty_question_is_accepted(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Empty query",
            "metadata": {"stage": "parse", "timings": {"total_ms": 0}},
        }

        response = self.client.post("/query", json={"question": ""})
        assert response.status_code == 200


class TestQueryRequest:
    def test_valid_request(self):
        req = QueryRequest(question="Show me all artists")
        assert req.question == "Show me all artists"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.server'`

- [ ] **Step 3: Implement the server**

```python
# src/server.py
"""
Odin FastAPI Server.

Exposes the query pipeline as a REST endpoint.
The orchestrator runs query processing in a thread to avoid blocking the event loop.
"""

import asyncio
import argparse
from typing import Any, Dict, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from src.llm_client import LLMClient
from src.llm.nl_to_ir import NaturalLanguageToIR
from src.schema.extractor import SQLiteSchemaExtractor
from src.orchestrator import QueryOrchestrator

app = FastAPI(title="Odin", description="LLM-to-SQL Pipeline")

orchestrator: Optional[QueryOrchestrator] = None


class QueryRequest(BaseModel):
    question: str


def create_app(
    db_path: str,
    llm_base_url: str = "http://localhost:1234/v1",
    llm_api_key: str = "lmstudio",
    llm_model: str = "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
    temperature: float = 0.1,
    default_limit: int = 100,
) -> FastAPI:
    """Create and configure the FastAPI app with an orchestrator."""
    global orchestrator

    schema_extractor = SQLiteSchemaExtractor(db_path)
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
        db_path=db_path,
        llm_client=llm_client,
        system_prompt=system_prompt,
        schema=validator_schema,
        default_limit=default_limit,
    )

    return app


@app.post("/query")
async def query(request: QueryRequest) -> Dict[str, Any]:
    result = await asyncio.to_thread(orchestrator.process_query, request.question)
    return result


if __name__ == "__main__":
    import uvicorn

    parser = argparse.ArgumentParser(description="Odin API Server")
    parser.add_argument("--db", required=True, help="Path to SQLite database file")
    parser.add_argument("--host", default="0.0.0.0", help="Server host")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--llm-url", default="http://localhost:1234/v1", help="LLM API base URL")
    parser.add_argument("--llm-key", default="lmstudio", help="LLM API key")
    parser.add_argument("--llm-model", default="qwen3.5-27b-claude-4.6-opus-reasoning-distilled", help="LLM model name")
    parser.add_argument("--temperature", type=float, default=0.1, help="LLM temperature")
    parser.add_argument("--default-limit", type=int, default=100, help="Default row limit")
    args = parser.parse_args()

    create_app(
        db_path=args.db,
        llm_base_url=args.llm_url,
        llm_api_key=args.llm_key,
        llm_model=args.llm_model,
        temperature=args.temperature,
        default_limit=args.default_limit,
    )

    uvicorn.run(app, host=args.host, port=args.port)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_server.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/test_workflow_*.py tests/test_orchestrator_workflows.py tests/test_server.py -v`
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat: add FastAPI server with POST /query endpoint"
```
