# Multi-Turn Conversation Support

## Problem

Odin's query pipeline is fully stateless. Each `POST /v1/query` request creates a fresh `PipelineContext` and the LLM receives only a system prompt and the current question. Users cannot ask follow-up questions like "now group that by month" or "filter by active ones" because the LLM has no knowledge of prior interactions.

## Goal

Add session-based conversation history so that follow-up queries can reference prior turns. Existing stateless behavior must remain the default when no session is used.

## API Changes

### New Endpoints

**`POST /v1/sessions`**

Creates a new conversation session.

- Request body: none
- Response: `{ "session_id": "<uuid>" }`
- Status: `201 Created`

**`DELETE /v1/sessions/{session_id}`**

Explicitly ends a session and frees its memory.

- Response: `204 No Content`
- Unknown/expired session: `404 Not Found`

### Modified Endpoint

**`POST /v1/query`**

Add an optional `session_id` field to the request body.

```json
{
  "question": "filter by active ones",
  "session_id": "abc-123"
}
```

- If `session_id` is omitted or null: behaves exactly as today (stateless).
- If `session_id` is provided and valid: query runs with conversation history from that session.
- If `session_id` is provided but unknown/expired: returns `404` with error message.

After a successful query within a session, the turn (question + result summary) is appended to the session history.

## Session Store

### Data Model

```python
@dataclass
class ConversationTurn:
    question: str       # The natural language input
    summary: str        # The natural language result summary

@dataclass
class Session:
    session_id: str
    created_at: datetime
    last_accessed: datetime
    turns: list[ConversationTurn]
```

### Storage

In-memory `dict[str, Session]`. No database persistence. Sessions are lost on server restart.

### TTL

Sessions expire after 30 minutes of inactivity (measured from `last_accessed`). Expiry is checked lazily: when a session is accessed, its TTL is verified before use. Expired sessions are removed on access.

### Turn Window

The last 10 turns are included in the LLM prompt. Older turns within the session are retained in memory but not sent to the LLM.

## LLM Context Changes

### Parse Stage

When a query has an associated session with history, the parse stage augments the LLM prompt with prior conversation turns. The conversation history is injected into the user message, before the current question:

```
Previous conversation:
User: show me all users
Assistant: Found 150 users across 3 departments.

User: show me their email addresses
Assistant: Retrieved email addresses for all 150 users.

Current question: now filter by active ones
```

This gives the LLM enough context to resolve references ("that", "those", "it") and understand implicit filters or groupings.

### Summarize Stage

No changes. The summarize stage already receives the current query's SQL and results, which is sufficient context.

### LLMClient

No changes to `LLMClient.generate()` signature. The conversation history is composed into the prompt string before the call is made.

## Pipeline Changes

### PipelineContext

Add an optional field for conversation history:

```python
conversation_history: Optional[list[ConversationTurn]] = None
```

This is populated by the orchestrator before the pipeline runs when a session is active.

### Orchestrator

`QueryOrchestrator.process_query()` gains an optional `conversation_history` parameter. When provided, it sets `context.conversation_history` before running the pipeline. After a successful run, the orchestrator returns the turn data (question + summary) for the server to append to the session.

## What Doesn't Change

- Queries without a `session_id` behave identically to today.
- The validate, build, and execute pipeline stages are unaffected.
- The `LLMClient` interface is unchanged.
- Schema extraction and system prompt construction are unchanged.

## Error Handling

| Scenario | Response |
|----------|----------|
| Query with unknown `session_id` | `404 Not Found` with error message |
| Query with expired `session_id` | `404 Not Found` with error message |
| Delete unknown/expired session | `404 Not Found` |
| Session creation | No failure modes beyond server capacity |
| Pipeline failure within a session | Failed turns are not appended to history |
