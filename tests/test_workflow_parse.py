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
