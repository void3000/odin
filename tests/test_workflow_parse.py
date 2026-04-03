from unittest.mock import MagicMock

from src.ir.models import QueryIR, TableSource, FieldExpr
from src.ir.parser import IRParser
from src.graph import ConversationTurn
from src.workflows.base import PipelineContext
from src.workflows.parse import ParseWorkflow


def _make_context() -> PipelineContext:
    return PipelineContext(
        natural_language="Show me all users",
        db_url="/tmp/test.db",
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

        mock_parser.parse.assert_called_once_with(
            "Show me all users",
            conversation_history=None,
        )


class TestParseWorkflowWithHistory:
    def test_passes_conversation_history_to_parser(self):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"success": True, "data": _make_query_ir()}

        workflow = ParseWorkflow(mock_parser)
        ctx = _make_context()
        ctx.conversation_history = [
            ConversationTurn(question="show all users", summary="Found 150 users."),
        ]
        workflow.run(ctx)

        mock_parser.parse.assert_called_once_with(
            "Show me all users",
            conversation_history=ctx.conversation_history,
        )

    def test_passes_none_history_when_not_set(self):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"success": True, "data": _make_query_ir()}

        workflow = ParseWorkflow(mock_parser)
        ctx = _make_context()
        workflow.run(ctx)

        mock_parser.parse.assert_called_once_with(
            "Show me all users",
            conversation_history=None,
        )


class TestBuildUserMessage:
    def setup_method(self):
        self.parser = IRParser(llm_client=MagicMock(), system_prompt="test")

    def test_no_history_returns_plain_question(self):
        result = self.parser._build_user_message("show all users", None)
        assert result == "show all users"

    def test_empty_history_returns_plain_question(self):
        result = self.parser._build_user_message("show all users", [])
        assert result == "show all users"

    def test_with_history_formats_conversation(self):
        history = [
            ConversationTurn(question="show all users", summary="Found 150 users."),
            ConversationTurn(question="filter by active", summary="42 active users."),
        ]
        result = self.parser._build_user_message("group by department", history)
        assert "Previous conversation:" in result
        assert "User: show all users" in result
        assert "Assistant: Found 150 users." in result
        assert "User: filter by active" in result
        assert "Assistant: 42 active users." in result
        assert "Current question: group by department" in result
