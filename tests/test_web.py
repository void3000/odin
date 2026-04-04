from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage, AIMessage

from src.server import app


class TestWebRoutes:
    def setup_method(self):
        import src.server as server_module
        self.mock_graph = MagicMock()
        self._original_graph = server_module.graph
        server_module.graph = self.mock_graph
        self._original_sessions = server_module.sessions
        server_module.sessions = set()
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.graph = self._original_graph
        server_module.sessions = self._original_sessions

    def test_index_returns_html(self):
        response = self.client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Odin" in response.text

    def test_create_session_returns_sidebar(self):
        response = self.client.post("/sessions")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        import src.server as server_module
        assert len(server_module.sessions) == 1

    def test_delete_session_returns_sidebar(self):
        import src.server as server_module
        server_module.sessions.add("test-session-id")
        response = self.client.delete("/sessions/test-session-id")
        assert response.status_code == 200
        assert "test-session-id" not in server_module.sessions

    def test_chat_returns_message_partial(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="show all artists"),
                AIMessage(content="Found 275 artists."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 275 artists.",
                "error": None,
            },
        }
        response = self.client.post("/chat", data={"input": "show all artists"})
        assert response.status_code == 200
        assert "Found 275 artists." in response.text
        assert "assistant" in response.text

    def test_chat_with_session(self):
        import src.server as server_module
        server_module.sessions.add("sess-123")
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="show all artists"),
                AIMessage(content="Found 275 artists."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 275 artists.",
                "error": None,
            },
        }
        response = self.client.post(
            "/chat",
            data={"input": "show all artists", "session_id": "sess-123"},
        )
        assert response.status_code == 200
        call_args = self.mock_graph.invoke.call_args
        config = call_args[0][1]
        assert config["configurable"]["thread_id"] == "sess-123"

    def test_chat_error_shows_error_message(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="bad query"),
                AIMessage(content="Parse failed"),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": False,
                "error": "Parse failed",
            },
        }
        response = self.client.post("/chat", data={"input": "bad query"})
        assert response.status_code == 200
        assert "Error:" in response.text
        assert "Parse failed" in response.text

    def test_load_session_returns_chat_area(self):
        import src.server as server_module
        server_module.sessions.add("sess-456")

        mock_state = MagicMock()
        mock_state.values = {
            "messages": [
                HumanMessage(content="show artists"),
                AIMessage(content="Found 275 artists."),
            ]
        }
        self.mock_graph.get_state.return_value = mock_state

        response = self.client.get("/sessions/sess-456")
        assert response.status_code == 200
        assert "show artists" in response.text
        assert "Found 275 artists." in response.text

    def test_sidebar_refresh(self):
        response = self.client.get("/sidebar")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
