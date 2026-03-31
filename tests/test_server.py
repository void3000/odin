from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from src.server import app, QueryRequest


class TestQueryEndpoint:
    def setup_method(self):
        """Mock the orchestrator before each test."""
        import src.server as server_module
        self.mock_orchestrator = MagicMock()
        self._original = server_module.orchestrator
        server_module.orchestrator = self.mock_orchestrator
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.orchestrator = self._original

    def test_successful_query(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 artists.",
            "error": None,
            "metadata": {"stage": "complete", "timings": {"total_ms": 150}},
        }

        response = self.client.post("/query", json={"question": "Show me all artists"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["summary"] == "Found 3 artists."
        self.mock_orchestrator.process_query.assert_called_once_with("Show me all artists")

    def test_failed_query(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
            "metadata": {"stage": "parse", "timings": {"parse_ms": 50, "total_ms": 50}},
        }

        response = self.client.post("/query", json={"question": "bad query"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Parse failed"

    def test_missing_question_returns_422(self):
        response = self.client.post("/query", json={})
        assert response.status_code == 422

    def test_empty_question_is_accepted(self):
        self.mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Empty query",
            "metadata": {"stage": "parse", "timings": {"total_ms": 0}},
        }

        response = self.client.post("/query", json={"question": ""})
        assert response.status_code == 200


class TestQueryRequest:
    def test_valid_request(self):
        req = QueryRequest(question="Show me all artists")
        assert req.question == "Show me all artists"
