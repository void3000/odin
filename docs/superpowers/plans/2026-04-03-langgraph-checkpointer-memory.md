# LangGraph Checkpointer Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the custom `SessionManager` with LangGraph's built-in `InMemorySaver` checkpointer and `MessagesState` for idiomatic multi-turn conversation memory.

**Architecture:** The graph state extends `MessagesState` to get a built-in `messages` list persisted by the checkpointer per `thread_id`. Graph nodes translate between LangGraph messages and the orchestrator's existing interface. Session endpoints remain unchanged; `session.py` is deleted.

**Tech Stack:** LangGraph (`MessagesState`, `InMemorySaver`), `langchain-core` (`HumanMessage`, `AIMessage`)

---

### Task 1: Rewrite graph.py with MessagesState and checkpointer

**Files:**
- Modify: `src/graph.py`

- [ ] **Step 1: Write the failing tests for new GraphState and node signatures**

Create a new test file that tests the updated graph module. The key changes: `GraphState` extends `MessagesState`, nodes read from `messages` instead of `input`/`conversation_history`, and `create_graph` accepts a `checkpointer` parameter.

Create `tests/test_graph_checkpointer.py`:

```python
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from src.graph import GraphState, router_node, query_node, chat_node, create_graph


class TestRouterNode:
    def test_classifies_query_intent(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "query")

        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_classifies_chat_intent(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "chat")

        state: GraphState = {
            "messages": [HumanMessage(content="hello, what can you do?")],
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "chat"

    def test_defaults_to_query_on_unexpected_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "I think this is a query about users")

        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_defaults_to_query_on_llm_failure(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (False, "connection error")

        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_includes_conversation_history_in_prompt(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "query")

        state: GraphState = {
            "messages": [
                HumanMessage(content="show users"),
                AIMessage(content="Found 10 users."),
                HumanMessage(content="filter by active"),
            ],
            "intent": None,
            "result": None,
        }
        router_node(state, mock_llm)

        call_args = mock_llm.generate.call_args
        user_message = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][1]
        assert "show users" in user_message
        assert "filter by active" in user_message


class TestQueryNode:
    def test_calls_orchestrator_and_sets_result(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 users.",
            "error": None,
        }

        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
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

        state: GraphState = {
            "messages": [
                HumanMessage(content="show users"),
                AIMessage(content="Found 10 users."),
                HumanMessage(content="filter by active"),
            ],
            "intent": "query",
            "result": None,
        }
        query_node(state, mock_orchestrator)
        call_args = mock_orchestrator.process_query.call_args
        assert call_args[0][0] == "filter by active"
        history = call_args[1]["conversation_history"]
        assert len(history) == 1
        assert history[0].question == "show users"
        assert history[0].summary == "Found 10 users."

    def test_appends_ai_message_on_success(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 users.",
            "error": None,
        }

        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert result["messages"][0].content == "Found 3 users."

    def test_appends_ai_message_on_failure(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
        }

        state: GraphState = {
            "messages": [HumanMessage(content="bad query")],
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert "Parse failed" in result["messages"][0].content

    def test_handles_orchestrator_failure(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
        }

        state: GraphState = {
            "messages": [HumanMessage(content="bad query")],
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert result["result"]["type"] == "query"
        assert result["result"]["success"] is False
        assert result["result"]["error"] == "Parse failed"


class TestChatNode:
    def test_generates_chat_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "The users table has columns: id, name, email.")

        state: GraphState = {
            "messages": [HumanMessage(content="what tables are available?")],
            "intent": "chat",
            "result": None,
        }
        result = chat_node(state, mock_llm, system_prompt="You are a helpful assistant.\nSchema: users(id, name)")
        assert result["result"]["type"] == "chat"
        assert result["result"]["success"] is True
        assert result["result"]["message"] == "The users table has columns: id, name, email."

    def test_appends_ai_message(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "Hello! How can I help?")

        state: GraphState = {
            "messages": [HumanMessage(content="hello")],
            "intent": "chat",
            "result": None,
        }
        result = chat_node(state, mock_llm, system_prompt="test")
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert result["messages"][0].content == "Hello! How can I help?"

    def test_handles_llm_failure(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (False, "connection error")

        state: GraphState = {
            "messages": [HumanMessage(content="hello")],
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

        state: GraphState = {
            "messages": [
                HumanMessage(content="show users"),
                AIMessage(content="Found 10 users."),
                HumanMessage(content="which ones are active?"),
            ],
            "intent": "chat",
            "result": None,
        }
        chat_node(state, mock_llm, system_prompt="test")

        call_args = mock_llm.generate.call_args
        user_message = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][1]
        assert "show users" in user_message
        assert "which ones are active?" in user_message


class TestCreateGraph:
    def test_creates_compiled_graph_with_checkpointer(self):
        from langgraph.checkpoint.memory import InMemorySaver

        mock_llm = MagicMock()
        mock_orchestrator = MagicMock()
        checkpointer = InMemorySaver()
        graph = create_graph(
            orchestrator=mock_orchestrator,
            llm_client=mock_llm,
            system_prompt="test prompt",
            checkpointer=checkpointer,
        )
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_creates_graph_without_checkpointer(self):
        mock_llm = MagicMock()
        mock_orchestrator = MagicMock()
        graph = create_graph(
            orchestrator=mock_orchestrator,
            llm_client=mock_llm,
            system_prompt="test prompt",
        )
        assert graph is not None
        assert hasattr(graph, "invoke")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_graph_checkpointer.py -v`
Expected: FAIL — the current `GraphState` doesn't extend `MessagesState`, nodes expect `input`/`conversation_history` keys.

- [ ] **Step 3: Implement the new graph.py**

Rewrite `src/graph.py`:

```python
"""
LangGraph Intent Routing.

Three-node graph that classifies user input as a database query or chat,
then routes to the appropriate handler. Uses MessagesState for
checkpointer-backed conversation memory.
"""

from dataclasses import dataclass
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, MessagesState, END

from src.logging_config import get_component_logger

logger = get_component_logger("graph")

ROUTER_SYSTEM_PROMPT = """You are a request classifier. Your job is to determine if the user's message \
is a database query that needs SQL execution, or a conversational message.

Respond with exactly one word:
- "query" if the user wants to retrieve, filter, count, or analyze specific data stored in the database
- "chat" if the user is asking a general knowledge question, greeting, requesting clarification, \
asking about the database schema/structure, or asking about concepts/definitions

Key distinction: "query" means the answer requires running SQL against the database. \
"chat" means the answer can be given from general knowledge or schema information alone.

Examples:
- "show me all users" -> query
- "how many orders last month" -> query
- "filter by active ones" -> query
- "what is the total revenue" -> query
- "hello" -> chat
- "what tables are available?" -> chat
- "thanks" -> chat
- "what does the status field mean?" -> chat
- "what is rock music?" -> chat
- "explain what a genre is" -> chat
- "what columns does the users table have?" -> chat"""

CHAT_SYSTEM_PROMPT_TEMPLATE = """You are a helpful data assistant. You can answer questions about the database \
schema, explain what data is available, and have general conversations.

{schema_context}

Rules:
- Be concise and helpful.
- When asked about tables or columns, reference the actual schema above.
- Do not make up data or pretend to query the database.
- Do not use emojis, special characters, or unicode symbols. Use only plain ASCII text."""


class GraphState(MessagesState):
    intent: Optional[str]
    result: Optional[dict]


@dataclass
class ConversationTurn:
    """A question/summary pair extracted from message history for the orchestrator."""
    question: str
    summary: str


def _extract_history(messages: list) -> tuple[str, list[ConversationTurn] | None]:
    """Extract the current question and conversation history from messages.

    Returns:
        (current_question, history) where history is None if there are no prior turns.
    """
    if not messages:
        return "", None

    current_question = messages[-1].content if messages else ""

    history = []
    # Pair up prior HumanMessage/AIMessage as conversation turns
    prior = messages[:-1]
    i = 0
    while i < len(prior) - 1:
        if isinstance(prior[i], HumanMessage) and isinstance(prior[i + 1], AIMessage):
            history.append(ConversationTurn(
                question=prior[i].content,
                summary=prior[i + 1].content,
            ))
            i += 2
        else:
            i += 1

    return current_question, history if history else None


def _build_history_context(messages: list) -> str:
    """Format message history into a user message string for the LLM."""
    current_question, history = _extract_history(messages)

    if not history:
        return current_question

    lines = ["Previous conversation:"]
    for turn in history:
        lines.append(f"User: {turn.question}")
        lines.append(f"Assistant: {turn.summary}")
        lines.append("")
    lines.append(f"Current message: {current_question}")
    return "\n".join(lines)


def router_node(state: GraphState, llm_client: Any) -> dict:
    """Classify intent as 'query' or 'chat'."""
    user_message = _build_history_context(state["messages"])

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
    current_question, history = _extract_history(state["messages"])

    result = orchestrator.process_query(
        current_question,
        conversation_history=history,
    )
    result["type"] = "query"

    # Append AI message so the checkpointer persists it for future turns
    summary = result.get("summary") or result.get("error", "")
    return {"result": result, "messages": [AIMessage(content=summary)]}


def chat_node(state: GraphState, llm_client: Any, system_prompt: str) -> dict:
    """Generate a conversational response."""
    user_message = _build_history_context(state["messages"])

    success, response = llm_client.generate(
        system_prompt=system_prompt,
        user_message=user_message,
    )

    if success:
        result = {"type": "chat", "success": True, "message": response}
    else:
        result = {"type": "chat", "success": False, "error": f"Chat generation failed: {response}"}

    # Append AI message for checkpointer persistence
    ai_content = response if success else f"Chat generation failed: {response}"
    return {"result": result, "messages": [AIMessage(content=ai_content)]}


def _route_by_intent(state: GraphState) -> str:
    """Conditional edge: route based on classified intent."""
    return state["intent"]


def create_graph(orchestrator: Any, llm_client: Any, system_prompt: str, checkpointer=None):
    """
    Build and compile the intent routing graph.

    Args:
        orchestrator: QueryOrchestrator instance for database queries.
        llm_client: LLMClient instance for router and chat nodes.
        system_prompt: System prompt containing schema context (used for chat node).
        checkpointer: Optional LangGraph checkpointer for conversation persistence.
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

    return graph.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest tests/test_graph_checkpointer.py -v`
Expected: All 18 tests PASS.

- [ ] **Step 5: Delete old graph tests and commit**

```bash
rm tests/test_graph.py
git add src/graph.py tests/test_graph_checkpointer.py tests/test_graph.py
git commit -m "feat: rewrite graph with MessagesState and checkpointer support"
```

---

### Task 2: Update server.py to use checkpointer instead of SessionManager

**Files:**
- Modify: `src/server.py`

- [ ] **Step 1: Write the failing tests for the updated server**

Create `tests/test_server_checkpointer.py`:

```python
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
        # First arg is the input dict with messages
        input_dict = call_args[0][0]
        assert isinstance(input_dict["messages"][0], HumanMessage)
        assert input_dict["messages"][0].content == "show all users"
        # Second arg is the config with thread_id
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
        # No config passed for stateless queries
        if len(call_args[0]) > 1:
            assert call_args[0][1] is None
        else:
            config = call_args[1].get("config")
            assert config is None
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `pytest tests/test_server_checkpointer.py -v`
Expected: FAIL — server still imports `SessionManager`, uses old graph invoke signature.

- [ ] **Step 3: Implement the updated server.py**

Rewrite `src/server.py`:

```python
"""
Odin FastAPI Server.

Exposes the query pipeline as a REST endpoint.
The orchestrator runs query processing in a thread to avoid blocking the event loop.
"""

import asyncio
import json
import logging
import time
import uuid
import uvicorn
from typing import Optional, Set

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings_from_cli
from src.db import create_schema_extractor
from src.llm_client import LLMClient
from src.llm.nl_to_ir import NaturalLanguageToIR
from src.orchestrator import QueryOrchestrator
from src.graph import create_graph
from src.logging_config import get_component_logger, get_uvicorn_log_config, request_id_var, setup_logging

logger = get_component_logger("server")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns a unique request ID and logs request lifecycle."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)

        logger.info(f"{request.method} {request.url.path}")
        start = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(f"{request.method} {request.url.path} → {response.status_code} ({elapsed_ms:.0f}ms)")

        response.headers["X-Request-ID"] = request_id
        return response


orchestrator: Optional[QueryOrchestrator] = None
sessions: Set[str] = set()
graph = None


class QueryRequest(BaseModel):
    input: str
    session_id: Optional[str] = None


class SessionMiddleware(BaseHTTPMiddleware):
    """Handles session validation and response enrichment on /v1/query.

    Before: validates session_id exists in known sessions set.
    After: injects session_id into response body, sets status code.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path != "/v1/query" or request.method != "POST":
            return await call_next(request)

        body_bytes = await request.body()
        try:
            body = json.loads(body_bytes)
        except (json.JSONDecodeError, ValueError):
            return await call_next(request)

        session_id = body.get("session_id")

        # Validate session exists
        if session_id and session_id not in sessions:
            return JSONResponse(
                status_code=404,
                content={"error": "Session not found or expired"},
            )

        request.state.session_id = session_id

        response = await call_next(request)

        # Read response body
        response_body = b""
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                response_body += chunk.encode()
            else:
                response_body += chunk

        try:
            result = json.loads(response_body)
        except (json.JSONDecodeError, ValueError):
            return Response(content=response_body, status_code=response.status_code,
                            headers=dict(response.headers), media_type=response.media_type)

        # Inject session_id into response
        if session_id:
            result["session_id"] = session_id

        # Set status code based on result
        if "type" in result:
            status_code = 200 if result.get("success") else 500
        else:
            status_code = response.status_code
        return JSONResponse(content=result, status_code=status_code)


app = FastAPI(title="Odin", description="LLM-to-SQL Pipeline")
app.add_middleware(SessionMiddleware)
app.add_middleware(RequestIdMiddleware)


def create_app(
    db_url: str,
    llm_base_url: str = "http://localhost:1234/v1",
    llm_api_key: str = "lmstudio",
    llm_model: str = "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
    temperature: float = 0.1,
    default_limit: int = 100,
) -> FastAPI:
    """Create and configure the FastAPI app with an orchestrator.

    Accepts individual parameters for backwards compatibility.
    Prefer create_app_from_settings() for new code.
    """
    global orchestrator, sessions, graph

    schema_extractor = create_schema_extractor(db_url)
    schema = schema_extractor.extract_schema()
    search_path = getattr(schema_extractor, "schemas", None)

    llm_client = LLMClient(
        base_url=llm_base_url,
        api_key=llm_api_key,
        model=llm_model,
        temperature=temperature,
    )

    nl_converter = NaturalLanguageToIR(api_key=llm_api_key)
    system_prompt = nl_converter._build_system_prompt(schema)

    validator_schema = {
        table.name: {
            "columns": {col.name: {"type": col.type} for col in table.columns}
        }
        for table in schema.tables
    }

    orchestrator = QueryOrchestrator(
        db_url=db_url,
        llm_client=llm_client,
        system_prompt=system_prompt,
        schema=validator_schema,
        default_limit=default_limit,
        search_path=search_path,
    )

    sessions = set()

    checkpointer = InMemorySaver()
    graph = create_graph(
        orchestrator=orchestrator,
        llm_client=llm_client,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )

    return app


def create_app_from_settings(settings) -> FastAPI:
    """Create and configure the FastAPI app from a ServerSettings instance."""
    return create_app(
        db_url=settings.db,
        llm_base_url=settings.llm_url,
        llm_api_key=settings.llm_key,
        llm_model=settings.llm_model,
        temperature=settings.temperature,
        default_limit=settings.default_limit,
    )


@app.post("/v1/sessions", status_code=201)
async def create_session():
    session_id = str(uuid.uuid4())
    sessions.add(session_id)
    return {"session_id": session_id}


@app.delete("/v1/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    if session_id not in sessions:
        return JSONResponse(
            status_code=404,
            content={"error": "Session not found or expired"},
        )
    sessions.discard(session_id)


@app.post("/v1/query")
async def query(request: Request, body: QueryRequest):
    session_id = getattr(request.state, "session_id", None)

    config = None
    if session_id:
        config = {"configurable": {"thread_id": session_id}}

    graph_result = await asyncio.to_thread(
        graph.invoke,
        {"messages": [HumanMessage(content=body.input)]},
        config,
    )

    return graph_result["result"]


if __name__ == "__main__":
    settings = settings_from_cli()
    setup_logging(
        log_level=logging.getLevelName(settings.log_level.upper()),
        log_file=settings.log_file,
    )
    create_app_from_settings(settings)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_config=get_uvicorn_log_config(log_file=settings.log_file),
    )
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `pytest tests/test_server_checkpointer.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Delete old server tests and commit**

```bash
rm tests/test_server.py
git add src/server.py tests/test_server_checkpointer.py tests/test_server.py
git commit -m "feat: replace SessionManager with checkpointer in server"
```

---

### Task 3: Delete session.py and clean up old test file

**Files:**
- Delete: `src/session.py`
- Delete: `tests/test_session.py`

- [ ] **Step 1: Verify no remaining imports of session module**

Run: `grep -r "from src.session" src/ tests/`
Expected: No matches (all references were removed in Tasks 1 and 2).

- [ ] **Step 2: Delete session.py and its tests**

```bash
rm src/session.py tests/test_session.py
```

- [ ] **Step 3: Run full test suite**

Run: `pytest -v`
Expected: All tests pass. No import errors.

- [ ] **Step 4: Commit**

```bash
git add src/session.py tests/test_session.py
git commit -m "refactor: delete session.py, replaced by LangGraph checkpointer"
```

---

### Task 4: Rename test files and run final verification

**Files:**
- Rename: `tests/test_graph_checkpointer.py` → `tests/test_graph.py`
- Rename: `tests/test_server_checkpointer.py` → `tests/test_server.py`

- [ ] **Step 1: Rename test files to their original names**

```bash
mv tests/test_graph_checkpointer.py tests/test_graph.py
mv tests/test_server_checkpointer.py tests/test_server.py
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_graph_checkpointer.py tests/test_server_checkpointer.py tests/test_graph.py tests/test_server.py
git commit -m "refactor: rename checkpointer test files to standard names"
```
