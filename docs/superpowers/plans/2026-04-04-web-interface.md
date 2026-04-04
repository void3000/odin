# Web Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a chat-style web interface to Odin, served by the existing FastAPI server using Jinja2 templates and HTMX.

**Architecture:** Jinja2 templates render HTML, HTMX handles partial page updates (no full reloads). Web routes live in `src/web/` and call the same `graph.invoke()` path as the API. Pico CSS provides polished defaults.

**Tech Stack:** Jinja2, HTMX (CDN), Pico CSS (CDN), FastAPI `Jinja2Templates`

---

### Task 1: Add jinja2 dependency and create web module skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/web/__init__.py`
- Create: `src/web/routes.py`

- [ ] **Step 1: Add jinja2 to pyproject.toml**

In `pyproject.toml`, add `"jinja2"` to the `dependencies` list:

```toml
dependencies = [
    "langgraph",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "fastapi",
    "uvicorn[standard]",
    "jinja2",
]
```

- [ ] **Step 2: Install the updated dependencies**

Run: `pip install -e .`

- [ ] **Step 3: Create src/web/__init__.py**

```python
"""Odin Web Interface — Jinja2 + HTMX chat UI."""
```

- [ ] **Step 4: Create src/web/routes.py with placeholder routes**

```python
"""Web interface routes for the Odin chat UI."""

import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from langchain_core.messages import AIMessage, HumanMessage

import src.server as server_module

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page — sidebar + chat area."""
    session_names = _get_session_names()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "sessions": session_names,
        "active_session": None,
        "messages": [],
    })


@router.post("/sessions", response_class=HTMLResponse)
async def create_session(request: Request):
    """Create a new session, return updated sidebar partial."""
    session_id = str(uuid.uuid4())
    server_module.sessions.add(session_id)
    session_names = _get_session_names()
    return templates.TemplateResponse("partials/sidebar.html", {
        "request": request,
        "sessions": session_names,
        "active_session": session_id,
    })


@router.delete("/sessions/{session_id}", response_class=HTMLResponse)
async def delete_session(request: Request, session_id: str):
    """Delete a session, return updated sidebar partial."""
    server_module.sessions.discard(session_id)
    session_names = _get_session_names()
    return templates.TemplateResponse("partials/sidebar.html", {
        "request": request,
        "sessions": session_names,
        "active_session": None,
    })


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def load_session(request: Request, session_id: str):
    """Load a session's chat history, return chat area partial."""
    messages = _get_session_messages(session_id)
    return templates.TemplateResponse("partials/chat_area.html", {
        "request": request,
        "active_session": session_id,
        "messages": messages,
    })


@router.post("/chat", response_class=HTMLResponse)
async def chat(request: Request, input: str = Form(...), session_id: str = Form(default="")):
    """Send a query, return the assistant's response as a message partial."""
    config = None
    if session_id:
        config = {"configurable": {"thread_id": session_id}}
    else:
        # Throwaway thread for single-query mode
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    graph_result = await asyncio.to_thread(
        server_module.graph.invoke,
        {"messages": [HumanMessage(content=input)]},
        config,
    )

    result = graph_result["result"]
    if result.get("success"):
        content = result.get("summary") or result.get("message", "")
    else:
        content = f"Error: {result.get('error', 'Unknown error')}"

    return templates.TemplateResponse("partials/message.html", {
        "request": request,
        "role": "assistant",
        "content": content,
    })


def _get_session_names() -> list[dict]:
    """Get session IDs with display names from the checkpointer."""
    result = []
    for session_id in server_module.sessions:
        name = "New Session"
        turn_count = 0
        try:
            config = {"configurable": {"thread_id": session_id}}
            state = server_module.graph.get_state(config)
            messages = state.values.get("messages", [])
            if messages:
                first_human = next(
                    (m for m in messages if isinstance(m, HumanMessage)), None
                )
                if first_human:
                    name = first_human.content[:30]
                    if len(first_human.content) > 30:
                        name += "..."
                turn_count = len([m for m in messages if isinstance(m, HumanMessage)])
        except Exception:
            pass
        result.append({
            "id": session_id,
            "name": name,
            "turn_count": turn_count,
        })
    return result


def _get_session_messages(session_id: str) -> list[dict]:
    """Get message history for a session from the checkpointer."""
    try:
        config = {"configurable": {"thread_id": session_id}}
        state = server_module.graph.get_state(config)
        messages = state.values.get("messages", [])
    except Exception:
        messages = []

    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"role": "assistant", "content": msg.content})
    return result
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/web/__init__.py src/web/routes.py
git commit -m "feat: add web module skeleton with routes"
```

---

### Task 2: Create base template and static CSS

**Files:**
- Create: `src/web/templates/base.html`
- Create: `src/web/static/style.css`

- [ ] **Step 1: Create src/web/templates/base.html**

```html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Odin</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
    <link rel="stylesheet" href="/static/style.css">
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
</head>
<body>
    {% block body %}{% endblock %}
</body>
</html>
```

- [ ] **Step 2: Create src/web/static/style.css**

```css
/* Reset Pico defaults for full-height chat layout */
:root {
    --pico-font-size: 15px;
    --accent: #7c6ef0;
    --accent-hover: #6b5dd3;
    --sidebar-bg: #11111b;
    --sidebar-width: 260px;
    --chat-bg: #181825;
    --msg-user-bg: #7c6ef0;
    --msg-user-color: #ffffff;
    --msg-assistant-bg: #2a2a3c;
    --msg-assistant-color: #cdd6f4;
    --input-bg: #1e1e2e;
    --border-color: #313244;
}

html, body {
    height: 100%;
    margin: 0;
    padding: 0;
    overflow: hidden;
}

/* Main layout */
.app-layout {
    display: flex;
    height: 100vh;
}

/* Sidebar */
.sidebar {
    width: var(--sidebar-width);
    min-width: var(--sidebar-width);
    background: var(--sidebar-bg);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    padding: 0;
}

.sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.sidebar-header h2 {
    margin: 0;
    font-size: 18px;
    color: #cdd6f4;
}

.btn-new-session {
    background: var(--border-color);
    color: #bac2de;
    border: none;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 13px;
    cursor: pointer;
}

.btn-new-session:hover {
    background: #45475a;
}

.session-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
}

.session-item {
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 4px;
    transition: background 0.15s;
}

.session-item:hover {
    background: #1e1e2e;
}

.session-item.active {
    background: #1e1e2e;
    border-left: 3px solid var(--accent);
}

.session-item .session-name {
    font-size: 13px;
    color: #cdd6f4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.session-item .session-meta {
    font-size: 11px;
    color: #585b70;
    margin-top: 2px;
}

.session-item .session-delete {
    float: right;
    color: #585b70;
    font-size: 12px;
    cursor: pointer;
    border: none;
    background: none;
    padding: 0;
    line-height: 1;
}

.session-item .session-delete:hover {
    color: #f38ba8;
}

.sidebar-footer {
    padding: 12px 16px;
    border-top: 1px solid var(--border-color);
}

.sidebar-footer label {
    font-size: 12px;
    color: #585b70;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0;
}

/* Chat area */
.chat-area {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: var(--chat-bg);
    min-width: 0;
}

.chat-header {
    padding: 12px 20px;
    border-bottom: 1px solid var(--border-color);
    font-size: 14px;
    color: #bac2de;
}

.chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.chat-input-area {
    padding: 16px 20px;
    border-top: 1px solid var(--border-color);
}

.chat-input-form {
    display: flex;
    gap: 8px;
    align-items: center;
    margin: 0;
}

.chat-input-form input[type="text"] {
    flex: 1;
    background: var(--input-bg);
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 10px 16px;
    color: #cdd6f4;
    font-size: 14px;
    margin: 0;
}

.chat-input-form input[type="text"]:focus {
    border-color: var(--accent);
    outline: none;
}

.chat-input-form button[type="submit"] {
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    cursor: pointer;
    font-size: 14px;
    width: auto;
    margin: 0;
}

.chat-input-form button[type="submit"]:hover {
    background: var(--accent-hover);
}

/* Message bubbles */
.message {
    max-width: 70%;
    padding: 10px 16px;
    border-radius: 16px;
    font-size: 14px;
    line-height: 1.5;
    word-wrap: break-word;
}

.message.user {
    align-self: flex-end;
    background: var(--msg-user-bg);
    color: var(--msg-user-color);
    border-bottom-right-radius: 4px;
}

.message.assistant {
    align-self: flex-start;
    background: var(--msg-assistant-bg);
    color: var(--msg-assistant-color);
    border-bottom-left-radius: 4px;
}

/* Typing indicator */
.typing-indicator {
    align-self: flex-start;
    padding: 10px 16px;
    background: var(--msg-assistant-bg);
    border-radius: 16px;
    border-bottom-left-radius: 4px;
    display: flex;
    gap: 4px;
    align-items: center;
}

.typing-indicator .dot {
    width: 8px;
    height: 8px;
    background: #585b70;
    border-radius: 50%;
    animation: typing 1.4s infinite;
}

.typing-indicator .dot:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator .dot:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
    0%, 60%, 100% { opacity: 0.3; transform: translateY(0); }
    30% { opacity: 1; transform: translateY(-4px); }
}

/* Empty state */
.empty-state {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #585b70;
    font-size: 15px;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/web/templates/base.html src/web/static/style.css
git commit -m "feat: add base template and CSS styles"
```

---

### Task 3: Create index.html and partial templates

**Files:**
- Create: `src/web/templates/index.html`
- Create: `src/web/templates/partials/sidebar.html`
- Create: `src/web/templates/partials/chat_area.html`
- Create: `src/web/templates/partials/message.html`
- Create: `src/web/templates/partials/typing.html`

- [ ] **Step 1: Create src/web/templates/partials/message.html**

```html
<div class="message {{ role }}">
    {{ content }}
</div>
```

- [ ] **Step 2: Create src/web/templates/partials/typing.html**

```html
<div class="typing-indicator" id="typing-indicator">
    <div class="dot"></div>
    <div class="dot"></div>
    <div class="dot"></div>
</div>
```

- [ ] **Step 3: Create src/web/templates/partials/sidebar.html**

```html
<div class="session-list" id="session-list">
    {% for session in sessions %}
    <div class="session-item {% if session.id == active_session %}active{% endif %}"
         hx-get="/sessions/{{ session.id }}"
         hx-target="#chat-area"
         hx-swap="innerHTML"
         onclick="setActiveSession('{{ session.id }}', this)">
        <button class="session-delete"
                hx-delete="/sessions/{{ session.id }}"
                hx-target="#sidebar-content"
                hx-swap="innerHTML"
                onclick="event.stopPropagation(); if(getActiveSession() === '{{ session.id }}') clearChat();"
                title="Delete session">&times;</button>
        <div class="session-name">{{ session.name }}</div>
        <div class="session-meta">{{ session.turn_count }} turn{{ 's' if session.turn_count != 1 else '' }}</div>
    </div>
    {% endfor %}
    {% if not sessions %}
    <div style="padding: 12px; color: #585b70; font-size: 13px;">No sessions yet</div>
    {% endif %}
</div>
```

- [ ] **Step 4: Create src/web/templates/partials/chat_area.html**

```html
<div class="chat-header">
    {% if active_session %}
        Session
    {% else %}
        Single Query
    {% endif %}
</div>
<div class="chat-messages" id="chat-messages">
    {% for msg in messages %}
        {% include "partials/message.html" with context %}
        {% set role = msg.role %}
        {% set content = msg.content %}
    {% endfor %}
    {% if not messages %}
    <div class="empty-state">Ask a question about your data</div>
    {% endif %}
</div>
<div class="chat-input-area">
    <form class="chat-input-form" onsubmit="return sendMessage(event)">
        <input type="hidden" name="session_id" id="session-id-input" value="{{ active_session or '' }}">
        <input type="text" name="input" id="chat-input" placeholder="Ask a question about your data..." autocomplete="off" required>
        <button type="submit">Send</button>
    </form>
</div>
```

- [ ] **Step 5: Create src/web/templates/index.html**

```html
{% extends "base.html" %}

{% block body %}
<div class="app-layout">
    <div class="sidebar">
        <div class="sidebar-header">
            <h2>Odin</h2>
            <button class="btn-new-session"
                    hx-post="/sessions"
                    hx-target="#sidebar-content"
                    hx-swap="innerHTML">+ New</button>
        </div>
        <div id="sidebar-content">
            {% include "partials/sidebar.html" %}
        </div>
        <div class="sidebar-footer">
            <label>
                <input type="checkbox" id="single-query-toggle"
                       onchange="toggleSingleQuery(this.checked)" checked>
                Single query mode
            </label>
        </div>
    </div>
    <div class="chat-area" id="chat-area">
        <div class="chat-header">Single Query</div>
        <div class="chat-messages" id="chat-messages">
            <div class="empty-state">Ask a question about your data</div>
        </div>
        <div class="chat-input-area">
            <form class="chat-input-form" onsubmit="return sendMessage(event)">
                <input type="hidden" name="session_id" id="session-id-input" value="">
                <input type="text" name="input" id="chat-input" placeholder="Ask a question about your data..." autocomplete="off" required>
                <button type="submit">Send</button>
            </form>
        </div>
    </div>
</div>

<script>
    let activeSession = null;

    function getActiveSession() { return activeSession; }

    function setActiveSession(sessionId, element) {
        activeSession = sessionId;
        document.getElementById('session-id-input').value = sessionId;
        document.getElementById('single-query-toggle').checked = false;
        // Update active class
        document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
        if (element) element.classList.add('active');
    }

    function clearChat() {
        activeSession = null;
        document.getElementById('session-id-input').value = '';
        document.getElementById('single-query-toggle').checked = true;
        document.getElementById('chat-area').innerHTML = `
            <div class="chat-header">Single Query</div>
            <div class="chat-messages" id="chat-messages">
                <div class="empty-state">Ask a question about your data</div>
            </div>
            <div class="chat-input-area">
                <form class="chat-input-form" onsubmit="return sendMessage(event)">
                    <input type="hidden" name="session_id" id="session-id-input" value="">
                    <input type="text" name="input" id="chat-input" placeholder="Ask a question about your data..." autocomplete="off" required>
                    <button type="submit">Send</button>
                </form>
            </div>`;
    }

    function toggleSingleQuery(checked) {
        if (checked) {
            activeSession = null;
            document.getElementById('session-id-input').value = '';
            document.querySelectorAll('.session-item').forEach(el => el.classList.remove('active'));
            clearChat();
        }
    }

    function sendMessage(event) {
        event.preventDefault();
        const input = document.getElementById('chat-input');
        const messagesDiv = document.getElementById('chat-messages');
        const text = input.value.trim();
        if (!text) return false;

        // Remove empty state if present
        const emptyState = messagesDiv.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        // Add user message immediately (optimistic UI)
        const userMsg = document.createElement('div');
        userMsg.className = 'message user';
        userMsg.textContent = text;
        messagesDiv.appendChild(userMsg);

        // Add typing indicator
        const typing = document.createElement('div');
        typing.className = 'typing-indicator';
        typing.id = 'typing-indicator';
        typing.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
        messagesDiv.appendChild(typing);

        // Scroll to bottom
        messagesDiv.scrollTop = messagesDiv.scrollHeight;

        // Send via fetch
        const sessionId = document.getElementById('session-id-input').value;
        const formData = new FormData();
        formData.append('input', text);
        formData.append('session_id', sessionId);

        fetch('/chat', { method: 'POST', body: formData })
            .then(response => response.text())
            .then(html => {
                const indicator = document.getElementById('typing-indicator');
                if (indicator) {
                    indicator.outerHTML = html;
                }
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
                // Refresh sidebar to update session names/turn counts
                if (sessionId) {
                    htmx.ajax('GET', '/sidebar', { target: '#sidebar-content', swap: 'innerHTML' });
                }
            })
            .catch(() => {
                const indicator = document.getElementById('typing-indicator');
                if (indicator) {
                    indicator.outerHTML = '<div class="message assistant">Error: Failed to connect to server.</div>';
                }
            });

        input.value = '';
        return false;
    }
</script>
{% endblock %}
```

- [ ] **Step 6: Commit**

```bash
git add src/web/templates/index.html src/web/templates/partials/
git commit -m "feat: add index and partial templates"
```

---

### Task 4: Mount web routes on the FastAPI app

**Files:**
- Modify: `src/server.py`
- Modify: `src/web/routes.py` (add sidebar refresh route)

- [ ] **Step 1: Add a sidebar refresh route to src/web/routes.py**

Add this route after the existing routes in `routes.py`:

```python
@router.get("/sidebar", response_class=HTMLResponse)
async def refresh_sidebar(request: Request):
    """Return the sidebar partial (for refreshing after a query)."""
    session_names = _get_session_names()
    active = request.query_params.get("active")
    return templates.TemplateResponse("partials/sidebar.html", {
        "request": request,
        "sessions": session_names,
        "active_session": active,
    })
```

- [ ] **Step 2: Mount web routes and static files in src/server.py**

Add these imports at the top of `src/server.py`:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from src.web.routes import router as web_router
```

Then after the line `app.add_middleware(RequestIdMiddleware)`, add:

```python
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "web" / "static")), name="static")
app.include_router(web_router)
```

- [ ] **Step 3: Verify the server starts and serves the page**

Run: `ODIN_LOG_LEVEL=WARNING python -c "from src.server import app; print('App created successfully')"`
Expected: `App created successfully` (no import errors)

- [ ] **Step 4: Commit**

```bash
git add src/server.py src/web/routes.py
git commit -m "feat: mount web routes and static files on FastAPI app"
```

---

### Task 5: Fix the chat_area partial template rendering

The `chat_area.html` partial needs to render messages from a list of dicts correctly. The initial version uses Jinja2 includes incorrectly. Fix it.

**Files:**
- Modify: `src/web/templates/partials/chat_area.html`

- [ ] **Step 1: Rewrite chat_area.html to render messages correctly**

Replace the contents of `src/web/templates/partials/chat_area.html`:

```html
<div class="chat-header">
    {% if active_session %}
        Session
    {% else %}
        Single Query
    {% endif %}
</div>
<div class="chat-messages" id="chat-messages">
    {% for msg in messages %}
    <div class="message {{ msg.role }}">
        {{ msg.content }}
    </div>
    {% endfor %}
    {% if not messages %}
    <div class="empty-state">Ask a question about your data</div>
    {% endif %}
</div>
<div class="chat-input-area">
    <form class="chat-input-form" onsubmit="return sendMessage(event)">
        <input type="hidden" name="session_id" id="session-id-input" value="{{ active_session or '' }}">
        <input type="text" name="input" id="chat-input" placeholder="Ask a question about your data..." autocomplete="off" required>
        <button type="submit">Send</button>
    </form>
</div>
<script>
    // Re-set the active session after HTMX swap
    {% if active_session %}
    activeSession = '{{ active_session }}';
    {% endif %}
    // Scroll to bottom of chat
    var chatMessages = document.getElementById('chat-messages');
    if (chatMessages) chatMessages.scrollTop = chatMessages.scrollHeight;
</script>
```

- [ ] **Step 2: Commit**

```bash
git add src/web/templates/partials/chat_area.html
git commit -m "fix: render message list correctly in chat area partial"
```

---

### Task 6: Write tests for web routes

**Files:**
- Create: `tests/test_web.py`

- [ ] **Step 1: Create tests/test_web.py**

```python
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage, AIMessage

from src.server import app


class TestWebRoutes:
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

    def test_index_returns_html(self):
        response = self.client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Odin" in response.text

    def test_create_session_returns_sidebar(self):
        response = self.client.post("/sessions")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        import src.server as server_module
        assert len(server_module.sessions) == 1

    def test_delete_session_returns_sidebar(self):
        import src.server as server_module
        server_module.sessions.add("test-session-id")
        response = self.client.delete("/sessions/test-session-id")
        assert response.status_code == 200
        assert "test-session-id" not in server_module.sessions

    def test_chat_returns_message_partial(self):
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="show all artists"),
                AIMessage(content="Found 275 artists."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 275 artists.",
                "error": None,
            },
        }
        response = self.client.post("/chat", data={"input": "show all artists"})
        assert response.status_code == 200
        assert "Found 275 artists." in response.text
        assert "assistant" in response.text

    def test_chat_with_session(self):
        import src.server as server_module
        server_module.sessions.add("sess-123")
        self.mock_graph.invoke.return_value = {
            "messages": [
                HumanMessage(content="show all artists"),
                AIMessage(content="Found 275 artists."),
            ],
            "intent": "query",
            "result": {
                "type": "query",
                "success": True,
                "summary": "Found 275 artists.",
                "error": None,
            },
        }
        response = self.client.post(
            "/chat",
            data={"input": "show all artists", "session_id": "sess-123"},
        )
        assert response.status_code == 200
        # Verify thread_id was passed in config
        call_args = self.mock_graph.invoke.call_args
        config = call_args[0][1]
        assert config["configurable"]["thread_id"] == "sess-123"

    def test_chat_error_shows_error_message(self):
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
        response = self.client.post("/chat", data={"input": "bad query"})
        assert response.status_code == 200
        assert "Error:" in response.text
        assert "Parse failed" in response.text

    def test_load_session_returns_chat_area(self):
        import src.server as server_module
        server_module.sessions.add("sess-456")

        mock_state = MagicMock()
        mock_state.values = {
            "messages": [
                HumanMessage(content="show artists"),
                AIMessage(content="Found 275 artists."),
            ]
        }
        self.mock_graph.get_state.return_value = mock_state

        response = self.client.get("/sessions/sess-456")
        assert response.status_code == 200
        assert "show artists" in response.text
        assert "Found 275 artists." in response.text

    def test_sidebar_refresh(self):
        response = self.client.get("/sidebar")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_web.py -v`
Expected: All 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_web.py
git commit -m "test: add web interface route tests"
```
