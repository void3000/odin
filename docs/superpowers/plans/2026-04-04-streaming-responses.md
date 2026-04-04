# Streaming Responses Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream pipeline progress and LLM summary tokens to the web UI via Server-Sent Events so users see real-time feedback.

**Architecture:** A new `/chat/stream` SSE endpoint runs the pipeline in a thread, posting status and token events to a queue. The frontend reads the stream via `fetch()` + `ReadableStream`, updating the UI in-place. The existing `/chat` endpoint stays unchanged.

**Tech Stack:** FastAPI `StreamingResponse`, OpenAI SDK `stream=True`, SSE protocol, JavaScript `ReadableStream`

---

### Task 1: Add generate_stream() to LLMClient

**Files:**
- Modify: `src/llm_client.py`
- Test: `tests/test_llm_client_stream.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_llm_client_stream.py`:

```python
from unittest.mock import MagicMock, patch
from src.llm_client import LLMClient


class TestGenerateStream:
    def setup_method(self):
        with patch("src.llm_client.OpenAI"):
            self.client = LLMClient(base_url="http://localhost:1234/v1", api_key="test")

    def test_yields_content_tokens(self):
        # Mock streaming response
        chunk1 = MagicMock()
        chunk1.choices = [MagicMock()]
        chunk1.choices[0].delta.content = "Hello"

        chunk2 = MagicMock()
        chunk2.choices = [MagicMock()]
        chunk2.choices[0].delta.content = " world"

        chunk3 = MagicMock()
        chunk3.choices = [MagicMock()]
        chunk3.choices[0].delta.content = None

        self.client.client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])

        tokens = list(self.client.generate_stream("system", "user"))
        assert tokens == ["Hello", " world"]

    def test_handles_empty_stream(self):
        self.client.client.chat.completions.create.return_value = iter([])
        tokens = list(self.client.generate_stream("system", "user"))
        assert tokens == []

    def test_passes_stream_true(self):
        self.client.client.chat.completions.create.return_value = iter([])
        list(self.client.generate_stream("system prompt", "user message"))

        call_kwargs = self.client.client.chat.completions.create.call_args[1]
        assert call_kwargs["stream"] is True
        assert call_kwargs["model"] == self.client.model
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm_client_stream.py -v`
Expected: FAIL — `generate_stream` not found.

- [ ] **Step 3: Add generate_stream() to LLMClient**

Add this method to the `LLMClient` class in `src/llm_client.py`, after the `generate()` method:

```python
    def generate_stream(self, system_prompt: str, user_message: str):
        """
        Stream a response from the LLM token by token.

        Args:
            system_prompt: System message providing context
            user_message: User's question or request

        Yields:
            Content string tokens as they arrive
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=self.temperature,
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm_client_stream.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_client.py tests/test_llm_client_stream.py
git commit -m "feat: add generate_stream() for token-by-token LLM output"
```

---

### Task 2: Add summarize_stream() to ResultSummarizer

**Files:**
- Modify: `src/summarizer.py`
- Test: `tests/test_summarizer_stream.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_summarizer_stream.py`:

```python
from unittest.mock import MagicMock
from src.summarizer import ResultSummarizer


class TestSummarizeStream:
    def test_yields_tokens_from_llm(self):
        mock_llm = MagicMock()
        mock_llm.generate_stream.return_value = iter(["Found ", "3 ", "artists."])

        summarizer = ResultSummarizer(mock_llm)
        tokens = list(summarizer.summarize_stream(
            question="show artists",
            results=[{"name": "AC/DC"}, {"name": "Metallica"}, {"name": "Nirvana"}],
            sql="SELECT name FROM artist",
        ))

        assert tokens == ["Found ", "3 ", "artists."]
        mock_llm.generate_stream.assert_called_once()

    def test_passes_correct_prompt(self):
        mock_llm = MagicMock()
        mock_llm.generate_stream.return_value = iter(["ok"])

        summarizer = ResultSummarizer(mock_llm)
        list(summarizer.summarize_stream(
            question="show artists",
            results=[{"name": "AC/DC"}],
            sql="SELECT name FROM artist",
        ))

        call_args = mock_llm.generate_stream.call_args
        system_prompt = call_args[0][0]
        user_message = call_args[0][1]
        assert "data analyst" in system_prompt.lower()
        assert "show artists" in user_message
        assert "AC/DC" in user_message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_summarizer_stream.py -v`
Expected: FAIL — `summarize_stream` not found.

- [ ] **Step 3: Add summarize_stream() to ResultSummarizer**

Add this method to `ResultSummarizer` in `src/summarizer.py`, after the `summarize()` method:

```python
    def summarize_stream(
        self,
        question: str,
        results: List[Any],
        sql: str
    ):
        """
        Stream a summary of query results token by token.

        Args:
            question: The original natural language question.
            results: List of result rows.
            sql: The SQL query that was executed.

        Yields:
            Content string tokens as they arrive from the LLM.
        """
        user_message = (
            f"User's question: {question}\n\n"
            f"SQL executed: {sql}\n\n"
            f"Results ({len(results)} rows):\n{json.dumps(results, indent=2, default=str)}"
        )

        logger.debug(f"Streaming summary for {len(results)} rows")
        yield from self.llm_client.generate_stream(SUMMARIZE_SYSTEM_PROMPT, user_message)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_summarizer_stream.py -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/summarizer.py tests/test_summarizer_stream.py
git commit -m "feat: add summarize_stream() for token-by-token summarization"
```

---

### Task 3: Add process_query_stream() to QueryOrchestrator

**Files:**
- Modify: `src/orchestrator.py`
- Test: `tests/test_orchestrator_stream.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_orchestrator_stream.py`:

```python
from unittest.mock import MagicMock
from src.orchestrator import QueryOrchestrator


class TestProcessQueryStream:
    def setup_method(self):
        self.mock_source = MagicMock()
        self.mock_source.name = "test_db"
        self.mock_source.source_type = "database"

        self.mock_llm = MagicMock()
        # Parse returns valid IR JSON
        self.mock_llm.generate.return_value = (
            True,
            '{"operation": "SELECT", "source": {"table": "users"}, "fields": [{"field": "*"}]}'
        )

        self.schema = {
            "users": {"columns": {"id": {"type": "int"}, "name": {"type": "str"}}}
        }

    def test_emits_status_events_for_each_stage(self):
        mock_native = MagicMock()
        mock_native.sql = "SELECT * FROM users"
        mock_native.params = []
        self.mock_source.build_query.return_value = mock_native
        self.mock_source.is_connected.return_value = False

        from src.sources.base import QueryResult
        self.mock_source.execute.return_value = QueryResult(
            rows=[{"id": 1}], columns=["id"], row_count=1, source_name="test_db",
        )

        # Streaming summarizer
        self.mock_llm.generate_stream = MagicMock(return_value=iter(["Found ", "1 user."]))

        orchestrator = QueryOrchestrator(
            source=self.mock_source,
            llm_client=self.mock_llm,
            system_prompt="test",
            schema=self.schema,
        )

        events = []
        orchestrator.process_query_stream("show users", callback=lambda t, d: events.append((t, d)))

        status_events = [(t, d) for t, d in events if t == "status"]
        assert len(status_events) >= 4  # parse, validate, build, execute, summarize
        stages = [d["stage"] for _, d in status_events]
        assert "parse" in stages
        assert "execute" in stages
        assert "summarize" in stages

    def test_emits_token_events_during_summarization(self):
        mock_native = MagicMock()
        mock_native.sql = "SELECT * FROM users"
        mock_native.params = []
        self.mock_source.build_query.return_value = mock_native
        self.mock_source.is_connected.return_value = False

        from src.sources.base import QueryResult
        self.mock_source.execute.return_value = QueryResult(
            rows=[{"id": 1}], columns=["id"], row_count=1, source_name="test_db",
        )

        self.mock_llm.generate_stream = MagicMock(return_value=iter(["Found ", "1 user."]))

        orchestrator = QueryOrchestrator(
            source=self.mock_source,
            llm_client=self.mock_llm,
            system_prompt="test",
            schema=self.schema,
        )

        events = []
        orchestrator.process_query_stream("show users", callback=lambda t, d: events.append((t, d)))

        token_events = [(t, d) for t, d in events if t == "token"]
        assert len(token_events) == 2
        assert token_events[0][1]["content"] == "Found "
        assert token_events[1][1]["content"] == "1 user."

    def test_emits_done_event(self):
        mock_native = MagicMock()
        mock_native.sql = "SELECT * FROM users"
        mock_native.params = []
        self.mock_source.build_query.return_value = mock_native
        self.mock_source.is_connected.return_value = False

        from src.sources.base import QueryResult
        self.mock_source.execute.return_value = QueryResult(
            rows=[], columns=[], row_count=0, source_name="test_db",
        )

        self.mock_llm.generate_stream = MagicMock(return_value=iter(["No results."]))

        orchestrator = QueryOrchestrator(
            source=self.mock_source,
            llm_client=self.mock_llm,
            system_prompt="test",
            schema=self.schema,
        )

        events = []
        orchestrator.process_query_stream("show users", callback=lambda t, d: events.append((t, d)))

        done_events = [(t, d) for t, d in events if t == "done"]
        assert len(done_events) == 1
        assert done_events[0][1]["success"] is True

    def test_emits_error_on_parse_failure(self):
        self.mock_llm.generate.return_value = (True, "INSERT is not supported")

        orchestrator = QueryOrchestrator(
            source=self.mock_source,
            llm_client=self.mock_llm,
            system_prompt="test",
            schema=self.schema,
        )

        events = []
        orchestrator.process_query_stream("insert a user", callback=lambda t, d: events.append((t, d)))

        token_events = [(t, d) for t, d in events if t == "token"]
        assert len(token_events) >= 1  # error message as token

        done_events = [(t, d) for t, d in events if t == "done"]
        assert done_events[0][1]["success"] is True  # parse failures are friendly
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_orchestrator_stream.py -v`
Expected: FAIL — `process_query_stream` not found.

- [ ] **Step 3: Add process_query_stream() to QueryOrchestrator**

Add these to `src/orchestrator.py`. First, store the summarizer as an instance attribute by adding after `self.schema = schema`:

```python
        self.summarizer = summarizer
```

Then add the method after `process_query()`:

```python
    STAGE_MESSAGES = {
        "parse": "Parsing query...",
        "validate": "Validating...",
        "build": "Building query...",
        "execute": "Running query...",
        "summarize": "Summarizing results...",
    }

    def process_query_stream(self, natural_language: str, callback, conversation_history=None) -> None:
        """Process a query with streaming callbacks for status and tokens.

        Args:
            natural_language: The user's question
            callback: Function(event_type, data) called for each event.
                      event_type is "status", "token", or "done".
            conversation_history: Optional conversation history
        """
        logger.info(f"Processing query (streaming): {natural_language}")

        context = PipelineContext(
            natural_language=natural_language,
            source=self.source,
            schema=self.schema,
            conversation_history=conversation_history,
        )

        # Run all steps except summarize
        non_summary_steps = [s for s in self.steps if s.name != "summarize"]
        for step in non_summary_steps:
            msg = self.STAGE_MESSAGES.get(step.name, f"Running {step.name}...")
            callback("status", {"stage": step.name, "message": msg})
            context = step.execute(context)
            if context.error:
                # Surface parse/validate errors as friendly messages
                if context.failed_stage in ("parse", "validate"):
                    callback("token", {"content": context.error})
                    callback("done", {"success": True})
                else:
                    callback("token", {"content": "Sorry, I wasn't able to process that query. Please try rephrasing your question."})
                    logger.error(f"Pipeline failed at {context.failed_stage}: {context.error}")
                    callback("done", {"success": False})
                return

        # Stream the summarize step
        callback("status", {"stage": "summarize", "message": "Summarizing results..."})
        try:
            for token in self.summarizer.summarize_stream(
                context.natural_language, context.rows, context.sql
            ):
                callback("token", {"content": token})
            callback("done", {"success": True})
        except Exception as e:
            logger.error(f"Streaming summarization failed: {e}")
            callback("token", {"content": "Sorry, I wasn't able to summarize the results."})
            callback("done", {"success": False})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_orchestrator_stream.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator_stream.py
git commit -m "feat: add process_query_stream() with callback-based streaming"
```

---

### Task 4: Add /chat/stream SSE endpoint

**Files:**
- Modify: `src/web/routes.py`
- Test: `tests/test_web_stream.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_web_stream.py`:

```python
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from src.server import app


class TestChatStreamEndpoint:
    def setup_method(self):
        import src.server as server_module
        self.mock_graph = MagicMock()
        self._original_graph = server_module.graph
        server_module.graph = self.mock_graph
        self._original_sessions = server_module.sessions
        server_module.sessions = set()
        self._original_orchestrator = server_module.orchestrator
        self.mock_orchestrator = MagicMock()
        server_module.orchestrator = self.mock_orchestrator
        self.client = TestClient(app)

    def teardown_method(self):
        import src.server as server_module
        server_module.graph = self._original_graph
        server_module.sessions = self._original_sessions
        server_module.orchestrator = self._original_orchestrator

    def test_returns_event_stream(self):
        def fake_stream(question, callback, conversation_history=None):
            callback("status", {"stage": "parse", "message": "Parsing..."})
            callback("token", {"content": "Hello"})
            callback("done", {"success": True})

        self.mock_orchestrator.process_query_stream.side_effect = fake_stream

        response = self.client.post(
            "/chat/stream",
            data={"input": "show artists"},
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = response.text
        assert "event: status" in body
        assert "event: token" in body
        assert "event: done" in body
        assert "Hello" in body

    def test_streams_with_session(self):
        import src.server as server_module
        server_module.sessions.add("sess-1")

        def fake_stream(question, callback, conversation_history=None):
            callback("token", {"content": "Result"})
            callback("done", {"success": True})

        self.mock_orchestrator.process_query_stream.side_effect = fake_stream

        response = self.client.post(
            "/chat/stream",
            data={"input": "show artists", "session_id": "sess-1"},
        )

        assert response.status_code == 200
        assert "Result" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_web_stream.py -v`
Expected: FAIL — `/chat/stream` route not found.

- [ ] **Step 3: Add /chat/stream endpoint to src/web/routes.py**

Add these imports at the top of `src/web/routes.py`:

```python
import json
import queue
from fastapi.responses import StreamingResponse
```

Then add the endpoint after the existing `/chat` route:

```python
@router.post("/chat/stream")
async def chat_stream(request: Request, input: str = Form(...), session_id: str = Form(default="")):
    """Stream a query response as Server-Sent Events."""
    server = _server()

    async def event_generator():
        q = queue.Queue()

        def callback(event_type, data):
            q.put((event_type, data))

        def run_pipeline():
            try:
                server.orchestrator.process_query_stream(
                    input, callback=callback, conversation_history=None,
                )
            except Exception as e:
                callback("token", {"content": "Sorry, something went wrong."})
                callback("done", {"success": False})
            finally:
                q.put(None)  # sentinel

        # Run pipeline in thread
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, run_pipeline)

        # Yield SSE events from queue
        while True:
            try:
                item = await asyncio.to_thread(q.get, timeout=60)
            except Exception:
                break
            if item is None:
                break
            event_type, data = item
            yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_web_stream.py -v`
Expected: All 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/web/routes.py tests/test_web_stream.py
git commit -m "feat: add /chat/stream SSE endpoint"
```

---

### Task 5: Update frontend to use streaming

**Files:**
- Modify: `src/web/templates/index.html`
- Modify: `src/web/static/style.css` (add status indicator style)

- [ ] **Step 1: Add status indicator CSS**

Add to `src/web/static/style.css`, before the `/* ── Typing Indicator ── */` section:

```css
/* ── Status Indicator ── */
.status-indicator {
    align-self: flex-start;
    display: flex;
    gap: 14px;
    align-items: flex-start;
    margin-left: 42px;
    padding: 4px 0;
    font-size: 13px;
    color: var(--text-tertiary);
    animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
```

- [ ] **Step 2: Replace sendMessage() in index.html**

Replace the entire `sendMessage` function in `src/web/templates/index.html`:

```javascript
    async function sendMessage(event) {
        event.preventDefault();
        const input = document.getElementById('chat-input');
        const messagesDiv = document.getElementById('chat-messages');
        const text = input.value.trim();
        if (!text) return false;

        const emptyState = messagesDiv.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        // Add user message
        const userMsg = document.createElement('div');
        userMsg.className = 'message user';
        userMsg.textContent = text;
        messagesDiv.appendChild(userMsg);

        // Add typing indicator
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.id = 'stream-indicator';
        indicator.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
        messagesDiv.appendChild(indicator);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;

        input.value = '';

        const sessionId = document.getElementById('session-id-input').value;
        const formData = new FormData();
        formData.append('input', text);
        formData.append('session_id', sessionId);

        let assistantEl = null;
        let contentEl = null;
        let fullContent = '';

        try {
            const response = await fetch('/chat/stream', { method: 'POST', body: formData });
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // keep incomplete line

                let eventType = null;
                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7).trim();
                    } else if (line.startsWith('data: ') && eventType) {
                        const data = JSON.parse(line.slice(6));
                        handleStreamEvent(eventType, data);
                        eventType = null;
                    }
                }
            }
        } catch (e) {
            const ind = document.getElementById('stream-indicator');
            if (ind) ind.remove();
            if (!assistantEl) {
                createAssistantMessage('Error: Failed to connect to server.');
                renderMarkdown(messagesDiv);
            }
        }

        // Refresh sidebar
        if (sessionId) {
            htmx.ajax('GET', '/sidebar', { target: '#sidebar-content', swap: 'innerHTML' });
        }

        function handleStreamEvent(type, data) {
            if (type === 'status') {
                const ind = document.getElementById('stream-indicator');
                if (ind) {
                    ind.className = 'status-indicator';
                    ind.innerHTML = data.message;
                }
            } else if (type === 'token') {
                // First token: replace indicator with assistant message
                if (!assistantEl) {
                    const ind = document.getElementById('stream-indicator');
                    if (ind) ind.remove();
                    assistantEl = createAssistantMessage('');
                    contentEl = assistantEl.querySelector('.markdown-content') || assistantEl.querySelector('.assistant-body');
                }
                fullContent += data.content;
                contentEl.textContent = fullContent;
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            } else if (type === 'done') {
                // Render final markdown
                if (contentEl) {
                    contentEl.innerHTML = marked.parse(fullContent);
                }
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
        }

        function createAssistantMessage(text) {
            const msg = document.createElement('div');
            msg.className = 'message assistant';
            msg.innerHTML = `
                <div class="assistant-icon"><span>O</span></div>
                <div class="assistant-body">
                    <div class="markdown-content">${text}</div>
                </div>`;
            messagesDiv.appendChild(msg);
            return msg;
        }

        return false;
    }
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `pytest tests/test_web.py tests/test_web_stream.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/web/templates/index.html src/web/static/style.css
git commit -m "feat: switch frontend to streaming with progress indicators"
```
