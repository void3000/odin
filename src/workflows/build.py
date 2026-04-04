"""BuildWorkflow — converts validated QueryIR to a native query via the source."""

from src.logging_config import get_component_logger
from src.workflows.base import Workflow, PipelineContext

logger = get_component_logger("query_builder")


class BuildWorkflow(Workflow):
    name = "build"

    def __init__(self, default_limit: int = 100):
        self.default_limit = default_limit

    def run(self, context: PipelineContext) -> PipelineContext:
        if context.query_ir and context.query_ir.limit is None:
            context.query_ir.limit = self.default_limit

        logger.info(f"Building query for table: {context.query_ir.source.table}")
        logger.debug("QueryIR:\n%s", context.query_ir.model_dump_json(indent=2))

        context.native_query = context.source.build_query(context.query_ir)
        # Store sql/params for logging if available
        if hasattr(context.native_query, "sql"):
            context.sql = context.native_query.sql
            context.params = getattr(context.native_query, "params", None)
            logger.debug("Generated SQL: %s", context.sql)
            logger.debug("Params: %s", context.params)
        return context
