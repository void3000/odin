# Streaming Responses Design

Stream pipeline progress and LLM summary tokens to the web UI via Server-Sent Events (SSE), giving the user real-time feedback as their query is processed.

## Motivation

Currently the user sees a typing indicator for the entire duration of the query (parse → validate → build → execute → summarize). With streaming, they see progress updates as each stage completes, then the summary types out token by token. This makes the interface feel responsive even on slow queries.

## Scope

- New `/chat/stream` SSE endpoint (additive — existing `/chat` stays)
- `LLMClient.generate_stream()` for token-by-token LLM output
- `ResultSummarizer.summarize_stream()` for streaming summarization
- `QueryOrchestrator.process_query_stream()` with callback for events
- Frontend `sendMessage()` updated to consume the SSE stream

**Out of scope:** Streaming for the `/v1/query` API endpoint, LangGraph native streaming, WebSocket support.

## SSE Event Protocol

Three event types sent from `/chat/stream`:

### status

Emitted when a pipeline stage starts. The frontend updates the transient indicator in-place.

```
event: status
data: {"stage": "parse", "message": "Parsing query..."}
```

Stages: `parse`, `validate`, `build`, `execute`, `summarize`.

### token

Emitted during summarization as the LLM generates tokens. The frontend appends each token to the assistant message.

```
event: token
data: {"content": "Found"}
```

### done

Signals the stream is complete.

```
event: done
data: {"success": true}
```

If the pipeline failed, a single `token` event with the friendly error message is sent before `done`.

## Backend Changes

### LLMClient.generate_stream()

New method on `src/llm_client.py`. Uses the OpenAI SDK's `stream=True` parameter:

```python
def generate_stream(self, system_prompt, user_message):
    response = self.client.chat.completions.create(
        model=self.model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=self.temperature,
        stream=True,
    )
    for chunk in response:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
```

Existing `generate()` is unchanged.

### ResultSummarizer.summarize_stream()

New method on `src/summarizer.py`. Takes the same inputs as `summarize()`, yields tokens instead of returning a complete string. Uses `LLMClient.generate_stream()` internally.

### QueryOrchestrator.process_query_stream()

New method on `src/orchestrator.py`. Takes a callback function `(event_type: str, data: dict) -> None`. Runs the same pipeline stages sequentially:

1. For each stage (parse, validate, build, execute): calls `callback("status", {"stage": name, "message": "..."})` before running the stage. If the stage fails, sends the friendly error as a `token` event and `done` with `success: False`.
2. For the summarize stage: calls `callback("status", ...)`, then uses `ResultSummarizer.summarize_stream()` and calls `callback("token", {"content": chunk})` for each token.
3. Calls `callback("done", {"success": True})` when complete.

Existing `process_query()` is unchanged.

### /chat/stream endpoint

New route in `src/web/routes.py`. Uses `FastAPI.StreamingResponse` with `text/event-stream` media type.

A `queue.Queue` bridges the sync pipeline thread and the async SSE generator:
- The pipeline runs in a thread via `asyncio.to_thread`, posting `(event_type, data)` tuples to the queue via the callback
- The async generator reads from the queue and yields SSE-formatted strings
- The callback posts a sentinel `None` to signal completion

The endpoint handles `session_id` the same way as `/chat` — maps it to `thread_id` in the LangGraph config for the graph invocation. However, for streaming, the orchestrator is called directly (not via `graph.invoke`) since the graph's `invoke` doesn't support the callback pattern. The checkpointer state is updated manually after streaming completes.

## Frontend Changes

`sendMessage()` in `index.html` switches from `fetch('/chat')` to `fetch('/chat/stream')`.

### Stream processing flow

1. User sends message, optimistic bubble + typing dots appear
2. `fetch('/chat/stream', {method: 'POST', body: formData})` starts
3. Read response via `response.body.getReader()` and `TextDecoder`
4. Parse SSE events from text chunks:
   - `status` → replace typing dots with status text
   - First `token` → replace status indicator with empty assistant message (Gemini-style with icon), append token
   - Subsequent `token` → append to assistant message content
   - `done` → run `marked.parse()` on the complete content for final markdown render
5. Refresh sidebar if in a session

### Markdown rendering

During token streaming, content is shown as plain text. Once `done` arrives, the full content is parsed as markdown in one pass. This avoids janky re-rendering on every token while still giving a smooth typing effect.

### Fallback

If the stream fails (network error), the typing indicator is replaced with a generic error message.

## Files Changed

| File | Action |
|---|---|
| `src/llm_client.py` | Modify — add `generate_stream()` method |
| `src/summarizer.py` | Modify — add `summarize_stream()` method |
| `src/orchestrator.py` | Modify — add `process_query_stream()` method |
| `src/web/routes.py` | Modify — add `/chat/stream` SSE endpoint |
| `src/web/templates/index.html` | Modify — switch `sendMessage()` to streaming fetch |

**Not changed:** `src/graph.py`, `src/server.py`, existing `/chat` endpoint, `/v1/query` API, workflows, CSS, other templates. The streaming path is entirely additive.
