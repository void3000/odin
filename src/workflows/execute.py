"""ExecuteWorkflow — executes SQL against the database."""

from src.executor.connectors.sqlite import SQLiteConnector
from src.executor.errors import DatabaseError
from src.workflows.base import Workflow, PipelineContext


class ExecuteWorkflow(Workflow):
    name = "execute"

    def __init__(self, db_path: str):
        self.db_path = db_path

    def run(self, context: PipelineContext) -> PipelineContext:
        connector = SQLiteConnector(database=self.db_path)
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
