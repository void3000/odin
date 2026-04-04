from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.server import app


class TestChatStreamEndpoint:
    def setup_method(self):
        import src.server as server_module
        self.mock_graph = MagicMock()
        self._original_graph = server_module.graph
        server_module.graph = self.mock_graph
        self._original_sessions = server_module.sessions
        server_module.sessions = set()
        self._original_orchestrator = server_module.orchestrator
        self.mock_orchestrator = MagicMock()
        server_module.orchestrator = self.mock_orchestrator
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.graph = self._original_graph
        server_module.sessions = self._original_sessions
        server_module.orchestrator = self._original_orchestrator

    def test_returns_event_stream(self):
        def fake_stream(question, callback, conversation_history=None):
            callback("status", {"stage": "parse", "message": "Parsing..."})
            callback("token", {"content": "Hello"})
            callback("done", {"success": True})

        self.mock_orchestrator.process_query_stream.side_effect = fake_stream

        response = self.client.post(
            "/chat/stream",
            data={"input": "show artists"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = response.text
        assert "event: status" in body
        assert "event: token" in body
        assert "event: done" in body
        assert "Hello" in body

    def test_streams_with_session(self):
        import src.server as server_module
        server_module.sessions.add("sess-1")

        def fake_stream(question, callback, conversation_history=None):
            callback("token", {"content": "Result"})
            callback("done", {"success": True})

        self.mock_orchestrator.process_query_stream.side_effect = fake_stream

        response = self.client.post(
            "/chat/stream",
            data={"input": "show artists", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        assert "Result" in response.text
