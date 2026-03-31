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
