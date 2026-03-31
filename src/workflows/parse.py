"""ParseWorkflow — converts natural language to QueryIR via LLM."""

from src.ir.parser import IRParser
from src.workflows.base import Workflow, PipelineContext


class ParseWorkflow(Workflow):
    name = "parse"

    def __init__(self, parser: IRParser):
        self.parser = parser

    def run(self, context: PipelineContext) -> PipelineContext:
        result = self.parser.parse(context.natural_language)
        if not result["success"]:
            context.error = result["error"]
            context.failed_stage = self.name
            return context
        context.query_ir = result["data"]
        return context
