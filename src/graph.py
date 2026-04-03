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
