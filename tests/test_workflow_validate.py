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
