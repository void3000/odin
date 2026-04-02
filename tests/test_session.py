import time
from unittest.mock import patch
from src.session import SessionManager, Session, ConversationTurn


class TestSessionManager:
    def setup_method(self):
        self.manager = SessionManager(ttl_seconds=1800, max_turns=10)

    def test_create_returns_session_with_uuid(self):
        session = self.manager.create()
        assert isinstance(session, Session)
        assert len(session.session_id) == 36  # UUID format
        assert session.turns == []

    def test_get_returns_created_session(self):
        session = self.manager.create()
        retrieved = self.manager.get(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id

    def test_get_unknown_session_returns_none(self):
        result = self.manager.get("nonexistent-id")
        assert result is None

    def test_delete_removes_session(self):
        session = self.manager.create()
        deleted = self.manager.delete(session.session_id)
        assert deleted is True
        assert self.manager.get(session.session_id) is None

    def test_delete_unknown_returns_false(self):
        assert self.manager.delete("nonexistent-id") is False

    def test_add_turn_appends_to_session(self):
        session = self.manager.create()
        self.manager.add_turn(
            session.session_id,
            question="show all users",
            summary="Found 150 users.",
        )
        retrieved = self.manager.get(session.session_id)
        assert len(retrieved.turns) == 1
        assert retrieved.turns[0].question == "show all users"
        assert retrieved.turns[0].summary == "Found 150 users."

    def test_get_history_returns_last_n_turns(self):
        manager = SessionManager(ttl_seconds=1800, max_turns=2)
        session = manager.create()
        for i in range(5):
            manager.add_turn(session.session_id, f"q{i}", f"s{i}")
        history = manager.get_history(session.session_id)
        assert len(history) == 2
        assert history[0].question == "q3"
        assert history[1].question == "q4"

    def test_get_history_unknown_session_returns_empty(self):
        assert self.manager.get_history("nonexistent") == []


class TestSessionTTL:
    def test_expired_session_returns_none(self):
        manager = SessionManager(ttl_seconds=0)
        session = manager.create()
        time.sleep(0.01)
        assert manager.get(session.session_id) is None

    def test_access_updates_last_accessed(self):
        manager = SessionManager(ttl_seconds=1800)
        session = manager.create()
        original_time = session.last_accessed
        time.sleep(0.01)
        retrieved = manager.get(session.session_id)
        assert retrieved.last_accessed > original_time
