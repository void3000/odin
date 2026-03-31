"""BuildWorkflow — converts validated QueryIR to SQL."""

from src.query_builder import SQLBuilder
from src.workflows.base import Workflow, PipelineContext


class BuildWorkflow(Workflow):
    name = "build"

    def run(self, context: PipelineContext) -> PipelineContext:
        builder = SQLBuilder()
        context.sql, context.params = builder.build(context.query_ir)
        return context
