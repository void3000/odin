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
        self.summarizer = summarizer

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

    STAGE_MESSAGES = {
        "parse": "Parsing query...",
        "validate": "Validating...",
        "build": "Building query...",
        "execute": "Running query...",
        "summarize": "Summarizing results...",
    }

    def process_query_stream(self, natural_language: str, callback, conversation_history=None) -> None:
        """Process a query with streaming callbacks for status and tokens.

        Args:
            natural_language: The user's question
            callback: Function(event_type, data) called for each event.
                      event_type is "status", "token", or "done".
            conversation_history: Optional conversation history
        """
        logger.info(f"Processing query (streaming): {natural_language}")

        context = PipelineContext(
            natural_language=natural_language,
            source=self.source,
            schema=self.schema,
            conversation_history=conversation_history,
        )

        # Run all steps except summarize
        non_summary_steps = [s for s in self.steps if s.name != "summarize"]
        for step in non_summary_steps:
            msg = self.STAGE_MESSAGES.get(step.name, f"Running {step.name}...")
            callback("status", {"stage": step.name, "message": msg})
            context = step.execute(context)
            if context.error:
                # Surface parse/validate errors as friendly messages
                if context.failed_stage in ("parse", "validate"):
                    callback("token", {"content": context.error})
                    callback("done", {"success": True})
                else:
                    callback("token", {"content": "Sorry, I wasn't able to process that query. Please try rephrasing your question."})
                    logger.error(f"Pipeline failed at {context.failed_stage}: {context.error}")
                    callback("done", {"success": False})
                return

        # Stream the summarize step
        callback("status", {"stage": "summarize", "message": "Summarizing results..."})
        try:
            for token in self.summarizer.summarize_stream(
                context.natural_language, context.rows, context.sql
            ):
                callback("token", {"content": token})
            callback("done", {"success": True})
        except Exception as e:
            logger.error(f"Streaming summarization failed: {e}")
            callback("token", {"content": "Sorry, I wasn't able to summarize the results."})
            callback("done", {"success": False})

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
