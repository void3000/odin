from unittest.mock import MagicMock
from src.orchestrator import QueryOrchestrator


class TestProcessQueryStream:
    def setup_method(self):
        self.mock_source = MagicMock()
        self.mock_source.name = "test_db"
        self.mock_source.source_type = "database"

        self.mock_llm = MagicMock()
        self.mock_llm.generate.return_value = (
            True,
            '{"operation": "SELECT", "source": {"table": "users"}, "fields": [{"field": "*"}]}'
        )

        self.schema = {
            "users": {"columns": {"id": {"type": "int"}, "name": {"type": "str"}}}
        }

    def _make_orchestrator(self):
        mock_native = MagicMock()
        mock_native.sql = "SELECT * FROM users"
        mock_native.params = []
        self.mock_source.build_query.return_value = mock_native
        self.mock_source.is_connected.return_value = False

        from src.sources.base import QueryResult
        self.mock_source.execute.return_value = QueryResult(
            rows=[{"id": 1}], columns=["id"], row_count=1, source_name="test_db",
        )

        self.mock_llm.generate_stream = MagicMock(return_value=iter(["Found ", "1 user."]))

        return QueryOrchestrator(
            source=self.mock_source,
            llm_client=self.mock_llm,
            system_prompt="test",
            schema=self.schema,
        )

    def test_emits_status_events_for_each_stage(self):
        orchestrator = self._make_orchestrator()
        events = []
        orchestrator.process_query_stream("show users", callback=lambda t, d: events.append((t, d)))

        status_events = [(t, d) for t, d in events if t == "status"]
        assert len(status_events) >= 4
        stages = [d["stage"] for _, d in status_events]
        assert "parse" in stages
        assert "execute" in stages
        assert "summarize" in stages

    def test_emits_token_events_during_summarization(self):
        orchestrator = self._make_orchestrator()
        events = []
        orchestrator.process_query_stream("show users", callback=lambda t, d: events.append((t, d)))

        token_events = [(t, d) for t, d in events if t == "token"]
        assert len(token_events) == 2
        assert token_events[0][1]["content"] == "Found "
        assert token_events[1][1]["content"] == "1 user."

    def test_emits_done_event(self):
        orchestrator = self._make_orchestrator()
        events = []
        orchestrator.process_query_stream("show users", callback=lambda t, d: events.append((t, d)))

        done_events = [(t, d) for t, d in events if t == "done"]
        assert len(done_events) == 1
        assert done_events[0][1]["success"] is True

    def test_emits_error_on_parse_failure(self):
        self.mock_llm.generate.return_value = (True, "INSERT is not supported")

        orchestrator = QueryOrchestrator(
            source=self.mock_source,
            llm_client=self.mock_llm,
            system_prompt="test",
            schema=self.schema,
        )

        events = []
        orchestrator.process_query_stream("insert a user", callback=lambda t, d: events.append((t, d)))

        token_events = [(t, d) for t, d in events if t == "token"]
        assert len(token_events) >= 1

        done_events = [(t, d) for t, d in events if t == "done"]
        assert done_events[0][1]["success"] is True  # parse failures are friendly
