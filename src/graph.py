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
    """Extract the current question and conversation history from messages."""
    if not messages:
        return "", None

    current_question = messages[-1].content if messages else ""

    history = []
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

    intent = "query"
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

    ai_content = response if success else f"Chat generation failed: {response}"
    return {"result": result, "messages": [AIMessage(content=ai_content)]}


def _route_by_intent(state: GraphState) -> str:
    """Conditional edge: route based on classified intent."""
    return state["intent"]


def create_graph(orchestrator: Any, llm_client: Any, system_prompt: str, checkpointer=None):
    """Build and compile the intent routing graph."""
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
