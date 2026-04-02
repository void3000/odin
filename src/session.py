"""
Session Manager.

In-memory session store for multi-turn conversation history.
Sessions expire after a configurable TTL of inactivity.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.logging_config import get_component_logger

logger = get_component_logger("session")


@dataclass
class ConversationTurn:
    """A single question/answer pair in a conversation."""
    question: str
    summary: str


@dataclass
class Session:
    """A conversation session with history."""
    session_id: str
    created_at: datetime
    last_accessed: datetime
    turns: List[ConversationTurn] = field(default_factory=list)


class SessionManager:
    """
    In-memory session store with TTL-based expiry.

    Sessions are checked lazily on access — no background thread.
    """

    def __init__(self, ttl_seconds: int = 1800, max_turns: int = 10):
        self._sessions: Dict[str, Session] = {}
        self._ttl_seconds = ttl_seconds
        self._max_turns = max_turns
        logger.info(f"SessionManager initialized (TTL={ttl_seconds}s, max_turns={max_turns})")

    def create(self) -> Session:
        """Create a new session and return it."""
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        session = Session(session_id=session_id, created_at=now, last_accessed=now)
        self._sessions[session_id] = session
        logger.info(f"Session created: {session_id}")
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """Get a session by ID. Returns None if not found or expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if self._is_expired(session):
            del self._sessions[session_id]
            logger.info(f"Session expired and removed: {session_id}")
            return None
        session.last_accessed = datetime.now(timezone.utc)
        return session

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Session deleted: {session_id}")
            return True
        return False

    def add_turn(self, session_id: str, question: str, summary: str) -> None:
        """Append a conversation turn to a session."""
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.turns.append(ConversationTurn(question=question, summary=summary))

    def get_history(self, session_id: str) -> List[ConversationTurn]:
        """Get the last N turns for a session (bounded by max_turns)."""
        session = self._sessions.get(session_id)
        if session is None:
            return []
        return session.turns[-self._max_turns:]

    def _is_expired(self, session: Session) -> bool:
        elapsed = (datetime.now(timezone.utc) - session.last_accessed).total_seconds()
        return elapsed > self._ttl_seconds
