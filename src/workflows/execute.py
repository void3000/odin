"""ExecuteWorkflow — executes a native query via the data source."""

from src.workflows.base import Workflow, PipelineContext


class ExecuteWorkflow(Workflow):
    name = "execute"

    def run(self, context: PipelineContext) -> PipelineContext:
        source = context.source
        try:
            if not source.is_connected():
                source.connect()
            result = source.execute(context.native_query)
            context.rows = result.rows
        except Exception as e:
            context.error = str(e)
            context.failed_stage = self.name
        finally:
            source.disconnect()
        return context
