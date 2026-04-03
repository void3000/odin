# LangGraph Intent Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a LangGraph routing layer that classifies user input as database query or chat, then routes to the existing orchestrator pipeline or a conversational LLM response.

**Architecture:** A three-node LangGraph `StateGraph` wraps the existing orchestrator. A router node classifies intent via a lightweight LLM call, then conditionally routes to a query node (existing pipeline) or chat node (schema-aware LLM conversation). The server calls the graph instead of the orchestrator directly, and the request field is renamed from `question` to `input`.

**Tech Stack:** LangGraph (`StateGraph`, `TypedDict`, `END`), existing `LLMClient`, existing `QueryOrchestrator`, pytest

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/graph.py` | Create | `GraphState` TypedDict, router/query/chat node functions, `create_graph()` factory |
| `tests/test_graph.py` | Create | Unit tests for each node and routing logic |
| `src/server.py` | Modify | Rename `question` to `input`, call graph instead of orchestrator, update session turn logic for chat type |
| `tests/test_server.py` | Modify | Update for `input` field, `type` in response, graph mock |

---

### Task 1: Graph Module — State and Node Functions

**Files:**
- Create: `src/graph.py`
- Create: `tests/test_graph.py`

- [ ] **Step 1: Write failing tests for router node**

```python
# tests/test_graph.py
from unittest.mock import MagicMock
from src.graph import GraphState, router_node, query_node, chat_node, create_graph


class TestRouterNode:
    def test_classifies_query_intent(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "query")

        state: GraphState = {
            "input": "show me all users",
            "conversation_history": None,
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_classifies_chat_intent(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "chat")

        state: GraphState = {
            "input": "hello, what can you do?",
            "conversation_history": None,
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "chat"

    def test_defaults_to_query_on_unexpected_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "I think this is a query about users")

        state: GraphState = {
            "input": "show me all users",
            "conversation_history": None,
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_defaults_to_query_on_llm_failure(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (False, "connection error")

        state: GraphState = {
            "input": "show me all users",
            "conversation_history": None,
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_includes_conversation_history_in_prompt(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "query")

        from src.session import ConversationTurn
        history = [ConversationTurn(question="show users", summary="Found 10 users.")]

        state: GraphState = {
            "input": "filter by active",
            "conversation_history": history,
            "intent": None,
            "result": None,
        }
        router_node(state, mock_llm)

        call_args = mock_llm.generate.call_args
        user_message = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][1]
        assert "show users" in user_message
        assert "filter by active" in user_message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_graph.py::TestRouterNode -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.graph'`

- [ ] **Step 3: Write failing tests for query node**

```python
# Add to tests/test_graph.py
class TestQueryNode:
    def test_calls_orchestrator_and_sets_result(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 users.",
            "error": None,
        }

        state: GraphState = {
            "input": "show me all users",
            "conversation_history": None,
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert result["result"]["type"] == "query"
        assert result["result"]["success"] is True
        assert result["result"]["summary"] == "Found 3 users."
        mock_orchestrator.process_query.assert_called_once_with(
            "show me all users", conversation_history=None,
        )

    def test_passes_conversation_history_to_orchestrator(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "42 active users.",
            "error": None,
        }

        from src.session import ConversationTurn
        history = [ConversationTurn(question="show users", summary="Found 10 users.")]

        state: GraphState = {
            "input": "filter by active",
            "conversation_history": history,
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        mock_orchestrator.process_query.assert_called_once_with(
            "filter by active", conversation_history=history,
        )

    def test_handles_orchestrator_failure(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
        }

        state: GraphState = {
            "input": "bad query",
            "conversation_history": None,
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert result["result"]["type"] == "query"
        assert result["result"]["success"] is False
        assert result["result"]["error"] == "Parse failed"
```

- [ ] **Step 4: Write failing tests for chat node**

```python
# Add to tests/test_graph.py
class TestChatNode:
    def test_generates_chat_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "The users table has columns: id, name, email.")

        state: GraphState = {
            "input": "what tables are available?",
            "conversation_history": None,
            "intent": "chat",
            "result": None,
        }
        result = chat_node(state, mock_llm, system_prompt="You are a helpful assistant.\nSchema: users(id, name)")
        assert result["result"]["type"] == "chat"
        assert result["result"]["success"] is True
        assert result["result"]["message"] == "The users table has columns: id, name, email."

    def test_handles_llm_failure(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (False, "connection error")

        state: GraphState = {
            "input": "hello",
            "conversation_history": None,
            "intent": "chat",
            "result": None,
        }
        result = chat_node(state, mock_llm, system_prompt="test")
        assert result["result"]["type"] == "chat"
        assert result["result"]["success"] is False
        assert "connection error" in result["result"]["error"]

    def test_includes_conversation_history(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "Sure, the active ones are...")

        from src.session import ConversationTurn
        history = [ConversationTurn(question="show users", summary="Found 10 users.")]

        state: GraphState = {
            "input": "which ones are active?",
            "conversation_history": history,
            "intent": "chat",
            "result": None,
        }
        chat_node(state, mock_llm, system_prompt="test")

        call_args = mock_llm.generate.call_args
        user_message = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][1]
        assert "show users" in user_message
        assert "which ones are active?" in user_message
```

- [ ] **Step 5: Write failing test for create_graph**

```python
# Add to tests/test_graph.py
class TestCreateGraph:
    def test_creates_compiled_graph(self):
        mock_llm = MagicMock()
        mock_orchestrator = MagicMock()
        graph = create_graph(
            orchestrator=mock_orchestrator,
            llm_client=mock_llm,
            system_prompt="test prompt",
        )
        assert graph is not None
        # Verify it's a compiled LangGraph (has invoke method)
        assert hasattr(graph, "invoke")
```

- [ ] **Step 6: Implement src/graph.py**

```python
# src/graph.py
"""
LangGraph Intent Routing.

Three-node graph that classifies user input as a database query or chat,
then routes to the appropriate handler.
"""

from typing import Any, Optional

from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict

from src.logging_config import get_component_logger

logger = get_component_logger("graph")

ROUTER_SYSTEM_PROMPT = """You are a request classifier. Your job is to determine if the user's message \
is a database query that needs SQL execution, or a conversational message.

Respond with exactly one word:
- "query" if the user wants to retrieve, filter, count, or analyze data from the database
- "chat" if the user is asking a general question, greeting, requesting clarification, \
or asking about the database schema/structure

Examples:
- "show me all users" -> query
- "how many orders last month" -> query
- "filter by active ones" -> query
- "hello" -> chat
- "what tables are available?" -> chat
- "thanks" -> chat
- "what does the status field mean?" -> chat"""

CHAT_SYSTEM_PROMPT_TEMPLATE = """You are a helpful data assistant. You can answer questions about the database \
schema, explain what data is available, and have general conversations.

{schema_context}

Rules:
- Be concise and helpful.
- When asked about tables or columns, reference the actual schema above.
- Do not make up data or pretend to query the database.
- Do not use emojis, special characters, or unicode symbols. Use only plain ASCII text."""


class GraphState(TypedDict):
    input: str
    conversation_history: Optional[list]
    intent: Optional[str]
    result: Optional[dict]


def _build_history_context(input_text: str, conversation_history) -> str:
    """Format conversation history + current input into a user message."""
    if not conversation_history:
        return input_text

    lines = ["Previous conversation:"]
    for turn in conversation_history:
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {turn.summary}")
        lines.append("")
    lines.append(f"Current message: {input_text}")
    return "\n".join(lines)


def router_node(state: GraphState, llm_client: Any) -> dict:
    """Classify intent as 'query' or 'chat'."""
    user_message = _build_history_context(state["input"], state.get("conversation_history"))

    success, response = llm_client.generate(
        system_prompt=ROUTER_SYSTEM_PROMPT,
        user_message=user_message,
    )

    intent = "query"  # safe default
    if success:
        cleaned = response.strip().lower()
        if cleaned in ("query", "chat"):
            intent = cleaned

    logger.info(f"Router classified intent as: {intent}")
    return {"intent": intent}


def query_node(state: GraphState, orchestrator: Any) -> dict:
    """Run the existing query pipeline via the orchestrator."""
    result = orchestrator.process_query(
        state["input"],
        conversation_history=state.get("conversation_history"),
    )
    result["type"] = "query"
    return {"result": result}


def chat_node(state: GraphState, llm_client: Any, system_prompt: str) -> dict:
    """Generate a conversational response."""
    user_message = _build_history_context(state["input"], state.get("conversation_history"))

    success, response = llm_client.generate(
        system_prompt=system_prompt,
        user_message=user_message,
    )

    if success:
        result = {"type": "chat", "success": True, "message": response}
    else:
        result = {"type": "chat", "success": False, "error": f"Chat generation failed: {response}"}

    return {"result": result}


def _route_by_intent(state: GraphState) -> str:
    """Conditional edge: route based on classified intent."""
    return state["intent"]


def create_graph(orchestrator: Any, llm_client: Any, system_prompt: str):
    """
    Build and compile the intent routing graph.

    Args:
        orchestrator: QueryOrchestrator instance for database queries.
        llm_client: LLMClient instance for router and chat nodes.
        system_prompt: System prompt containing schema context (used for chat node).
    """
    chat_system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(schema_context=system_prompt)

    graph = StateGraph(GraphState)

    graph.add_node("router", lambda state: router_node(state, llm_client))
    graph.add_node("query", lambda state: query_node(state, orchestrator))
    graph.add_node("chat", lambda state: chat_node(state, llm_client, chat_system_prompt))

    graph.set_entry_point("router")
    graph.add_conditional_edges("router", _route_by_intent, {"query": "query", "chat": "chat"})
    graph.add_edge("query", END)
    graph.add_edge("chat", END)

    return graph.compile()
```

- [ ] **Step 7: Run all graph tests**

Run: `.venv/bin/pytest tests/test_graph.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/graph.py tests/test_graph.py
git commit -m "feat: add LangGraph intent routing with router, query, and chat nodes"
```

---

### Task 2: Wire Graph Into Server and Rename `question` to `input`

**Files:**
- Modify: `src/server.py`
- Modify: `tests/test_server.py`

- [ ] **Step 1: Update server.py — imports, globals, QueryRequest**

In `src/server.py`, add the graph import:

```python
from src.graph import create_graph
```

Add a module-level `graph` variable alongside orchestrator and session_manager:

```python
orchestrator: Optional[QueryOrchestrator] = None
session_manager: Optional[SessionManager] = None
graph = None
```

Rename `question` to `input` in `QueryRequest`:

```python
class QueryRequest(BaseModel):
    input: str
    session_id: Optional[str] = None
```

- [ ] **Step 2: Update create_app to initialize the graph**

In `create_app`, add `graph` to the global declaration and initialize it after the orchestrator:

```python
def create_app(...) -> FastAPI:
    global orchestrator, session_manager, graph

    # ... existing schema_extractor, llm_client, orchestrator setup (unchanged) ...

    session_manager = SessionManager()

    graph = create_graph(
        orchestrator=orchestrator,
        llm_client=llm_client,
        system_prompt=system_prompt,
    )

    return app
```

- [ ] **Step 3: Update the query endpoint to call graph**

Replace the query endpoint with:

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

    graph_result = await asyncio.to_thread(
        graph.invoke,
        {
            "input": request.input,
            "conversation_history": conversation_history,
        },
    )

    result = graph_result["result"]

    if session_id and result.get("success"):
        summary = result.get("summary") or result.get("message", "")
        session_manager.add_turn(
            session_id,
            question=request.input,
            summary=summary,
        )

    if session_id:
        result["session_id"] = session_id

    status_code = 200 if result.get("success") else 500
    return JSONResponse(content=result, status_code=status_code)
```

- [ ] **Step 4: Update tests/test_server.py**

Replace the mock setup to mock the graph instead of orchestrator. Update all `question` references to `input`.

In `TestQueryEndpoint`:

```python
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
```

In `TestQueryRequest`:

```python
class TestQueryRequest:
    def test_valid_request(self):
        req = QueryRequest(input="Show me all artists")
        assert req.input == "Show me all artists"
```

In `TestSessionEndpoints`, update to mock graph instead of orchestrator, and replace all `"question"` keys with `"input"`:

```python
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
```

- [ ] **Step 5: Run all server tests**

Run: `.venv/bin/pytest tests/test_server.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/server.py tests/test_server.py
git commit -m "feat: wire LangGraph into server, rename question to input"
```

---

### Task 3: End-to-End Verification

**Files:**
- No new files

- [ ] **Step 1: Run all graph and server tests**

Run: `.venv/bin/pytest tests/test_graph.py tests/test_server.py tests/test_session.py tests/test_workflow_parse.py tests/test_workflow_base.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run full test suite to check for regressions**

Run: `.venv/bin/pytest tests/ --ignore=tests/test_ir_validator.py -v --tb=short`
Expected: Same pre-existing failures only. No new failures introduced.

- [ ] **Step 3: Commit plan**

```bash
git add docs/superpowers/plans/2026-04-03-langgraph-intent-routing.md
git commit -m "docs: add LangGraph intent routing implementation plan"
```
