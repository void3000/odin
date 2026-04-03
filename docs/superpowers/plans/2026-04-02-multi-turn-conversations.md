# Multi-Turn Conversation Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add session-based conversation history so follow-up queries can reference prior turns, while preserving existing stateless behavior.

**Architecture:** A new `SessionManager` class in `src/session.py` holds an in-memory dict of sessions. The server creates/deletes sessions via new endpoints and passes conversation history into the orchestrator. The parse stage injects history into the LLM prompt. Queries without a `session_id` behave identically to today.

**Tech Stack:** Python dataclasses, FastAPI, uuid, datetime, pytest, unittest.mock

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/session.py` | Create | `ConversationTurn`, `Session`, `SessionManager` classes |
| `tests/test_session.py` | Create | Unit tests for session manager |
| `src/workflows/base.py` | Modify | Add `conversation_history` field to `PipelineContext` |
| `src/workflows/parse.py` | Modify | Inject conversation history into parser call |
| `src/ir/parser.py` | Modify | Accept and format conversation history in LLM prompt |
| `tests/test_workflow_parse.py` | Modify | Test history injection |
| `src/orchestrator.py` | Modify | Accept and pass conversation history through pipeline |
| `tests/test_orchestrator_workflows.py` | Modify | Test orchestrator with history |
| `src/server.py` | Modify | Session endpoints, wire session manager to query flow |
| `tests/test_server.py` | Modify | Test session endpoints and session-aware queries |

---

### Task 1: Session Manager — Data Model and Core Logic

**Files:**
- Create: `src/session.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: Write failing tests for SessionManager**

```python
# tests/test_session.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.session'`

- [ ] **Step 3: Implement SessionManager**

```python
# src/session.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py -v`
Expected: All 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/session.py tests/test_session.py
git commit -m "feat: add SessionManager with TTL-based in-memory session store"
```

---

### Task 2: Add conversation_history to PipelineContext

**Files:**
- Modify: `src/workflows/base.py:14-32`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/test_workflow_base.py
from src.session import ConversationTurn

def test_pipeline_context_has_conversation_history():
    ctx = PipelineContext(
        natural_language="test",
        db_url="sqlite:///test.db",
        schema={},
        conversation_history=[
            ConversationTurn(question="q1", summary="s1"),
        ],
    )
    assert len(ctx.conversation_history) == 1
    assert ctx.conversation_history[0].question == "q1"

def test_pipeline_context_conversation_history_defaults_none():
    ctx = PipelineContext(
        natural_language="test",
        db_url="sqlite:///test.db",
        schema={},
    )
    assert ctx.conversation_history is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workflow_base.py::test_pipeline_context_has_conversation_history -v`
Expected: FAIL — `unexpected keyword argument 'conversation_history'`

- [ ] **Step 3: Add conversation_history field to PipelineContext**

In `src/workflows/base.py`, add to the `PipelineContext` dataclass after the `schema` field:

```python
    # Conversation history (for multi-turn sessions)
    conversation_history: Optional[List[Any]] = None
```

The full imports line becomes:
```python
from typing import Any, Dict, List, Optional
```

(Already correct — no import change needed.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_base.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/workflows/base.py tests/test_workflow_base.py
git commit -m "feat: add conversation_history field to PipelineContext"
```

---

### Task 3: IRParser accepts and formats conversation history

**Files:**
- Modify: `src/ir/parser.py:39-54`
- Modify: `tests/test_workflow_parse.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_workflow_parse.py
from src.session import ConversationTurn


class TestParseWorkflowWithHistory:
    def test_passes_conversation_history_to_parser(self):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"success": True, "data": _make_query_ir()}

        workflow = ParseWorkflow(mock_parser)
        ctx = _make_context()
        ctx.conversation_history = [
            ConversationTurn(question="show all users", summary="Found 150 users."),
        ]
        workflow.run(ctx)

        mock_parser.parse.assert_called_once_with(
            "Show me all users",
            conversation_history=ctx.conversation_history,
        )

    def test_passes_none_history_when_not_set(self):
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {"success": True, "data": _make_query_ir()}

        workflow = ParseWorkflow(mock_parser)
        ctx = _make_context()
        workflow.run(ctx)

        mock_parser.parse.assert_called_once_with(
            "Show me all users",
            conversation_history=None,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_parse.py::TestParseWorkflowWithHistory -v`
Expected: FAIL — `parse() got an unexpected keyword argument 'conversation_history'`

- [ ] **Step 3: Update ParseWorkflow to pass history**

In `src/workflows/parse.py`, update the `run` method:

```python
    def run(self, context: PipelineContext) -> PipelineContext:
        result = self.parser.parse(
            context.natural_language,
            conversation_history=context.conversation_history,
        )
        if not result["success"]:
            context.error = result["error"]
            context.failed_stage = self.name
            return context
        context.query_ir = result["data"]
        return context
```

- [ ] **Step 4: Update IRParser.parse to accept and format history**

In `src/ir/parser.py`, update the `parse` method signature and build the user message with history:

```python
    def parse(self, natural_language: str, conversation_history=None) -> Dict[str, Any]:
        """
        Parse a natural language query into IR.

        Args:
            natural_language: User's question in natural language
            conversation_history: Optional list of ConversationTurn for multi-turn context

        Returns:
            Dict with 'success' boolean and either 'data' (QueryIR) or 'error'
        """
        try:
            user_message = self._build_user_message(natural_language, conversation_history)

            success, response = self.llm_client.generate(
                system_prompt=self.system_prompt,
                user_message=user_message,
            )
            # ... rest unchanged
```

Add the helper method to `IRParser`:

```python
    def _build_user_message(self, natural_language: str, conversation_history=None) -> str:
        """Build the user message, optionally including conversation history."""
        if not conversation_history:
            return natural_language

        lines = ["Previous conversation:"]
        for turn in conversation_history:
            lines.append(f"User: {turn.question}")
            lines.append(f"Assistant: {turn.summary}")
            lines.append("")
        lines.append(f"Current question: {natural_language}")
        return "\n".join(lines)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_parse.py -v`
Expected: All tests PASS (including existing ones)

- [ ] **Step 6: Add unit test for _build_user_message**

```python
# Add to tests/test_workflow_parse.py
from src.ir.parser import IRParser


class TestBuildUserMessage:
    def setup_method(self):
        self.parser = IRParser(llm_client=MagicMock(), system_prompt="test")

    def test_no_history_returns_plain_question(self):
        result = self.parser._build_user_message("show all users", None)
        assert result == "show all users"

    def test_empty_history_returns_plain_question(self):
        result = self.parser._build_user_message("show all users", [])
        assert result == "show all users"

    def test_with_history_formats_conversation(self):
        history = [
            ConversationTurn(question="show all users", summary="Found 150 users."),
            ConversationTurn(question="filter by active", summary="42 active users."),
        ]
        result = self.parser._build_user_message("group by department", history)
        assert "Previous conversation:" in result
        assert "User: show all users" in result
        assert "Assistant: Found 150 users." in result
        assert "User: filter by active" in result
        assert "Assistant: 42 active users." in result
        assert "Current question: group by department" in result
```

- [ ] **Step 7: Run all parse tests**

Run: `pytest tests/test_workflow_parse.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/ir/parser.py src/workflows/parse.py tests/test_workflow_parse.py
git commit -m "feat: inject conversation history into LLM parse prompt"
```

---

### Task 4: Orchestrator passes conversation history

**Files:**
- Modify: `src/orchestrator.py:64-80`
- Modify: `tests/test_orchestrator_workflows.py`

- [ ] **Step 1: Read current orchestrator tests**

Run: `cat tests/test_orchestrator_workflows.py` (use Read tool)

- [ ] **Step 2: Write failing test**

```python
# Add to tests/test_orchestrator_workflows.py
from src.session import ConversationTurn


class TestOrchestratorWithHistory:
    def test_process_query_passes_history_to_context(self):
        """Verify conversation_history flows into PipelineContext."""
        mock_llm = MagicMock()
        orchestrator = QueryOrchestrator(
            db_url="sqlite:///test.db",
            llm_client=mock_llm,
            system_prompt="test",
            schema={"users": {"columns": {"id": {"type": "int"}}}},
        )

        history = [ConversationTurn(question="q1", summary="s1")]

        # Mock the first step to capture context
        captured_contexts = []
        original_execute = orchestrator.steps[0].execute

        def capture_execute(ctx):
            captured_contexts.append(ctx)
            ctx.error = "stop early"  # Stop pipeline after first step
            return ctx

        orchestrator.steps[0].execute = capture_execute
        orchestrator.process_query("test query", conversation_history=history)

        assert len(captured_contexts) == 1
        assert captured_contexts[0].conversation_history == history

    def test_process_query_without_history_defaults_none(self):
        mock_llm = MagicMock()
        orchestrator = QueryOrchestrator(
            db_url="sqlite:///test.db",
            llm_client=mock_llm,
            system_prompt="test",
            schema={"users": {"columns": {"id": {"type": "int"}}}},
        )

        captured_contexts = []
        def capture_execute(ctx):
            captured_contexts.append(ctx)
            ctx.error = "stop early"
            return ctx

        orchestrator.steps[0].execute = capture_execute
        orchestrator.process_query("test query")

        assert captured_contexts[0].conversation_history is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_orchestrator_workflows.py::TestOrchestratorWithHistory -v`
Expected: FAIL — `process_query() got an unexpected keyword argument 'conversation_history'`

- [ ] **Step 4: Update process_query to accept conversation_history**

In `src/orchestrator.py`, update `process_query`:

```python
    def process_query(self, natural_language: str, conversation_history=None) -> Dict[str, Any]:
        """Process a natural language query through the complete pipeline."""
        logger.info(f"Processing query: {natural_language}")

        context = PipelineContext(
            natural_language=natural_language,
            db_url=self.db_url,
            schema=self.schema,
            conversation_history=conversation_history,
        )

        for step in self.steps:
            context = step.execute(context)
            if context.error:
                break

        context.timings["total_ms"] = sum(context.timings.values())
        return self._to_result_dict(context)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator_workflows.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator_workflows.py
git commit -m "feat: orchestrator accepts and passes conversation history"
```

---

### Task 5: Server session endpoints and session-aware queries

**Files:**
- Modify: `src/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Write failing tests for session endpoints**

```python
# Add to tests/test_server.py
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

        # First query
        self.client.post(
            "/v1/query",
            json={"question": "show all users", "session_id": session_id},
        )

        # Second query — should pass history
        self.client.post(
            "/v1/query",
            json={"question": "filter by active", "session_id": session_id},
        )

        call_args = self.mock_orchestrator.process_query.call_args_list[1]
        assert call_args[0][0] == "filter by active"
        history = call_args[1]["conversation_history"]
        assert len(history) == 1
        assert history[0].question == "show all users"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_server.py::TestSessionEndpoints -v`
Expected: FAIL — session endpoints don't exist yet

- [ ] **Step 3: Update server.py with session support**

In `src/server.py`, add the session manager import and global, update `QueryRequest`, and add session endpoints:

Add import at top:
```python
from src.session import SessionManager
```

Add module-level variable next to `orchestrator`:
```python
session_manager: Optional[SessionManager] = None
```

Update `QueryRequest`:
```python
class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None
```

Add session endpoints:
```python
@app.post("/v1/sessions", status_code=201)
async def create_session():
    session = session_manager.create()
    return {"session_id": session.session_id}


@app.delete("/v1/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    if not session_manager.delete(session_id):
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found or expired"},
        )
```

Update the query endpoint:
```python
@app.post("/v1/query")
async def query(request: QueryRequest):
    conversation_history = None
    session_id = request.session_id

    if session_id:
        session = session_manager.get(session_id)
        if session is None:
            return JSONResponse(
                status_code=404,
                content={"error": "Session not found or expired"},
            )
        conversation_history = session_manager.get_history(session_id)

    result = await asyncio.to_thread(
        orchestrator.process_query,
        request.question,
        conversation_history=conversation_history,
    )

    if session_id and result.get("success"):
        session_manager.add_turn(
            session_id,
            question=request.question,
            summary=result.get("summary", ""),
        )

    if session_id:
        result["session_id"] = session_id

    status_code = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status_code)
```

Update `create_app` to initialize the session manager:
```python
def create_app(...) -> FastAPI:
    global orchestrator, session_manager

    # ... existing orchestrator setup ...

    session_manager = SessionManager()

    return app
```

- [ ] **Step 4: Update existing test_server.py tests for /v1/query path**

The existing `TestQueryEndpoint` tests use `/query` but the endpoint is at `/v1/query`. Update the test `setup_method` to also set the session_manager module variable, and update URL paths if needed to match the actual endpoint.

- [ ] **Step 5: Run all server tests**

Run: `pytest tests/test_server.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat: add session endpoints and session-aware query flow"
```

---

### Task 6: End-to-End Verification

**Files:**
- No new files — run full test suite

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify no regressions in existing tests**

Check that all pre-existing tests still pass. Pay special attention to:
- `tests/test_workflow_parse.py` — existing tests should still pass since `conversation_history` defaults to `None`
- `tests/test_server.py` — existing stateless query tests unchanged
- `tests/test_orchestrator_workflows.py` — existing tests pass with default `None` history

- [ ] **Step 3: Commit spec update**

```bash
git add docs/superpowers/specs/2026-04-01-multi-turn-conversations-design.md
git commit -m "docs: update spec with session_id in query response"
```
