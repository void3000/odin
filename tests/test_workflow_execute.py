from unittest.mock import MagicMock
from src.workflows.base import PipelineContext
from src.workflows.execute import ExecuteWorkflow
from src.sources.base import QueryResult


class TestExecuteWorkflow:
    def test_uses_source_execute(self):
        mock_source = MagicMock()
        mock_source.is_connected.return_value = False
        mock_source.execute.return_value = QueryResult(
            rows=[{"id": 1, "name": "Alice"}],
            columns=["id", "name"],
            row_count=1,
            source_name="test_db",
        )

        mock_query = MagicMock()

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.native_query = mock_query

        workflow = ExecuteWorkflow()
        result = workflow.run(context)

        mock_source.connect.assert_called_once()
        mock_source.execute.assert_called_once_with(mock_query)
        mock_source.disconnect.assert_called_once()
        assert result.rows == [{"id": 1, "name": "Alice"}]
        assert result.error is None

    def test_skips_connect_if_already_connected(self):
        mock_source = MagicMock()
        mock_source.is_connected.return_value = True
        mock_source.execute.return_value = QueryResult(
            rows=[], columns=[], row_count=0, source_name="db",
        )

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.native_query = MagicMock()

        workflow = ExecuteWorkflow()
        workflow.run(context)

        mock_source.connect.assert_not_called()

    def test_handles_execution_error(self):
        mock_source = MagicMock()
        mock_source.is_connected.return_value = True
        mock_source.execute.side_effect = Exception("Connection lost")

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.native_query = MagicMock()

        workflow = ExecuteWorkflow()
        result = workflow.run(context)

        assert result.error is not None
        assert "Connection lost" in result.error
