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

    def test_applies_default_limit_when_none(self):
        workflow = BuildWorkflow(default_limit=100)
        ctx = _make_context()
        assert ctx.query_ir.limit is None
        workflow.run(ctx)
        assert ctx.query_ir.limit == 100

    def test_does_not_override_existing_limit(self):
        workflow = BuildWorkflow(default_limit=100)
        ctx = _make_context()
        ctx.query_ir.limit = 10
        workflow.run(ctx)
        assert ctx.query_ir.limit == 10

    def test_custom_default_limit(self):
        workflow = BuildWorkflow(default_limit=50)
        ctx = _make_context()
        workflow.run(ctx)
        assert ctx.query_ir.limit == 50
