from unittest.mock import MagicMock
from src.graph import GraphState, router_node, query_node, chat_node, create_graph
from src.session import ConversationTurn


class TestRouterNode:
    def test_classifies_query_intent(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "query")

        state: GraphState = {
            "input": "show me all users",
            "conversation_history": None,
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_classifies_chat_intent(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "chat")

        state: GraphState = {
            "input": "hello, what can you do?",
            "conversation_history": None,
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "chat"

    def test_defaults_to_query_on_unexpected_response(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "I think this is a query about users")

        state: GraphState = {
            "input": "show me all users",
            "conversation_history": None,
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_defaults_to_query_on_llm_failure(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (False, "connection error")

        state: GraphState = {
            "input": "show me all users",
            "conversation_history": None,
            "intent": None,
            "result": None,
        }
        result = router_node(state, mock_llm)
        assert result["intent"] == "query"

    def test_includes_conversation_history_in_prompt(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (True, "query")

        history = [ConversationTurn(question="show users", summary="Found 10 users.")]

        state: GraphState = {
            "input": "filter by active",
            "conversation_history": history,
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
            "input": "show me all users",
            "conversation_history": None,
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

        history = [ConversationTurn(question="show users", summary="Found 10 users.")]

        state: GraphState = {
            "input": "filter by active",
            "conversation_history": history,
            "intent": "query",
            "result": None,
        }
        query_node(state, mock_orchestrator)
        mock_orchestrator.process_query.assert_called_once_with(
            "filter by active", conversation_history=history,
        )

    def test_handles_orchestrator_failure(self):
        mock_orchestrator = MagicMock()
        mock_orchestrator.process_query.return_value = {
            "success": False,
            "error": "Parse failed",
        }

        state: GraphState = {
            "input": "bad query",
            "conversation_history": None,
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
            "input": "what tables are available?",
            "conversation_history": None,
            "intent": "chat",
            "result": None,
        }
        result = chat_node(state, mock_llm, system_prompt="You are a helpful assistant.\nSchema: users(id, name)")
        assert result["result"]["type"] == "chat"
        assert result["result"]["success"] is True
        assert result["result"]["message"] == "The users table has columns: id, name, email."

    def test_handles_llm_failure(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = (False, "connection error")

        state: GraphState = {
            "input": "hello",
            "conversation_history": None,
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

        history = [ConversationTurn(question="show users", summary="Found 10 users.")]

        state: GraphState = {
            "input": "which ones are active?",
            "conversation_history": history,
            "intent": "chat",
            "result": None,
        }
        chat_node(state, mock_llm, system_prompt="test")

        call_args = mock_llm.generate.call_args
        user_message = call_args[1]["user_message"] if "user_message" in call_args[1] else call_args[0][1]
        assert "show users" in user_message
        assert "which ones are active?" in user_message


class TestCreateGraph:
    def test_creates_compiled_graph(self):
        mock_llm = MagicMock()
        mock_orchestrator = MagicMock()
        graph = create_graph(
            orchestrator=mock_orchestrator,
            llm_client=mock_llm,
            system_prompt="test prompt",
        )
        assert graph is not None
        assert hasattr(graph, "invoke")
