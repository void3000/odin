"""BuildWorkflow — converts validated QueryIR to SQL."""

from src.query_builder import SQLBuilder
from src.workflows.base import Workflow, PipelineContext


class BuildWorkflow(Workflow):
    name = "build"

    def __init__(self, default_limit: int = 100):
        self.default_limit = default_limit

    def run(self, context: PipelineContext) -> PipelineContext:
        if context.query_ir and context.query_ir.limit is None:
            context.query_ir.limit = self.default_limit
        builder = SQLBuilder()
        context.sql, context.params = builder.build(context.query_ir)
        return context
