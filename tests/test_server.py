from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.server import app, QueryRequest


class TestQueryEndpoint:
    def setup_method(self):
        import src.server as server_module
        from src.session import SessionManager
        self.mock_graph = MagicMock()
        self._original_graph = server_module.graph
        server_module.graph = self.mock_graph
        self._original_session_manager = server_module.session_manager
        server_module.session_manager = SessionManager()
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.graph = self._original_graph
        server_module.session_manager = self._original_session_manager

    def test_successful_query(self):
        self.mock_graph.invoke.return_value = {
            "input": "Show me all artists",
            "conversation_history": None,
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
            "input": "bad query",
            "conversation_history": None,
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
            "input": "hello",
            "conversation_history": None,
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
        from src.session import SessionManager
        self.mock_graph = MagicMock()
        self._original_graph = server_module.graph
        server_module.graph = self.mock_graph
        self.session_manager = SessionManager(ttl_seconds=1800, max_turns=10)
        self._original_session_manager = server_module.session_manager
        server_module.session_manager = self.session_manager
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.graph = self._original_graph
        server_module.session_manager = self._original_session_manager

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
            "input": "show all users",
            "conversation_history": None,
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
        assert data["type"] == "query"

    def test_query_with_unknown_session_returns_404(self):
        response = self.client.post(
            "/v1/query",
            json={"input": "show all users", "session_id": "nonexistent"},
        )
        assert response.status_code == 404

    def test_query_without_session_works_stateless(self):
        self.mock_graph.invoke.return_value = {
            "input": "show all users",
            "conversation_history": None,
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

    def test_successful_query_appends_turn_to_session(self):
        self.mock_graph.invoke.return_value = {
            "input": "show all users",
            "conversation_history": None,
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
        session = self.session_manager.get(session_id)
        assert len(session.turns) == 1
        assert session.turns[0].question == "show all users"
        assert session.turns[0].summary == "Found 3 users."

    def test_chat_response_appends_turn_to_session(self):
        self.mock_graph.invoke.return_value = {
            "input": "what tables exist?",
            "conversation_history": None,
            "intent": "chat",
            "result": {
                "type": "chat",
                "success": True,
                "message": "There are 3 tables: users, orders, products.",
            },
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        self.client.post(
            "/v1/query",
            json={"input": "what tables exist?", "session_id": session_id},
        )
        session = self.session_manager.get(session_id)
        assert len(session.turns) == 1
        assert session.turns[0].question == "what tables exist?"
        assert session.turns[0].summary == "There are 3 tables: users, orders, products."

    def test_failed_query_does_not_append_turn(self):
        self.mock_graph.invoke.return_value = {
            "input": "bad query",
            "conversation_history": None,
            "intent": "query",
            "result": {
                "type": "query",
                "success": False,
                "error": "Parse failed",
            },
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        self.client.post(
            "/v1/query",
            json={"input": "bad query", "session_id": session_id},
        )
        session = self.session_manager.get(session_id)
        assert len(session.turns) == 0

    def test_query_passes_history_to_graph(self):
        self.mock_graph.invoke.return_value = {
            "input": "filter by active",
            "conversation_history": None,
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Result.",
                "error": None,
            },
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]

        # Manually add a turn to simulate first query
        self.session_manager.add_turn(session_id, "show all users", "Found 10 users.")

        self.client.post(
            "/v1/query",
            json={"input": "filter by active", "session_id": session_id},
        )
        call_args = self.mock_graph.invoke.call_args[0][0]
        assert call_args["input"] == "filter by active"
        assert len(call_args["conversation_history"]) == 1
        assert call_args["conversation_history"][0].question == "show all users"
