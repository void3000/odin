from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage, AIMessage

from src.server import app, QueryRequest


class TestQueryEndpoint:
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

    def test_successful_query(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="Show me all artists"),
                AIMessage(content="Found 3 artists."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 3 artists.",
                "error": None,
            },
        }
        response = self.client.post("/v1/query", json={"input": "Show me all artists"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["type"] == "query"
        assert data["summary"] == "Found 3 artists."

    def test_failed_query(self):
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
        response = self.client.post("/v1/query", json={"input": "bad query"})
        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Parse failed"

    def test_missing_input_returns_422(self):
        response = self.client.post("/v1/query", json={})
        assert response.status_code == 422

    def test_chat_response(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="hello"),
                AIMessage(content="Hello! I can help you query the database."),
            ],
            "intent": "chat",
            "result": {
                "type": "chat",
                "success": True,
                "message": "Hello! I can help you query the database.",
            },
        }
        response = self.client.post("/v1/query", json={"input": "hello"})
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "chat"
        assert data["message"] == "Hello! I can help you query the database."


class TestQueryRequest:
    def test_valid_request(self):
        req = QueryRequest(input="Show me all artists")
        assert req.input == "Show me all artists"


class TestSessionEndpoints:
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

    def test_create_session(self):
        response = self.client.post("/v1/sessions")
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 36

    def test_delete_session(self):
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        delete_resp = self.client.delete(f"/v1/sessions/{session_id}")
        assert delete_resp.status_code == 204

    def test_delete_unknown_session_returns_404(self):
        response = self.client.delete("/v1/sessions/nonexistent")
        assert response.status_code == 404

    def test_query_with_valid_session(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="show all users"),
                AIMessage(content="Found 3 users."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 3 users.",
                "error": None,
            },
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        response = self.client.post(
            "/v1/query",
            json={"input": "show all users", "session_id": session_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["success"] is True

    def test_query_with_unknown_session_returns_404(self):
        response = self.client.post(
            "/v1/query",
            json={"input": "show all users", "session_id": "nonexistent"},
        )
        assert response.status_code == 404

    def test_query_without_session_works_stateless(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="show all users"),
                AIMessage(content="Found 3 users."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 3 users.",
                "error": None,
            },
        }
        response = self.client.post(
            "/v1/query",
            json={"input": "show all users"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" not in data or data.get("session_id") is None

    def test_query_passes_thread_id_to_graph(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="show all users"),
                AIMessage(content="Found 3 users."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 3 users.",
                "error": None,
            },
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        self.client.post(
            "/v1/query",
            json={"input": "show all users", "session_id": session_id},
        )
        call_args = self.mock_graph.invoke.call_args
        input_dict = call_args[0][0]
        assert isinstance(input_dict["messages"][0], HumanMessage)
        assert input_dict["messages"][0].content == "show all users"
        config = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("config")
        assert config["configurable"]["thread_id"] == session_id

    def test_stateless_query_has_no_config(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="show all users"),
                AIMessage(content="Found 3 users."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 3 users.",
                "error": None,
            },
        }
        self.client.post(
            "/v1/query",
            json={"input": "show all users"},
        )
        call_args = self.mock_graph.invoke.call_args
        if len(call_args[0]) > 1:
            assert call_args[0][1] is None
        else:
            config = call_args[1].get("config")
            assert config is None
