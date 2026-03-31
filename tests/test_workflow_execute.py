from unittest.mock import MagicMock, patch

from src.workflows.base import PipelineContext
from src.workflows.execute import ExecuteWorkflow


def _make_context() -> PipelineContext:
    ctx = PipelineContext(
        natural_language="Show me all users",
        db_path="/tmp/test.db",
        schema={},
    )
    ctx.sql = "SELECT id, name FROM users"
    ctx.params = []
    return ctx


class TestExecuteWorkflow:
    @patch("src.workflows.execute.SQLiteConnector")
    def test_successful_execution_sets_rows(self, MockConnector):
        mock_conn = MockConnector.return_value
        mock_raw = MagicMock()
        mock_raw.columns = ["id", "name"]
        mock_raw.rows = [(1, "Alice"), (2, "Bob")]
        mock_conn.execute_query.return_value = mock_raw

        workflow = ExecuteWorkflow("/tmp/test.db")
        ctx = workflow.run(_make_context())

        assert ctx.rows == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        assert ctx.error is None
        mock_conn.connect.assert_called_once()
        mock_conn.disconnect.assert_called_once()

    @patch("src.workflows.execute.SQLiteConnector")
    def test_database_error_sets_error(self, MockConnector):
        from src.executor.errors import DatabaseError

        mock_conn = MockConnector.return_value
        mock_conn.execute_query.side_effect = DatabaseError("table not found")

        workflow = ExecuteWorkflow("/tmp/test.db")
        ctx = workflow.run(_make_context())

        assert ctx.error == "table not found"
        assert ctx.failed_stage == "execute"
        mock_conn.disconnect.assert_called_once()

    @patch("src.workflows.execute.SQLiteConnector")
    def test_passes_sql_and_params_to_connector(self, MockConnector):
        mock_conn = MockConnector.return_value
        mock_raw = MagicMock()
        mock_raw.columns = ["id"]
        mock_raw.rows = []
        mock_conn.execute_query.return_value = mock_raw

        workflow = ExecuteWorkflow("/tmp/test.db")
        ctx = _make_context()
        ctx.sql = "SELECT id FROM users WHERE name = ?"
        ctx.params = ["Alice"]
        workflow.run(ctx)

        mock_conn.execute_query.assert_called_once_with(
            {"sql": "SELECT id FROM users WHERE name = ?", "params": ["Alice"]}
        )
