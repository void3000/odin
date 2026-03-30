"""
Query Orchestrator.

Coordinates the complete query processing pipeline:
1. Parse natural language to IR
2. Validate IR against schema
3. Build SQL from validated IR
4. Execute SQL and return results
5. Summarize results using LLM
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.ir.models import QueryIR
from src.ir.parser import IRParser
from src.ir.validator import IRValidator
from src.query_builder import SQLBuilder
from src.summarizer import ResultSummarizer
from src.executor.connectors.sqlite import SQLiteConnector
from src.executor.errors import DatabaseError
from src.logging_config import get_component_logger

logger = get_component_logger("orchestrator")


class QueryOrchestrator:
    """
    Orchestrates the complete query processing pipeline.

    Pipeline stages:
        1. Parse: Natural language -> IR (using LLM)
        2. Validate: IR against database schema
        3. Build: IR -> SQL query
        4. Execute: SQL -> Results
        5. Summarize: Results -> Natural language summary (using LLM)
    """

    def __init__(
        self,
        db_path: str,
        llm_client: Any,
        system_prompt: str,
        schema: Dict[str, Any]
    ):
        """
        Initialize orchestrator with all pipeline components.

        Args:
            db_path: Path to SQLite database
            llm_client: LLM client for parsing natural language
            system_prompt: System prompt for the LLM parser
            schema: Database schema from design document
        """
        self.db_path = db_path
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.schema = schema

        # Initialize pipeline components
        self.parser = IRParser(llm_client, system_prompt)
        self.validator = IRValidator(schema)
        self.builder = SQLBuilder()
        self.summarizer = ResultSummarizer(llm_client)

        logger.info(f"QueryOrchestrator initialized for database: {db_path}")
        logger.debug(f"Schema contains {len(schema)} tables")

    def process_query(
        self,
        natural_language: str,
    ) -> Dict[str, Any]:
        """
        Process a natural language query through the complete pipeline.

        Args:
            natural_language: User's question in natural language

        Returns:
            Dict with success status, summary, and metadata
        """
        logger.info(f"Processing query: {natural_language}")
        result = {
            "success": False,
            "error": None,
            "metadata": {}
        }

        try:
            # Stage 1: Parse natural language to IR
            logger.info("Stage 1: Parsing natural language to IR...")
            parse_result = self.parser.parse(natural_language)

            if not parse_result["success"]:
                result["error"] = parse_result["error"]
                result["metadata"]["stage"] = "parse"
                logger.error(f"Parse failed: {parse_result['error']}")
                return result

            query_ir = parse_result["data"]
            result["metadata"]["ir"] = query_ir.model_dump()
            logger.info("Stage 1 complete: IR parsed successfully")

            # Stage 2: Validate IR against schema
            logger.info("Stage 2: Validating IR against schema...")
            validation_errors = self.validator.validate_query(query_ir)

            if validation_errors:
                error_msg = "Validation failed:\n" + "\n".join(f"- {e}" for e in validation_errors)
                result["error"] = error_msg
                result["metadata"]["stage"] = "validate"
                logger.error(error_msg)
                return result

            logger.info("Stage 2 complete: IR validated successfully")

            # Stage 3: Build SQL from IR
            logger.info("Stage 3: Building SQL from IR...")
            sql, params = self.builder.build(query_ir)
            result["metadata"]["sql"] = sql
            result["metadata"]["params"] = params
            logger.debug(f"Generated SQL: {sql}")
            logger.info("Stage 3 complete: SQL built successfully")

            # Stage 4: Execute SQL query
            logger.info("Stage 4: Executing SQL query...")
            connector = SQLiteConnector(database=self.db_path)
            try:
                connector.connect()
                raw_result = connector.execute_query(
                    {"sql": sql, "params": params or []}
                )
                exec_result = [
                    dict(zip(raw_result.columns, row))
                    for row in raw_result.rows
                ]
            except DatabaseError as e:
                result["error"] = str(e)
                result["metadata"]["stage"] = "execute"
                logger.error(f"Execution failed: {e}")
                return result
            finally:
                connector.disconnect()

            result["metadata"]["row_count"] = len(exec_result)
            logger.info(f"Stage 4 complete: Query executed successfully, returned {len(exec_result)} rows")

            # Stage 5: Summarize results using LLM
            logger.info("Stage 5: Summarizing results...")
            summ_success, summary = self.summarizer.summarize(
                natural_language, exec_result, sql
            )

            if not summ_success:
                result["error"] = summary
                result["metadata"]["stage"] = "summarize"
                logger.error(f"Summarization failed: {summary}")
                return result

            result["success"] = True
            result["summary"] = summary
            result["metadata"]["stage"] = "complete"
            logger.info("Stage 5 complete: Results summarized successfully")

        except Exception as e:
            error_msg = f"Unexpected error in orchestrator: {str(e)}"
            result["error"] = error_msg
            logger.error(error_msg, exc_info=True)

        return result

    def get_schema_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the database schema.

        Returns:
            Dict with table names and column counts
        """
        summary = {}
        for table_name, table_info in self.schema.items():
            columns = table_info.get("columns", {})
            summary[table_name] = {
                "column_count": len(columns),
                "columns": list(columns.keys())
            }
        return summary
