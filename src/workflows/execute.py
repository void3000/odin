"""ExecuteWorkflow — executes SQL against the database."""

from src.db import create_connector
from src.executor.errors import DatabaseError
from src.workflows.base import Workflow, PipelineContext


class ExecuteWorkflow(Workflow):
    name = "execute"

    def __init__(self, db_url: str, search_path: list[str] | None = None):
        self.db_url = db_url
        self.search_path = search_path

    def run(self, context: PipelineContext) -> PipelineContext:
        connector = create_connector(self.db_url, search_path=self.search_path)
        try:
            connector.connect()
            raw = connector.execute_query(
                {"sql": context.sql, "params": context.params or []}
            )
            context.rows = [
                dict(zip(raw.columns, row)) for row in raw.rows
            ]
        except DatabaseError as e:
            context.error = str(e)
            context.failed_stage = self.name
        finally:
            connector.disconnect()
        return context
