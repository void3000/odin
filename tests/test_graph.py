from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, AIMessage
from src.graph import GraphState, router_node, query_node, chat_node, create_graph


class TestRouterNode:
    def test_classifies_query_intent(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "query")
        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_classifies_chat_intent(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "chat")
        state: GraphState = {
            "messages": [HumanMessage(content="hello, what can you do?")],
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "chat"

    def test_defaults_to_query_on_unexpected_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "I think this is a query about users")
        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_defaults_to_query_on_llm_failure(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (False, "connection error")
        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_includes_conversation_history_in_prompt(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "query")
        state: GraphState = {
            "messages": [
                HumanMessage(content="show users"),
                AIMessage(content="Found 10 users."),
                HumanMessage(content="filter by active"),
            ],
            "intent": None,
            "result": None,
        }
        router_node(state, mock_llm)
        call_args = mock_llm.generate.call_args
        user_message = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][1]
        assert "show users" in user_message
        assert "filter by active" in user_message


class TestQueryNode:
    def test_calls_orchestrator_and_sets_result(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 users.",
            "error": None,
        }
        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert result["result"]["type"] == "query"
        assert result["result"]["success"] is True
        assert result["result"]["summary"] == "Found 3 users."
        mock_orchestrator.process_query.assert_called_once_with(
            "show me all users", conversation_history=None,
        )

    def test_passes_conversation_history_to_orchestrator(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "42 active users.",
            "error": None,
        }
        state: GraphState = {
            "messages": [
                HumanMessage(content="show users"),
                AIMessage(content="Found 10 users."),
                HumanMessage(content="filter by active"),
            ],
            "intent": "query",
            "result": None,
        }
        query_node(state, mock_orchestrator)
        call_args = mock_orchestrator.process_query.call_args
        assert call_args[0][0] == "filter by active"
        history = call_args[1]["conversation_history"]
        assert len(history) == 1
        assert history[0].question == "show users"
        assert history[0].summary == "Found 10 users."

    def test_appends_ai_message_on_success(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": True,
            "summary": "Found 3 users.",
            "error": None,
        }
        state: GraphState = {
            "messages": [HumanMessage(content="show me all users")],
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert result["messages"][0].content == "Found 3 users."

    def test_appends_ai_message_on_failure(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
        }
        state: GraphState = {
            "messages": [HumanMessage(content="bad query")],
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert "Parse failed" in result["messages"][0].content

    def test_handles_orchestrator_failure(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
        }
        state: GraphState = {
            "messages": [HumanMessage(content="bad query")],
            "intent": "query",
            "result": None,
        }
        result = query_node(state, mock_orchestrator)
        assert result["result"]["type"] == "query"
        assert result["result"]["success"] is False
        assert result["result"]["error"] == "Parse failed"


class TestChatNode:
    def test_generates_chat_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "The users table has columns: id, name, email.")
        state: GraphState = {
            "messages": [HumanMessage(content="what tables are available?")],
            "intent": "chat",
            "result": None,
        }
        result = chat_node(state, mock_llm, system_prompt="You are a helpful assistant.\nSchema: users(id, name)")
        assert result["result"]["type"] == "chat"
        assert result["result"]["success"] is True
        assert result["result"]["message"] == "The users table has columns: id, name, email."

    def test_appends_ai_message(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "Hello! How can I help?")
        state: GraphState = {
            "messages": [HumanMessage(content="hello")],
            "intent": "chat",
            "result": None,
        }
        result = chat_node(state, mock_llm, system_prompt="test")
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], AIMessage)
        assert result["messages"][0].content == "Hello! How can I help?"

    def test_handles_llm_failure(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (False, "connection error")
        state: GraphState = {
            "messages": [HumanMessage(content="hello")],
            "intent": "chat",
            "result": None,
        }
        result = chat_node(state, mock_llm, system_prompt="test")
        assert result["result"]["type"] == "chat"
        assert result["result"]["success"] is False
        assert "connection error" in result["result"]["error"]

    def test_includes_conversation_history(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "Sure, the active ones are...")
        state: GraphState = {
            "messages": [
                HumanMessage(content="show users"),
                AIMessage(content="Found 10 users."),
                HumanMessage(content="which ones are active?"),
            ],
            "intent": "chat",
            "result": None,
        }
        chat_node(state, mock_llm, system_prompt="test")
        call_args = mock_llm.generate.call_args
        user_message = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][1]
        assert "show users" in user_message
        assert "which ones are active?" in user_message


class TestCreateGraph:
    def test_creates_compiled_graph_with_checkpointer(self):
        from langgraph.checkpoint.memory import InMemorySaver
        mock_llm = MagicMock()
        mock_orchestrator = MagicMock()
        checkpointer = InMemorySaver()
        graph = create_graph(
            orchestrator=mock_orchestrator,
            llm_client=mock_llm,
            system_prompt="test prompt",
            checkpointer=checkpointer,
        )
        assert graph is not None
        assert hasattr(graph, "invoke")

    def test_creates_graph_without_checkpointer(self):
        mock_llm = MagicMock()
        mock_orchestrator = MagicMock()
        graph = create_graph(
            orchestrator=mock_orchestrator,
            llm_client=mock_llm,
            system_prompt="test prompt",
        )
        assert graph is not None
        assert hasattr(graph, "invoke")
