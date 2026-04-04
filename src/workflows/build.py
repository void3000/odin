"""BuildWorkflow — converts validated QueryIR to a native query via the source."""

from src.workflows.base import Workflow, PipelineContext


class BuildWorkflow(Workflow):
    name = "build"

    def __init__(self, default_limit: int = 100):
        self.default_limit = default_limit

    def run(self, context: PipelineContext) -> PipelineContext:
        if context.query_ir and context.query_ir.limit is None:
            context.query_ir.limit = self.default_limit
        context.native_query = context.source.build_query(context.query_ir)
        # Store sql/params for logging if available
        if hasattr(context.native_query, "sql"):
            context.sql = context.native_query.sql
            context.params = getattr(context.native_query, "params", None)
        return context
