"""
Query Orchestrator.

Coordinates the complete query processing pipeline using Workflow steps:
1. Parse natural language to IR
2. Validate IR against schema
3. Build SQL from validated IR
4. Execute SQL and return results
5. Summarize results using LLM
"""

from typing import Any, Dict, List

from src.ir.parser import IRParser
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
    """
    Orchestrates the complete query processing pipeline.

    Pipeline stages are Workflow instances chained together.
    Each stage reads from and writes to a shared PipelineContext.
    """

    def __init__(
        self,
        db_url: str,
        llm_client: Any,
        system_prompt: str,
        schema: Dict[str, Any],
        default_limit: int = 100,
    ):
        self.db_url = db_url
        self.schema = schema

        parser = IRParser(llm_client, system_prompt)
        summarizer = ResultSummarizer(llm_client)

        self.steps: List[Workflow] = [
            ParseWorkflow(parser),
            ValidateWorkflow(),
            BuildWorkflow(default_limit=default_limit),
            ExecuteWorkflow(db_url),
            SummarizeWorkflow(summarizer),
        ]

        logger.info(f"QueryOrchestrator initialized for database: {db_url}")
        logger.debug(f"Schema contains {len(schema)} tables")

    def process_query(self, natural_language: str) -> Dict[str, Any]:
        """Process a natural language query through the complete pipeline."""
        logger.info(f"Processing query: {natural_language}")

        context = PipelineContext(
            natural_language=natural_language,
            db_url=self.db_url,
            schema=self.schema,
        )

        for step in self.steps:
            context = step.execute(context)
            if context.error:
                break

        context.timings["total_ms"] = sum(context.timings.values())
        return self._to_result_dict(context)

    def _to_result_dict(self, context: PipelineContext) -> Dict[str, Any]:
        """Convert PipelineContext to the existing result dict format."""
        result: Dict[str, Any] = {
            "success": context.error is None,
            "error": context.error,
        }
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
