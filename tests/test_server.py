from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.server import app, QueryRequest


class TestQueryEndpoint:
    def setup_method(self):
        """Mock the orchestrator and session_manager before each test."""
        import src.server as server_module
        from src.session import SessionManager
        self.mock_orchestrator = MagicMock()
        self._original = server_module.orchestrator
        server_module.orchestrator = self.mock_orchestrator
        self._original_session_manager = server_module.session_manager
        server_module.session_manager = SessionManager()
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.orchestrator = self._original
        server_module.session_manager = self._original_session_manager

    def test_successful_query(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 artists.",
            "error": None,
            "metadata": {"stage": "complete", "timings": {"total_ms": 150}},
        }

        response = self.client.post("/v1/query", json={"question": "Show me all artists"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["summary"] == "Found 3 artists."
        self.mock_orchestrator.process_query.assert_called_once_with(
            "Show me all artists", conversation_history=None
        )

    def test_failed_query(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
            "metadata": {"stage": "parse", "timings": {"parse_ms": 50, "total_ms": 50}},
        }

        response = self.client.post("/v1/query", json={"question": "bad query"})

        assert response.status_code == 500
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Parse failed"

    def test_missing_question_returns_422(self):
        response = self.client.post("/v1/query", json={})
        assert response.status_code == 422

    def test_empty_question_is_accepted(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Empty query",
            "metadata": {"stage": "parse", "timings": {"total_ms": 0}},
        }

        response = self.client.post("/v1/query", json={"question": ""})
        assert response.status_code == 500


class TestQueryRequest:
    def test_valid_request(self):
        req = QueryRequest(question="Show me all artists")
        assert req.question == "Show me all artists"


class TestSessionEndpoints:
    def setup_method(self):
        import src.server as server_module
        from src.session import SessionManager
        self.mock_orchestrator = MagicMock()
        self._original_orchestrator = server_module.orchestrator
        server_module.orchestrator = self.mock_orchestrator
        self.session_manager = SessionManager(ttl_seconds=1800, max_turns=10)
        self._original_session_manager = server_module.session_manager
        server_module.session_manager = self.session_manager
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.orchestrator = self._original_orchestrator
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
        self.mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 users.",
            "error": None,
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        response = self.client.post(
            "/v1/query",
            json={"question": "show all users", "session_id": session_id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["success"] is True

    def test_query_with_unknown_session_returns_404(self):
        response = self.client.post(
            "/v1/query",
            json={"question": "show all users", "session_id": "nonexistent"},
        )
        assert response.status_code == 404

    def test_query_without_session_works_stateless(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 users.",
            "error": None,
        }
        response = self.client.post(
            "/v1/query",
            json={"question": "show all users"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" not in data or data.get("session_id") is None

    def test_successful_query_appends_turn_to_session(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 users.",
            "error": None,
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        self.client.post(
            "/v1/query",
            json={"question": "show all users", "session_id": session_id},
        )
        session = self.session_manager.get(session_id)
        assert len(session.turns) == 1
        assert session.turns[0].question == "show all users"
        assert session.turns[0].summary == "Found 3 users."

    def test_failed_query_does_not_append_turn(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        self.client.post(
            "/v1/query",
            json={"question": "bad query", "session_id": session_id},
        )
        session = self.session_manager.get(session_id)
        assert len(session.turns) == 0

    def test_query_passes_history_to_orchestrator(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Result.",
            "error": None,
        }
        create_resp = self.client.post("/v1/sessions")
        session_id = create_resp.json()["session_id"]
        self.client.post(
            "/v1/query",
            json={"question": "show all users", "session_id": session_id},
        )
        self.client.post(
            "/v1/query",
            json={"question": "filter by active", "session_id": session_id},
        )
        call_args = self.mock_orchestrator.process_query.call_args_list[1]
        assert call_args[0][0] == "filter by active"
        history = call_args[1]["conversation_history"]
        assert len(history) == 1
        assert history[0].question == "show all users"
