from unittest.mock import MagicMock, patch

from src.ir.models import QueryIR, TableSource, FieldExpr
from src.orchestrator import QueryOrchestrator
from src.graph import ConversationTurn


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
            db_url="sqlite:///tmp/test.db",
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


class TestOrchestratorWithHistory:
    def test_process_query_passes_history_to_context(self):
        """Verify conversation_history flows into PipelineContext."""
        mock_llm = MagicMock()
        orchestrator = QueryOrchestrator(
            db_url="sqlite:///test.db",
            llm_client=mock_llm,
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
        mock_llm = MagicMock()
        orchestrator = QueryOrchestrator(
            db_url="sqlite:///test.db",
            llm_client=mock_llm,
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
