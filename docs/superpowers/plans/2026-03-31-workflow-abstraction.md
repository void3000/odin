# Workflow Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert each orchestrator pipeline stage into a self-contained Workflow class with a shared PipelineContext, making each stage independently runnable and testable.

**Architecture:** Abstract `Workflow` base class with `execute(context)` (timing/error handling) and `run(context)` (logic). A `PipelineContext` dataclass carries state between steps. The orchestrator becomes a thin loop over `List[Workflow]`.

**Tech Stack:** Python 3.13, Pydantic, pytest, unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-31-workflow-abstraction-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `src/workflows/__init__.py` | Public exports |
| Create | `src/workflows/base.py` | `Workflow` ABC + `PipelineContext` dataclass |
| Create | `src/workflows/parse.py` | `ParseWorkflow` — NL → QueryIR |
| Create | `src/workflows/validate.py` | `ValidateWorkflow` — IR schema validation |
| Create | `src/workflows/build.py` | `BuildWorkflow` — IR → SQL |
| Create | `src/workflows/execute.py` | `ExecuteWorkflow` — SQL → rows |
| Create | `src/workflows/summarize.py` | `SummarizeWorkflow` — rows → NL summary |
| Create | `tests/test_workflow_base.py` | Tests for Workflow ABC + PipelineContext |
| Create | `tests/test_workflow_parse.py` | Tests for ParseWorkflow |
| Create | `tests/test_workflow_validate.py` | Tests for ValidateWorkflow |
| Create | `tests/test_workflow_build.py` | Tests for BuildWorkflow |
| Create | `tests/test_workflow_execute.py` | Tests for ExecuteWorkflow |
| Create | `tests/test_workflow_summarize.py` | Tests for SummarizeWorkflow |
| Modify | `src/orchestrator.py` | Rewrite to use Workflow chain |
| Create | `tests/test_orchestrator_workflows.py` | Integration test: full pipeline via orchestrator |

---

### Task 1: Workflow Base Class + PipelineContext

**Files:**
- Create: `src/workflows/__init__.py`
- Create: `src/workflows/base.py`
- Test: `tests/test_workflow_base.py`

- [ ] **Step 1: Write failing tests for PipelineContext and Workflow**

```python
# tests/test_workflow_base.py
import pytest
from src.workflows.base import Workflow, PipelineContext


class TestPipelineContext:
    def test_create_with_required_fields(self):
        ctx = PipelineContext(
            natural_language="Show me all users",
            db_path="/tmp/test.db",
            schema={"users": {"columns": {"id": {"type": "int"}}}},
        )
        assert ctx.natural_language == "Show me all users"
        assert ctx.db_path == "/tmp/test.db"
        assert ctx.schema == {"users": {"columns": {"id": {"type": "int"}}}}

    def test_optional_fields_default_to_none(self):
        ctx = PipelineContext(
            natural_language="test",
            db_path="/tmp/test.db",
            schema={},
        )
        assert ctx.query_ir is None
        assert ctx.sql is None
        assert ctx.params is None
        assert ctx.rows is None
        assert ctx.summary is None
        assert ctx.error is None
        assert ctx.failed_stage is None

    def test_timings_default_to_empty_dict(self):
        ctx = PipelineContext(
            natural_language="test",
            db_path="/tmp/test.db",
            schema={},
        )
        assert ctx.timings == {}


class _StubWorkflow(Workflow):
    name = "stub"

    def run(self, context: PipelineContext) -> PipelineContext:
        context.summary = "done"
        return context


class _FailingWorkflow(Workflow):
    name = "failing"

    def run(self, context: PipelineContext) -> PipelineContext:
        raise ValueError("something broke")


class TestWorkflow:
    def test_execute_calls_run_and_records_timing(self):
        ctx = PipelineContext(
            natural_language="test",
            db_path="/tmp/test.db",
            schema={},
        )
        workflow = _StubWorkflow()
        result = workflow.execute(ctx)
        assert result.summary == "done"
        assert "stub_ms" in result.timings
        assert result.timings["stub_ms"] >= 0
        assert result.error is None

    def test_execute_catches_exception_and_sets_error(self):
        ctx = PipelineContext(
            natural_language="test",
            db_path="/tmp/test.db",
            schema={},
        )
        workflow = _FailingWorkflow()
        result = workflow.execute(ctx)
        assert result.error == "something broke"
        assert result.failed_stage == "failing"
        assert "failing_ms" in result.timings

    def test_workflow_is_abstract(self):
        with pytest.raises(TypeError):
            Workflow()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.workflows'`

- [ ] **Step 3: Create `src/workflows/` package and implement base classes**

```python
# src/workflows/__init__.py
from src.workflows.base import Workflow, PipelineContext

__all__ = ["Workflow", "PipelineContext"]
```

```python
# src/workflows/base.py
"""Workflow base class and PipelineContext for the query pipeline."""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.ir.models import QueryIR
from src.logging_config import get_component_logger

logger = get_component_logger("workflow")


@dataclass
class PipelineContext:
    """Shared state that flows through the pipeline."""

    # Input (set before pipeline starts)
    natural_language: str
    db_path: str
    schema: Dict[str, Any]

    # Stage outputs
    query_ir: Optional[QueryIR] = None
    sql: Optional[str] = None
    params: Optional[List] = None
    rows: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None

    # Metadata
    timings: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    failed_stage: Optional[str] = None


class Workflow(ABC):
    """Abstract base class for pipeline workflow steps."""

    name: str

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Run the workflow with timing and error handling."""
        logger.info(f"Stage: {self.name}...")
        t0 = time.perf_counter()
        try:
            context = self.run(context)
        except Exception as e:
            context.error = str(e)
            context.failed_stage = self.name
        context.timings[f"{self.name}_ms"] = (time.perf_counter() - t0) * 1000
        return context

    @abstractmethod
    def run(self, context: PipelineContext) -> PipelineContext:
        """Subclasses implement this. Set context fields and return context."""
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_base.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/workflows/__init__.py src/workflows/base.py tests/test_workflow_base.py
git commit -m "feat: add Workflow ABC and PipelineContext dataclass"
```

---

### Task 2: ParseWorkflow

**Files:**
- Create: `src/workflows/parse.py`
- Test: `tests/test_workflow_parse.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workflow_parse.py
from unittest.mock import MagicMock

from src.ir.models import QueryIR, TableSource, FieldExpr
from src.workflows.base import PipelineContext
from src.workflows.parse import ParseWorkflow


def _make_context() -> PipelineContext:
    return PipelineContext(
        natural_language="Show me all users",
        db_path="/tmp/test.db",
        schema={"users": {"columns": {"id": {"type": "int"}}}},
    )


def _make_query_ir() -> QueryIR:
    return QueryIR(
        operation="SELECT",
        source=TableSource(table="users"),
        fields=[FieldExpr(field="id")],
    )


class TestParseWorkflow:
    def test_successful_parse_sets_query_ir(self):
        mock_parser = MagicMock()
        query_ir = _make_query_ir()
        mock_parser.parse.return_value = {"success": True, "data": query_ir}

        workflow = ParseWorkflow(mock_parser)
        ctx = workflow.run(_make_context())

        assert ctx.query_ir == query_ir
        assert ctx.error is None

    def test_failed_parse_sets_error(self):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"success": False, "error": "LLM returned invalid JSON"}

        workflow = ParseWorkflow(mock_parser)
        ctx = workflow.run(_make_context())

        assert ctx.query_ir is None
        assert ctx.error == "LLM returned invalid JSON"
        assert ctx.failed_stage == "parse"

    def test_passes_natural_language_to_parser(self):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"success": True, "data": _make_query_ir()}

        workflow = ParseWorkflow(mock_parser)
        ctx = _make_context()
        workflow.run(ctx)

        mock_parser.parse.assert_called_once_with("Show me all users")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.workflows.parse'`

- [ ] **Step 3: Implement ParseWorkflow**

```python
# src/workflows/parse.py
"""ParseWorkflow — converts natural language to QueryIR via LLM."""

from src.ir.parser import IRParser
from src.workflows.base import Workflow, PipelineContext


class ParseWorkflow(Workflow):
    name = "parse"

    def __init__(self, parser: IRParser):
        self.parser = parser

    def run(self, context: PipelineContext) -> PipelineContext:
        result = self.parser.parse(context.natural_language)
        if not result["success"]:
            context.error = result["error"]
            context.failed_stage = self.name
            return context
        context.query_ir = result["data"]
        return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_parse.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/workflows/parse.py tests/test_workflow_parse.py
git commit -m "feat: add ParseWorkflow for NL-to-IR stage"
```

---

### Task 3: ValidateWorkflow

**Files:**
- Create: `src/workflows/validate.py`
- Test: `tests/test_workflow_validate.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workflow_validate.py
from unittest.mock import MagicMock, patch

from src.ir.models import QueryIR, TableSource, FieldExpr
from src.workflows.base import PipelineContext
from src.workflows.validate import ValidateWorkflow


def _make_context(query_ir=None) -> PipelineContext:
    schema = {"users": {"columns": {"id": {"type": "int"}, "name": {"type": "str"}}}}
    ctx = PipelineContext(
        natural_language="Show me all users",
        db_path="/tmp/test.db",
        schema=schema,
    )
    if query_ir:
        ctx.query_ir = query_ir
    return ctx


def _make_query_ir() -> QueryIR:
    return QueryIR(
        operation="SELECT",
        source=TableSource(table="users"),
        fields=[FieldExpr(field="id")],
    )


class TestValidateWorkflow:
    @patch("src.workflows.validate.IRValidator")
    def test_valid_ir_passes(self, MockValidator):
        MockValidator.return_value.validate_query.return_value = []

        workflow = ValidateWorkflow()
        ctx = _make_context(_make_query_ir())
        result = workflow.run(ctx)

        assert result.error is None
        MockValidator.assert_called_once_with(ctx.schema)

    @patch("src.workflows.validate.IRValidator")
    def test_invalid_ir_sets_error(self, MockValidator):
        MockValidator.return_value.validate_query.return_value = [
            "Table 'orders' not found in schema",
            "Field 'total' not found in table 'users'",
        ]

        workflow = ValidateWorkflow()
        ctx = _make_context(_make_query_ir())
        result = workflow.run(ctx)

        assert result.failed_stage == "validate"
        assert "Table 'orders' not found in schema" in result.error
        assert "Field 'total' not found in table 'users'" in result.error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.workflows.validate'`

- [ ] **Step 3: Implement ValidateWorkflow**

```python
# src/workflows/validate.py
"""ValidateWorkflow — validates QueryIR against database schema."""

from src.ir.validator import IRValidator
from src.workflows.base import Workflow, PipelineContext


class ValidateWorkflow(Workflow):
    name = "validate"

    def run(self, context: PipelineContext) -> PipelineContext:
        validator = IRValidator(context.schema)
        errors = validator.validate_query(context.query_ir)
        if errors:
            context.error = "Validation failed:\n" + "\n".join(f"- {e}" for e in errors)
            context.failed_stage = self.name
        return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_validate.py -v`
Expected: all 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/workflows/validate.py tests/test_workflow_validate.py
git commit -m "feat: add ValidateWorkflow for IR schema validation stage"
```

---

### Task 4: BuildWorkflow

**Files:**
- Create: `src/workflows/build.py`
- Test: `tests/test_workflow_build.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workflow_build.py
from src.ir.models import QueryIR, TableSource, FieldExpr
from src.workflows.base import PipelineContext
from src.workflows.build import BuildWorkflow


def _make_context() -> PipelineContext:
    ctx = PipelineContext(
        natural_language="Show me all users",
        db_path="/tmp/test.db",
        schema={"users": {"columns": {"id": {"type": "int"}, "name": {"type": "str"}}}},
    )
    ctx.query_ir = QueryIR(
        operation="SELECT",
        source=TableSource(table="users"),
        fields=[FieldExpr(field="id"), FieldExpr(field="name")],
    )
    return ctx


class TestBuildWorkflow:
    def test_builds_sql_from_ir(self):
        workflow = BuildWorkflow()
        ctx = workflow.run(_make_context())

        assert ctx.sql is not None
        assert "SELECT" in ctx.sql.upper()
        assert "users" in ctx.sql
        assert ctx.error is None

    def test_sets_params(self):
        workflow = BuildWorkflow()
        ctx = workflow.run(_make_context())

        assert ctx.params is not None
        assert isinstance(ctx.params, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_build.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.workflows.build'`

- [ ] **Step 3: Implement BuildWorkflow**

```python
# src/workflows/build.py
"""BuildWorkflow — converts validated QueryIR to SQL."""

from src.query_builder import SQLBuilder
from src.workflows.base import Workflow, PipelineContext


class BuildWorkflow(Workflow):
    name = "build"

    def run(self, context: PipelineContext) -> PipelineContext:
        builder = SQLBuilder()
        context.sql, context.params = builder.build(context.query_ir)
        return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_build.py -v`
Expected: all 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/workflows/build.py tests/test_workflow_build.py
git commit -m "feat: add BuildWorkflow for IR-to-SQL stage"
```

---

### Task 5: ExecuteWorkflow

**Files:**
- Create: `src/workflows/execute.py`
- Test: `tests/test_workflow_execute.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workflow_execute.py
from unittest.mock import MagicMock, patch

from src.workflows.base import PipelineContext
from src.workflows.execute import ExecuteWorkflow


def _make_context() -> PipelineContext:
    ctx = PipelineContext(
        natural_language="Show me all users",
        db_path="/tmp/test.db",
        schema={},
    )
    ctx.sql = "SELECT id, name FROM users"
    ctx.params = []
    return ctx


class TestExecuteWorkflow:
    @patch("src.workflows.execute.SQLiteConnector")
    def test_successful_execution_sets_rows(self, MockConnector):
        mock_conn = MockConnector.return_value
        mock_raw = MagicMock()
        mock_raw.columns = ["id", "name"]
        mock_raw.rows = [(1, "Alice"), (2, "Bob")]
        mock_conn.execute_query.return_value = mock_raw

        workflow = ExecuteWorkflow("/tmp/test.db")
        ctx = workflow.run(_make_context())

        assert ctx.rows == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        assert ctx.error is None
        mock_conn.connect.assert_called_once()
        mock_conn.disconnect.assert_called_once()

    @patch("src.workflows.execute.SQLiteConnector")
    def test_database_error_sets_error(self, MockConnector):
        from src.executor.errors import DatabaseError

        mock_conn = MockConnector.return_value
        mock_conn.execute_query.side_effect = DatabaseError("table not found")

        workflow = ExecuteWorkflow("/tmp/test.db")
        ctx = workflow.run(_make_context())

        assert ctx.error == "table not found"
        assert ctx.failed_stage == "execute"
        mock_conn.disconnect.assert_called_once()

    @patch("src.workflows.execute.SQLiteConnector")
    def test_passes_sql_and_params_to_connector(self, MockConnector):
        mock_conn = MockConnector.return_value
        mock_raw = MagicMock()
        mock_raw.columns = ["id"]
        mock_raw.rows = []
        mock_conn.execute_query.return_value = mock_raw

        workflow = ExecuteWorkflow("/tmp/test.db")
        ctx = _make_context()
        ctx.sql = "SELECT id FROM users WHERE name = ?"
        ctx.params = ["Alice"]
        workflow.run(ctx)

        mock_conn.execute_query.assert_called_once_with(
            {"sql": "SELECT id FROM users WHERE name = ?", "params": ["Alice"]}
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_execute.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.workflows.execute'`

- [ ] **Step 3: Implement ExecuteWorkflow**

```python
# src/workflows/execute.py
"""ExecuteWorkflow — executes SQL against the database."""

from src.executor.connectors.sqlite import SQLiteConnector
from src.executor.errors import DatabaseError
from src.workflows.base import Workflow, PipelineContext


class ExecuteWorkflow(Workflow):
    name = "execute"

    def __init__(self, db_path: str):
        self.db_path = db_path

    def run(self, context: PipelineContext) -> PipelineContext:
        connector = SQLiteConnector(database=self.db_path)
        try:
            connector.connect()
            raw = connector.execute_query(
                {"sql": context.sql, "params": context.params or []}
            )
            context.rows = [
                dict(zip(raw.columns, row)) for row in raw.rows
            ]
        except DatabaseError as e:
            context.error = str(e)
            context.failed_stage = self.name
        finally:
            connector.disconnect()
        return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_execute.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/workflows/execute.py tests/test_workflow_execute.py
git commit -m "feat: add ExecuteWorkflow for SQL execution stage"
```

---

### Task 6: SummarizeWorkflow

**Files:**
- Create: `src/workflows/summarize.py`
- Test: `tests/test_workflow_summarize.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workflow_summarize.py
from unittest.mock import MagicMock

from src.workflows.base import PipelineContext
from src.workflows.summarize import SummarizeWorkflow


def _make_context() -> PipelineContext:
    ctx = PipelineContext(
        natural_language="Show me all users",
        db_path="/tmp/test.db",
        schema={},
    )
    ctx.sql = "SELECT id, name FROM users"
    ctx.rows = [{"id": 1, "name": "Alice"}]
    return ctx


class TestSummarizeWorkflow:
    def test_successful_summary(self):
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (True, "There is 1 user: Alice.")

        workflow = SummarizeWorkflow(mock_summarizer)
        ctx = workflow.run(_make_context())

        assert ctx.summary == "There is 1 user: Alice."
        assert ctx.error is None

    def test_failed_summary_sets_error(self):
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (False, "LLM request failed")

        workflow = SummarizeWorkflow(mock_summarizer)
        ctx = workflow.run(_make_context())

        assert ctx.summary is None
        assert ctx.error == "LLM request failed"
        assert ctx.failed_stage == "summarize"

    def test_passes_correct_args_to_summarizer(self):
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (True, "summary")

        workflow = SummarizeWorkflow(mock_summarizer)
        ctx = _make_context()
        workflow.run(ctx)

        mock_summarizer.summarize.assert_called_once_with(
            "Show me all users",
            [{"id": 1, "name": "Alice"}],
            "SELECT id, name FROM users",
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_summarize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.workflows.summarize'`

- [ ] **Step 3: Implement SummarizeWorkflow**

```python
# src/workflows/summarize.py
"""SummarizeWorkflow — summarizes query results using LLM."""

from src.summarizer import ResultSummarizer
from src.workflows.base import Workflow, PipelineContext


class SummarizeWorkflow(Workflow):
    name = "summarize"

    def __init__(self, summarizer: ResultSummarizer):
        self.summarizer = summarizer

    def run(self, context: PipelineContext) -> PipelineContext:
        success, summary = self.summarizer.summarize(
            context.natural_language, context.rows, context.sql
        )
        if not success:
            context.error = summary
            context.failed_stage = self.name
            return context
        context.summary = summary
        return context
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_summarize.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/workflows/summarize.py tests/test_workflow_summarize.py
git commit -m "feat: add SummarizeWorkflow for result summarization stage"
```

---

### Task 7: Update `__init__.py` Exports

**Files:**
- Modify: `src/workflows/__init__.py`

- [ ] **Step 1: Update exports to include all workflows**

```python
# src/workflows/__init__.py
from src.workflows.base import Workflow, PipelineContext
from src.workflows.parse import ParseWorkflow
from src.workflows.validate import ValidateWorkflow
from src.workflows.build import BuildWorkflow
from src.workflows.execute import ExecuteWorkflow
from src.workflows.summarize import SummarizeWorkflow

__all__ = [
    "Workflow",
    "PipelineContext",
    "ParseWorkflow",
    "ValidateWorkflow",
    "BuildWorkflow",
    "ExecuteWorkflow",
    "SummarizeWorkflow",
]
```

- [ ] **Step 2: Verify all imports work**

Run: `python -c "from src.workflows import Workflow, PipelineContext, ParseWorkflow, ValidateWorkflow, BuildWorkflow, ExecuteWorkflow, SummarizeWorkflow; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Commit**

```bash
git add src/workflows/__init__.py
git commit -m "feat: export all workflow classes from workflows package"
```

---

### Task 8: Rewrite Orchestrator to Use Workflows

**Files:**
- Modify: `src/orchestrator.py`
- Test: `tests/test_orchestrator_workflows.py`

- [ ] **Step 1: Write integration test for workflow-based orchestrator**

```python
# tests/test_orchestrator_workflows.py
from unittest.mock import MagicMock, patch

from src.ir.models import QueryIR, TableSource, FieldExpr
from src.orchestrator import QueryOrchestrator


def _make_query_ir() -> QueryIR:
    return QueryIR(
        operation="SELECT",
        source=TableSource(table="users"),
        fields=[FieldExpr(field="id")],
    )


class TestOrchestratorWorkflows:
    def setup_method(self):
        self.schema = {"users": {"columns": {"id": {"type": "int"}, "name": {"type": "str"}}}}
        self.mock_llm = MagicMock()
        self.orchestrator = QueryOrchestrator(
            db_path="/tmp/test.db",
            llm_client=self.mock_llm,
            system_prompt="You are a SQL parser.",
            schema=self.schema,
        )

    @patch("src.workflows.execute.SQLiteConnector")
    @patch("src.workflows.parse.IRParser")
    def test_full_pipeline_success(self, MockParser, MockConnector):
        # Mock parse stage
        query_ir = _make_query_ir()
        self.orchestrator.steps[0].parser = MagicMock()
        self.orchestrator.steps[0].parser.parse.return_value = {"success": True, "data": query_ir}

        # Mock execute stage
        mock_conn = MockConnector.return_value
        mock_raw = MagicMock()
        mock_raw.columns = ["id"]
        mock_raw.rows = [(1,), (2,)]
        mock_conn.execute_query.return_value = mock_raw

        # Mock summarize stage
        self.orchestrator.steps[4].summarizer = MagicMock()
        self.orchestrator.steps[4].summarizer.summarize.return_value = (True, "Found 2 users.")

        result = self.orchestrator.process_query("Show me all users")

        assert result["success"] is True
        assert result["summary"] == "Found 2 users."
        assert "timings" in result["metadata"]
        assert result["metadata"]["stage"] == "complete"

    def test_pipeline_stops_on_parse_failure(self):
        self.orchestrator.steps[0].parser = MagicMock()
        self.orchestrator.steps[0].parser.parse.return_value = {
            "success": False,
            "error": "Invalid JSON",
        }

        result = self.orchestrator.process_query("bad query")

        assert result["success"] is False
        assert result["error"] == "Invalid JSON"
        assert result["metadata"]["stage"] == "parse"

    def test_result_contains_timing_metadata(self):
        self.orchestrator.steps[0].parser = MagicMock()
        self.orchestrator.steps[0].parser.parse.return_value = {
            "success": False,
            "error": "fail",
        }

        result = self.orchestrator.process_query("test")

        assert "parse_ms" in result["metadata"]["timings"]
        assert "total_ms" in result["metadata"]["timings"]
```

- [ ] **Step 2: Run tests to verify current state**

Run: `pytest tests/test_orchestrator_workflows.py -v`
Expected: may FAIL or PASS depending on current orchestrator — this confirms baseline

- [ ] **Step 3: Rewrite orchestrator to use workflows**

Replace the entire contents of `src/orchestrator.py` with:

```python
"""
Query Orchestrator.

Coordinates the complete query processing pipeline using Workflow steps:
1. Parse natural language to IR
2. Validate IR against schema
3. Build SQL from validated IR
4. Execute SQL and return results
5. Summarize results using LLM
"""

import logging
from typing import Any, Dict, List

from src.ir.parser import IRParser
from src.summarizer import ResultSummarizer
from src.workflows import (
    Workflow,
    PipelineContext,
    ParseWorkflow,
    ValidateWorkflow,
    BuildWorkflow,
    ExecuteWorkflow,
    SummarizeWorkflow,
)
from src.logging_config import get_component_logger

logger = get_component_logger("orchestrator")


class QueryOrchestrator:
    """
    Orchestrates the complete query processing pipeline.

    Pipeline stages are Workflow instances chained together.
    Each stage reads from and writes to a shared PipelineContext.
    """

    def __init__(
        self,
        db_path: str,
        llm_client: Any,
        system_prompt: str,
        schema: Dict[str, Any],
    ):
        self.db_path = db_path
        self.schema = schema

        parser = IRParser(llm_client, system_prompt)
        summarizer = ResultSummarizer(llm_client)

        self.steps: List[Workflow] = [
            ParseWorkflow(parser),
            ValidateWorkflow(),
            BuildWorkflow(),
            ExecuteWorkflow(db_path),
            SummarizeWorkflow(summarizer),
        ]

        logger.info(f"QueryOrchestrator initialized for database: {db_path}")
        logger.debug(f"Schema contains {len(schema)} tables")

    def process_query(self, natural_language: str) -> Dict[str, Any]:
        """Process a natural language query through the complete pipeline."""
        logger.info(f"Processing query: {natural_language}")

        context = PipelineContext(
            natural_language=natural_language,
            db_path=self.db_path,
            schema=self.schema,
        )

        for step in self.steps:
            context = step.execute(context)
            if context.error:
                break

        context.timings["total_ms"] = sum(context.timings.values())
        return self._to_result_dict(context)

    def _to_result_dict(self, context: PipelineContext) -> Dict[str, Any]:
        """Convert PipelineContext to the existing result dict format."""
        result: Dict[str, Any] = {
            "success": context.error is None,
            "error": context.error,
            "metadata": {
                "timings": context.timings,
                "stage": context.failed_stage or "complete",
            },
        }
        if context.query_ir:
            result["metadata"]["ir"] = context.query_ir.model_dump()
        if context.sql:
            result["metadata"]["sql"] = context.sql
            result["metadata"]["params"] = context.params
        if context.rows is not None:
            result["metadata"]["row_count"] = len(context.rows)
        if context.summary:
            result["summary"] = context.summary
        return result

    def get_schema_summary(self) -> Dict[str, Any]:
        """Get a summary of the database schema."""
        summary = {}
        for table_name, table_info in self.schema.items():
            columns = table_info.get("columns", {})
            summary[table_name] = {
                "column_count": len(columns),
                "columns": list(columns.keys()),
            }
        return summary
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/test_orchestrator_workflows.py tests/test_workflow_base.py tests/test_workflow_parse.py tests/test_workflow_validate.py tests/test_workflow_build.py tests/test_workflow_execute.py tests/test_workflow_summarize.py -v`
Expected: all tests PASS

- [ ] **Step 5: Run full test suite to check nothing is broken**

Run: `pytest -v`
Expected: all existing tests still PASS

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator_workflows.py
git commit -m "refactor: rewrite orchestrator to use Workflow pipeline"
```
