from unittest.mock import MagicMock

from src.ir.models import QueryIR, TableSource, FieldExpr
from src.orchestrator import QueryOrchestrator
from src.graph import ConversationTurn
from src.sources.base import QueryResult


def _make_query_ir() -> QueryIR:
    return QueryIR(
        operation="SELECT",
        source=TableSource(table="users"),
        fields=[FieldExpr(field="id")],
    )


def _make_mock_source():
    mock_source = MagicMock()
    mock_source.name = "test_db"
    mock_source.source_type = "sqlite"
    return mock_source


class TestOrchestratorWorkflows:
    def setup_method(self):
        self.schema = {"users": {"columns": {"id": {"type": "int"}, "name": {"type": "str"}}}}
        self.mock_llm = MagicMock()
        self.mock_source = _make_mock_source()
        self.orchestrator = QueryOrchestrator(
            source=self.mock_source,
            llm_client=self.mock_llm,
            system_prompt="You are a SQL parser.",
            schema=self.schema,
        )

    def test_full_pipeline_success(self):
        # Mock parse stage
        query_ir = _make_query_ir()
        self.orchestrator.steps[0].parser = MagicMock()
        self.orchestrator.steps[0].parser.parse.return_value = {"success": True, "data": query_ir}

        # Mock execute stage — source.execute returns QueryResult
        self.mock_source.is_connected.return_value = False
        mock_native = MagicMock()
        mock_native.sql = "SELECT id FROM users"
        mock_native.params = []
        self.mock_source.build_query.return_value = mock_native
        self.mock_source.execute.return_value = QueryResult(
            rows=[{"id": 1}, {"id": 2}],
            columns=["id"],
            row_count=2,
            source_name="test_db",
        )

        # Mock summarize stage
        self.orchestrator.steps[4].summarizer = MagicMock()
        self.orchestrator.steps[4].summarizer.summarize.return_value = (True, "Found 2 users.")

        result = self.orchestrator.process_query("Show me all users")

        assert result["success"] is True
        assert result["summary"] == "Found 2 users."

    def test_pipeline_stops_on_parse_failure(self):
        self.orchestrator.steps[0].parser = MagicMock()
        self.orchestrator.steps[0].parser.parse.return_value = {
            "success": False,
            "error": "Invalid JSON",
        }

        result = self.orchestrator.process_query("bad query")

        assert result["success"] is False
        assert result["error"] == "Invalid JSON"


class TestOrchestratorWithHistory:
    def test_process_query_passes_history_to_context(self):
        """Verify conversation_history flows into PipelineContext."""
        mock_source = _make_mock_source()
        orchestrator = QueryOrchestrator(
            source=mock_source,
            llm_client=MagicMock(),
            system_prompt="test",
            schema={"users": {"columns": {"id": {"type": "int"}}}},
        )

        history = [ConversationTurn(question="q1", summary="s1")]

        captured_contexts = []

        def capture_execute(ctx):
            captured_contexts.append(ctx)
            ctx.error = "stop early"
            return ctx

        orchestrator.steps[0].execute = capture_execute
        orchestrator.process_query("test query", conversation_history=history)

        assert len(captured_contexts) == 1
        assert captured_contexts[0].conversation_history == history

    def test_process_query_without_history_defaults_none(self):
        mock_source = _make_mock_source()
        orchestrator = QueryOrchestrator(
            source=mock_source,
            llm_client=MagicMock(),
            system_prompt="test",
            schema={"users": {"columns": {"id": {"type": "int"}}}},
        )

        captured_contexts = []

        def capture_execute(ctx):
            captured_contexts.append(ctx)
            ctx.error = "stop early"
            return ctx

        orchestrator.steps[0].execute = capture_execute
        orchestrator.process_query("test query")

        assert captured_contexts[0].conversation_history is None
