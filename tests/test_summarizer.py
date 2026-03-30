"""Tests for ResultSummarizer."""

import pytest
from unittest.mock import MagicMock
from src.summarizer import ResultSummarizer


class TestResultSummarizer:
    """Tests for ResultSummarizer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_llm = MagicMock()
        self.summarizer = ResultSummarizer(self.mock_llm)

    def test_summarize_success(self):
        """Summarizer returns LLM-generated summary."""
        self.mock_llm.generate.return_value = (True, "There are 2 users: Alice and Bob.")

        success, summary = self.summarizer.summarize(
            question="Show me all users",
            results=[{"name": "Alice"}, {"name": "Bob"}],
            sql="SELECT name FROM users"
        )

        assert success is True
        assert summary == "There are 2 users: Alice and Bob."
        self.mock_llm.generate.assert_called_once()

    def test_summarize_empty_results(self):
        """Summarizer handles empty result sets via LLM."""
        self.mock_llm.generate.return_value = (True, "No users were found in the database.")

        success, summary = self.summarizer.summarize(
            question="Show me all users",
            results=[],
            sql="SELECT name FROM users"
        )

        assert success is True
        assert summary == "No users were found in the database."
        self.mock_llm.generate.assert_called_once()

    def test_summarize_llm_failure(self):
        """Summarizer propagates LLM errors."""
        self.mock_llm.generate.return_value = (False, "API rate limit exceeded")

        success, summary = self.summarizer.summarize(
            question="Show me all users",
            results=[{"name": "Alice"}],
            sql="SELECT name FROM users"
        )

        assert success is False
        assert summary == "API rate limit exceeded"

    def test_prompt_contains_question_and_results(self):
        """Summarizer prompt includes the original question and result data."""
        self.mock_llm.generate.return_value = (True, "Summary.")

        self.summarizer.summarize(
            question="How many orders?",
            results=[{"count": 42}],
            sql="SELECT COUNT(*) as count FROM orders"
        )

        call_args = self.mock_llm.generate.call_args
        system_prompt = call_args[0][0] if call_args[0] else call_args[1]["system_prompt"]
        user_message = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["user_message"]

        assert "How many orders?" in user_message
        assert "42" in user_message


from src.orchestrator import QueryOrchestrator


class TestOrchestratorSummarization:
    """Tests for summarization integration in QueryOrchestrator."""

    def setup_method(self):
        """Set up orchestrator with mocked components."""
        self.mock_llm = MagicMock()
        self.schema = {
            "users": {
                "columns": {"id": {"type": "INTEGER"}, "name": {"type": "TEXT"}},
                "primary_key": "id",
            }
        }

    def test_process_query_returns_summary(self, tmp_path):
        """Successful query returns summary instead of raw data."""
        db_path = str(tmp_path / "test.db")
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice')")
        conn.commit()
        conn.close()

        # First call: IR parsing, Second call: summarization
        self.mock_llm.generate.side_effect = [
            (True, '{"operation": "SELECT", "source": {"table": "users"}, "fields": [{"field": "name"}]}'),
            (True, "There is 1 user: Alice."),
        ]

        orchestrator = QueryOrchestrator(
            db_path=db_path,
            llm_client=self.mock_llm,
            system_prompt="parse",
            schema=self.schema,
        )

        result = orchestrator.process_query("Show me all users")

        assert result["success"] is True
        assert result["summary"] == "There is 1 user: Alice."
        assert "data" not in result

    def test_process_query_summarize_failure(self, tmp_path):
        """Summarization failure returns error with stage."""
        db_path = str(tmp_path / "test.db")
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice')")
        conn.commit()
        conn.close()

        self.mock_llm.generate.side_effect = [
            (True, '{"operation": "SELECT", "source": {"table": "users"}, "fields": [{"field": "name"}]}'),
            (False, "API error"),
        ]

        orchestrator = QueryOrchestrator(
            db_path=db_path,
            llm_client=self.mock_llm,
            system_prompt="parse",
            schema=self.schema,
        )

        result = orchestrator.process_query("Show me all users")

        assert result["success"] is False
        assert result["error"] == "API error"
        assert result["metadata"]["stage"] == "summarize"
