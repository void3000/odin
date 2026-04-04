# Web Interface Design

A chat-style web interface for Odin, served by the existing FastAPI server using Jinja2 templates and HTMX for interactivity.

## Motivation

Odin currently only exposes a REST API. A web interface lets users interact with the natural language query pipeline directly in a browser without needing curl or a separate client.

## Approach

Jinja2 templates + HTMX, served by FastAPI. Pico CSS from CDN for polished defaults. No build step, no separate frontend project. All interactivity via HTMX partial swaps calling internal server routes.

## Layout

Left sidebar + chat area (ChatGPT-style):

- **Sidebar (fixed 260px):** "Odin" branding, "New Session" button, session list, single-query-mode toggle at bottom.
- **Chat area (flex-grow):** Header bar (session name or "Single Query"), scrollable message list, input form pinned to bottom.

User messages are right-aligned with an accent color. Assistant messages are left-aligned with a muted background. Summary-only responses (no raw data tables).

## File Structure

```
src/
├── web/
│   ├── __init__.py          # Mount routes on FastAPI app
│   ├── routes.py            # Web page routes
│   ├── templates/
│   │   ├── base.html        # Base layout (head, Pico CSS, HTMX)
│   │   ├── index.html       # Main page — sidebar + chat area
│   │   └── partials/
│   │       ├── message.html  # Single chat message bubble
│   │       ├── sidebar.html  # Session list
│   │       └── typing.html   # "Thinking..." indicator
│   └── static/
│       └── style.css         # Custom styles on top of Pico CSS
```

## Routes

| Route | Method | Returns | Purpose |
|---|---|---|---|
| `/` | GET | Full page | Main page with sidebar + chat area |
| `/sessions` | POST | Sidebar partial | Create session, return updated sidebar |
| `/sessions/{id}` | DELETE | Sidebar partial | Delete session, return updated sidebar |
| `/sessions/{id}` | GET | Chat area partial | Switch to session, load message history |
| `/chat` | POST | Message partials | Send query, return assistant response HTML |

## HTMX Interactions

### Sending a message

1. User types in input, presses Enter or clicks send.
2. HTMX `hx-post="/chat"` sends form data (`input` + optional `session_id`).
3. JavaScript appends the user's message bubble immediately (optimistic UI).
4. A "thinking..." indicator appears.
5. Server processes query via `graph.invoke()`, renders `message.html` partial.
6. HTMX swaps the "thinking..." indicator with the response.
7. Chat auto-scrolls to bottom.

### Session management

- **New Session:** `hx-post="/sessions"` returns updated sidebar HTML.
- **Switch session:** `hx-get="/sessions/{id}"` returns chat area with message history.
- **Delete session:** `hx-delete="/sessions/{id}"` returns updated sidebar.

## Data Flow & State

### Server-side state

Web routes import `graph` and `sessions` globals from `src/server.py` — same pattern as existing API endpoints.

### Message history

When loading a session's chat, the route calls `graph.get_state(config)` with the session's `thread_id` to retrieve the checkpointed `messages` list. Iterates through `HumanMessage`/`AIMessage` pairs and renders each as a `message.html` partial. The checkpointer is the single source of truth.

### Single query mode

No session ID is passed. Server generates a throwaway UUID for `thread_id` (so the graph can execute) but does not add it to the `sessions` set. Chat area resets on page load.

### Session naming

Sidebar shows the first `HumanMessage` content in the session (truncated to ~30 chars). Derived at render time from the checkpointer state — no extra storage.

## Templates

### base.html

Shared layout with `<head>` containing Pico CSS (CDN), HTMX (CDN), and custom `style.css`. Full-height body with no padding.

### index.html

Extends base. Two-column flex layout: sidebar (fixed 260px) + chat area (flex-grow). Input form uses `hx-post="/chat"`.

### partials/message.html

Single message bubble. Takes `role` ("user" or "assistant") and `content`. User messages right-aligned with accent color, assistant messages left-aligned with muted background.

### partials/sidebar.html

Session list with name, turn count, active highlight. Each item clickable via `hx-get`. Includes single-query-mode toggle.

### partials/typing.html

Animated "Thinking..." indicator with an ID for HTMX replacement.

### style.css

Custom overrides on top of Pico CSS: chat bubble styling, sidebar layout, full-height layout, typing indicator animation.

## Server Changes

### src/server.py

Mount web routes from `src/web`. Add Jinja2 `Templates` instance. Mount `src/web/static` as static files.

### pyproject.toml

Add `jinja2` to dependencies.

## Files Changed

| File | Action |
|---|---|
| `src/web/__init__.py` | Create — mount web routes |
| `src/web/routes.py` | Create — page routes |
| `src/web/templates/base.html` | Create — base layout |
| `src/web/templates/index.html` | Create — main page |
| `src/web/templates/partials/message.html` | Create — message bubble |
| `src/web/templates/partials/sidebar.html` | Create — session list |
| `src/web/templates/partials/typing.html` | Create — typing indicator |
| `src/web/static/style.css` | Create — custom styles |
| `src/server.py` | Modify — mount web routes, Jinja2 setup |
| `pyproject.toml` | Modify — add jinja2 dependency |

No changes to `graph.py`, `orchestrator.py`, existing API routes, or any query pipeline code. The web UI is purely additive.

## Dependencies

- `jinja2` — added to `pyproject.toml`
- Pico CSS — CDN, no install
- HTMX — CDN, no install
