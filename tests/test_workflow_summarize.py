from unittest.mock import MagicMock

from src.workflows.base import PipelineContext
from src.workflows.summarize import SummarizeWorkflow


def _make_context() -> PipelineContext:
    ctx = PipelineContext(
        natural_language="Show me all users",
        db_path="/tmp/test.db",
        schema={},
    )
    ctx.sql = "SELECT id, name FROM users"
    ctx.rows = [{"id": 1, "name": "Alice"}]
    return ctx


class TestSummarizeWorkflow:
    def test_successful_summary(self):
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (True, "There is 1 user: Alice.")

        workflow = SummarizeWorkflow(mock_summarizer)
        ctx = workflow.run(_make_context())

        assert ctx.summary == "There is 1 user: Alice."
        assert ctx.error is None

    def test_failed_summary_sets_error(self):
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (False, "LLM request failed")

        workflow = SummarizeWorkflow(mock_summarizer)
        ctx = workflow.run(_make_context())

        assert ctx.summary is None
        assert ctx.error == "LLM request failed"
        assert ctx.failed_stage == "summarize"

    def test_passes_correct_args_to_summarizer(self):
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = (True, "summary")

        workflow = SummarizeWorkflow(mock_summarizer)
        ctx = _make_context()
        workflow.run(ctx)

        mock_summarizer.summarize.assert_called_once_with(
            "Show me all users",
            [{"id": 1, "name": "Alice"}],
            "SELECT id, name FROM users",
        )
