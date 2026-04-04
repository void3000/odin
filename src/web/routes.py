"""Web interface routes for the Odin chat UI."""

import asyncio
import json
import queue
import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from langchain_core.messages import AIMessage, HumanMessage

TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

router = APIRouter()


def _server():
    """Lazy import to avoid circular dependency."""
    import src.server as server_module
    return server_module


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page — sidebar + chat area."""
    session_names = _get_session_names()
    return templates.TemplateResponse(request, "index.html", context={
        "sessions": session_names,
        "active_session": None,
        "messages": [],
    })


@router.post("/sessions", response_class=HTMLResponse)
async def create_session(request: Request):
    """Create a new session, return updated sidebar partial."""
    session_id = str(uuid.uuid4())
    _server().sessions.add(session_id)
    session_names = _get_session_names()
    return templates.TemplateResponse(request, "partials/sidebar.html", context={
        "sessions": session_names,
        "active_session": session_id,
    })


@router.delete("/sessions/{session_id}", response_class=HTMLResponse)
async def delete_session(request: Request, session_id: str):
    """Delete a session, return updated sidebar partial."""
    _server().sessions.discard(session_id)
    session_names = _get_session_names()
    return templates.TemplateResponse(request, "partials/sidebar.html", context={
        "sessions": session_names,
        "active_session": None,
    })


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def load_session(request: Request, session_id: str):
    """Load a session's chat history, return chat area partial."""
    messages = _get_session_messages(session_id)
    return templates.TemplateResponse(request, "partials/chat_area.html", context={
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
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    graph_result = await asyncio.to_thread(
        _server().graph.invoke,
        {"messages": [HumanMessage(content=input)]},
        config,
    )

    result = graph_result["result"]
    if result.get("success"):
        content = result.get("summary") or result.get("message", "")
    else:
        content = f"Error: {result.get('error', 'Unknown error')}"

    return templates.TemplateResponse(request, "partials/message.html", context={
        "role": "assistant",
        "content": content,
    })


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


@router.get("/sidebar", response_class=HTMLResponse)
async def refresh_sidebar(request: Request):
    """Return the sidebar partial (for refreshing after a query)."""
    session_names = _get_session_names()
    active = request.query_params.get("active")
    return templates.TemplateResponse(request, "partials/sidebar.html", context={
        "sessions": session_names,
        "active_session": active,
    })


def _get_session_names() -> list[dict]:
    """Get session IDs with display names from the checkpointer."""
    result = []
    for session_id in _server().sessions:
        name = "New Session"
        turn_count = 0
        try:
            config = {"configurable": {"thread_id": session_id}}
            state = _server().graph.get_state(config)
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
        state = _server().graph.get_state(config)
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
