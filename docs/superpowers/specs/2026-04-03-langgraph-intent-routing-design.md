# LangGraph Intent Routing

## Problem

The current pipeline sends every user message straight to IR generation. When conversation history is included, the LLM sometimes responds conversationally instead of producing IR JSON — it has no way to distinguish between database queries and chat messages. Non-query messages (clarifications, greetings, schema questions) need a different path.

## Goal

Add a LangGraph-based routing layer that classifies user input as either a database query or a conversational message, then routes to the appropriate handler. The existing pipeline is unchanged — the graph wraps it.

## Graph Structure

```
                    ┌──────────────┐
                    │    START     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Router Node │
                    │  Classifies  │
                    │  query/chat  │
                    └──────┬───────┘
                           │
                ┌──────────┴──────────┐
                │ "query"             │ "chat"
         ┌──────▼───────┐     ┌──────▼───────┐
         │  Query Node  │     │  Chat Node   │
         │  Existing    │     │  LLM chat    │
         │  orchestrator│     │  response    │
         │  pipeline    │     │  (schema-    │
         └──────┬───────┘     │   aware)     │
                │             └──────┬───────┘
                └──────────┬─────────┘
                    ┌──────▼───────┐
                    │     END      │
                    └──────────────┘
```

## Nodes

### Router Node

Makes a lightweight LLM call using the existing `LLMClient` with a classification prompt. The prompt includes conversation history (if present) so the router can understand follow-up context.

Input: user input + conversation history.
Output: sets `intent` to `"query"` or `"chat"` on the graph state.

The classification prompt asks the LLM to respond with a single word: `query` or `chat`. The response is lowercased and stripped. If the response is not exactly one of those two values, default to `query` (safe fallback — the pipeline will attempt IR generation).

### Query Node

Calls `orchestrator.process_query(input, conversation_history=history)` exactly as today.

Input: user input + conversation history from graph state.
Output: sets `result` on the graph state with `{ type: "query", success, summary, error }`.

### Chat Node

Makes an LLM call with the database schema in its system prompt so it can answer questions like "what tables are available?" or "what columns does the users table have?". Conversation history is included for multi-turn coherence.

Input: user input + conversation history + schema context.
Output: sets `result` on the graph state with `{ type: "chat", success: true, message: "..." }`.

## Graph State

```python
class GraphState(TypedDict):
    input: str                                    # User's message
    conversation_history: Optional[list]           # Prior turns from session
    intent: Optional[str]                          # "query" or "chat" (set by router)
    result: Optional[dict]                         # Final response dict
```

## API Changes

### Request

Rename `question` to `input` in the request body:

```json
{ "input": "show me all users", "session_id": "abc-123" }
```

`QueryRequest` becomes:

```python
class QueryRequest(BaseModel):
    input: str
    session_id: Optional[str] = None
```

### Response

The response gains a `type` field indicating which path handled the request:

**Query response:**
```json
{
  "type": "query",
  "success": true,
  "summary": "Found 150 users across 3 departments.",
  "session_id": "abc-123"
}
```

**Chat response:**
```json
{
  "type": "chat",
  "success": true,
  "message": "The users table has 7 columns: id, name, email, age, status, tier, verified.",
  "session_id": "abc-123"
}
```

**Error response (query failure):**
```json
{
  "type": "query",
  "success": false,
  "error": "Parse failed",
  "session_id": "abc-123"
}
```

## Session History

Both query and chat turns are appended to session history so the router always has full conversation context:

- **Query turns:** `input` + `summary`
- **Chat turns:** `input` + `message`

The `ConversationTurn` dataclass is unchanged — it stores `question` and `summary` internally regardless of turn type.

## Server Changes

### Query Endpoint

The `/v1/query` endpoint calls the LangGraph graph instead of the orchestrator directly:

```python
@app.post("/v1/query")
async def query(request: QueryRequest):
    # ... session lookup (unchanged) ...

    result = await asyncio.to_thread(
        graph.invoke,
        {
            "input": request.input,
            "conversation_history": conversation_history,
        },
    )

    # ... session turn append + response (updated for type field) ...
```

### create_app

Initializes the graph with the orchestrator, LLM client, and schema:

```python
graph = create_graph(
    orchestrator=orchestrator,
    llm_client=llm_client,
    system_prompt=system_prompt,
)
```

## File Changes

| File | Action | Responsibility |
|------|--------|---------------|
| `src/graph.py` | Create | LangGraph graph definition, state, router/query/chat nodes |
| `src/server.py` | Modify | Call graph instead of orchestrator; rename `question` to `input` |
| `tests/test_graph.py` | Create | Unit tests for graph nodes and routing |
| `tests/test_server.py` | Modify | Update for `input` field and `type` in response |

## What Doesn't Change

- The pipeline stages (parse, validate, build, execute, summarize)
- `QueryOrchestrator` — called by query node as-is
- `SessionManager` and session endpoints (`/v1/sessions`)
- `LLMClient` interface
- `IRParser` and conversation history injection
- Stateless queries (no `session_id`) still work
