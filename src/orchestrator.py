"""
Query Orchestrator.

Coordinates the complete query processing pipeline using Workflow steps.
"""

from typing import Any, Dict, List

from src.ir.parser import IRParser
from src.sources.base import DataSource
from src.summarizer import ResultSummarizer
from src.workflows import (
    Workflow,
    PipelineContext,
    ParseWorkflow,
    ValidateWorkflow,
    BuildWorkflow,
    ExecuteWorkflow,
    SummarizeWorkflow,
)
from src.logging_config import get_component_logger

logger = get_component_logger("orchestrator")


class QueryOrchestrator:
    """Orchestrates the complete query processing pipeline."""

    def __init__(
        self,
        source: DataSource,
        llm_client: Any,
        system_prompt: str,
        schema: Dict[str, Any],
        default_limit: int = 100,
    ):
        self.source = source
        self.schema = schema

        parser = IRParser(llm_client, system_prompt)
        summarizer = ResultSummarizer(llm_client)

        self.steps: List[Workflow] = [
            ParseWorkflow(parser),
            ValidateWorkflow(),
            BuildWorkflow(default_limit=default_limit),
            ExecuteWorkflow(),
            SummarizeWorkflow(summarizer),
        ]

        logger.info(f"QueryOrchestrator initialized for source: {source.name}")
        logger.debug(f"Schema contains {len(schema)} tables")

    def process_query(self, natural_language: str, conversation_history=None) -> Dict[str, Any]:
        """Process a natural language query through the complete pipeline."""
        logger.info(f"Processing query: {natural_language}")

        context = PipelineContext(
            natural_language=natural_language,
            source=self.source,
            schema=self.schema,
            conversation_history=conversation_history,
        )

        for step in self.steps:
            context = step.execute(context)
            if context.error:
                break

        context.timings["total_ms"] = sum(context.timings.values())
        return self._to_result_dict(context)

    def _to_result_dict(self, context: PipelineContext) -> Dict[str, Any]:
        """Convert PipelineContext to the existing result dict format.

        If the pipeline failed at the parse stage (e.g., the LLM declined
        an unsupported operation), return the error as a friendly summary
        instead of exposing internal state to the client.
        """
        if context.error and context.failed_stage in ("parse", "validate"):
            # Parse/validate failures often contain useful info for the user
            # (e.g., "INSERT not supported" or "table 'artists' not found")
            # Surface them as a helpful response, not an error.
            return {
                "success": True,
                "summary": context.error,
            }

        result: Dict[str, Any] = {
            "success": context.error is None,
        }
        if context.error:
            result["summary"] = "Sorry, I wasn't able to process that query. Please try rephrasing your question."
            logger.error(f"Pipeline failed at {context.failed_stage}: {context.error}")
        if context.summary:
            result["summary"] = context.summary
        return result

    def get_schema_summary(self) -> Dict[str, Any]:
        """Get a summary of the database schema."""
        summary = {}
        for table_name, table_info in self.schema.items():
            columns = table_info.get("columns", {})
            summary[table_name] = {
                "column_count": len(columns),
                "columns": list(columns.keys()),
            }
        return summary
