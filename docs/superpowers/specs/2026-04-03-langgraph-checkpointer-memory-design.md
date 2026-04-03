# LangGraph Checkpointer Memory Design

Replace the custom `SessionManager` with LangGraph's built-in checkpointer persistence, using `MessagesState` for idiomatic multi-turn conversation memory.

## Motivation

The current session system is a custom in-memory implementation (`src/session.py`) that manually tracks conversation turns, handles TTL expiry, and requires coordination across `SessionMiddleware`, `GraphState`, and `_build_history_context()`. LangGraph provides a built-in checkpointer mechanism that handles all of this natively, with a clear upgrade path to durable backends (PostgreSQL, Redis, MongoDB).

## Approach

**MessagesState with InMemorySaver checkpointer.** The graph state extends LangGraph's `MessagesState`, which provides a built-in `messages` list persisted automatically by the checkpointer. Graph nodes work with `HumanMessage`/`AIMessage` objects. The orchestrator interface is unchanged — graph nodes translate between messages and the orchestrator's expected format.

## Design

### Graph State

```python
from langgraph.graph import MessagesState

class GraphState(MessagesState):
    intent: Optional[str]
    result: Optional[dict]
```

`MessagesState` provides a `messages` list that the checkpointer persists per `thread_id`. The user's question arrives as a `HumanMessage`. Each node appends responses as `AIMessage` objects.

The `conversation_history` field and `_build_history_context()` helper are removed. Message history is in `state["messages"]` automatically.

### Checkpointer

`InMemorySaver` is created in `create_app()` and passed to `graph.compile(checkpointer=checkpointer)`:

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)
```

When the graph is invoked with a `thread_id` config, the checkpointer restores prior state (including all messages) and saves the new state after execution:

```python
graph.invoke(
    {"messages": [HumanMessage(content=user_input)]},
    config={"configurable": {"thread_id": session_id}},
)
```

Without a `thread_id`, the call is stateless (one-shot, no memory).

### Session Endpoints

The API contract is unchanged:

- `POST /v1/sessions` — generates and returns a UUID. No `Session` object needed; the checkpointer creates the thread implicitly on first query.
- `DELETE /v1/sessions/{session_id}` — removes the session ID from the known set.
- `POST /v1/query` with `session_id` — maps `session_id` to `thread_id` in the LangGraph config.

Session ID validation uses a simple `set` of known IDs in the server module, replacing the `SessionManager` class.

### SessionMiddleware

Stripped down to:

- Validate `session_id` if provided (check it exists in the known set).
- Return 404 if the session is unknown.
- Inject `session_id` into the response body after the call.
- Handle status code logic (200 vs 500 based on `result.success`).

No longer resolves conversation history or appends turns — the checkpointer handles both.

### Graph Nodes

**Router node:** Reads the latest message from `state["messages"]` (including prior conversation context from the checkpointer). Classifies intent.

**Query node:** Extracts conversation history from `state["messages"]` by pairing alternating `HumanMessage`/`AIMessage` entries. Passes them to `orchestrator.process_query(question, conversation_history)` in the existing format. Appends the summary as an `AIMessage`.

**Chat node:** Reads messages, generates a conversational response via LLM, appends as `AIMessage`.

### Orchestrator & Workflows

No changes. The orchestrator still receives `(natural_language, conversation_history=None)`. The graph node is the translation boundary between LangGraph messages and the orchestrator's interface.

`PipelineContext.conversation_history` type and usage remain the same.

## Files Changed

| File | Action |
|---|---|
| `src/graph.py` | Rewrite — `MessagesState`, new node logic, compile with checkpointer |
| `src/server.py` | Simplify — slim down `SessionMiddleware`, pass `thread_id` config, remove `SessionManager` usage |
| `src/session.py` | Delete |
| `src/orchestrator.py` | No change |
| `src/workflows/base.py` | No change |
| `src/workflows/parse.py` | No change |
| `tests/` | Update session and graph tests to match new behavior |

## Trade-offs

- **TTL expiry is lost.** `InMemorySaver` does not support TTL. Acceptable since sessions are already in-memory (lost on restart). Can add periodic cleanup or upgrade to `PostgresSaver` later.
- **Heavier state storage.** The checkpointer stores full graph state at every step, not just question/summary pairs. Acceptable for `InMemorySaver` and a reasonable trade-off for the simplification.
- **No new dependencies.** `InMemorySaver` ships with `langgraph` which is already installed.

## Future Upgrade Path

Swap `InMemorySaver` for `PostgresSaver` to get durable sessions that survive restarts. The change is a one-line swap in `create_app()` plus adding the `langgraph-checkpoint-postgres` package.
