import pytest
from src.workflows.base import Workflow, PipelineContext
from src.graph import ConversationTurn


class TestPipelineContext:
    def test_create_with_required_fields(self):
        ctx = PipelineContext(
            natural_language="Show me all users",
            db_url="sqlite:///test.db",
            schema={"users": {"columns": {"id": {"type": "int"}}}},
        )
        assert ctx.natural_language == "Show me all users"
        assert ctx.db_url == "sqlite:///test.db"
        assert ctx.schema == {"users": {"columns": {"id": {"type": "int"}}}}

    def test_optional_fields_default_to_none(self):
        ctx = PipelineContext(
            natural_language="test",
            db_url="sqlite:///test.db",
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
            db_url="sqlite:///test.db",
            schema={},
        )
        assert ctx.timings == {}

    def test_pipeline_context_has_conversation_history(self):
        ctx = PipelineContext(
            natural_language="test",
            db_url="sqlite:///test.db",
            schema={},
            conversation_history=[
                ConversationTurn(question="q1", summary="s1"),
            ],
        )
        assert len(ctx.conversation_history) == 1
        assert ctx.conversation_history[0].question == "q1"

    def test_pipeline_context_conversation_history_defaults_none(self):
        ctx = PipelineContext(
            natural_language="test",
            db_url="sqlite:///test.db",
            schema={},
        )
        assert ctx.conversation_history is None


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
            db_url="sqlite:///test.db",
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
            db_url="sqlite:///test.db",
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

    def test_subclass_without_name_raises(self):
        with pytest.raises(TypeError, match="must define a class attribute 'name'"):
            class _NoNameWorkflow(Workflow):
                def run(self, context):
                    return context
