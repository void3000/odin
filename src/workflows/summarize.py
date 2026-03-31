"""SummarizeWorkflow — summarizes query results using LLM."""

from src.summarizer import ResultSummarizer
from src.workflows.base import Workflow, PipelineContext


class SummarizeWorkflow(Workflow):
    name = "summarize"

    def __init__(self, summarizer: ResultSummarizer):
        self.summarizer = summarizer

    def run(self, context: PipelineContext) -> PipelineContext:
        success, summary = self.summarizer.summarize(
            context.natural_language, context.rows, context.sql
        )
        if not success:
            context.error = summary
            context.failed_stage = self.name
            return context
        context.summary = summary
        return context
