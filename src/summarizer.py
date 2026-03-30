"""
Result Summarizer.

Uses an LLM to summarize database query results into natural language.
"""

import json
import logging
from typing import Any, List, Tuple

from src.logging_config import get_component_logger

logger = get_component_logger("summarizer")

SUMMARIZE_SYSTEM_PROMPT = """You are a data analyst assistant. The user asked a question about a database, \
and a SQL query was executed to answer it. Your job is to summarize the results \
in clear, natural language that directly answers the user's question.

Rules:
- Answer the question directly and concisely.
- If the results are empty, say so in a helpful way related to the question.
- Do not mention SQL, queries, databases, or technical details.
- Do not use markdown formatting.
- Refer to the data naturally, as if you looked it up for the user."""


class ResultSummarizer:
    """Summarizes database query results into natural language using an LLM."""

    def __init__(self, llm_client: Any):
        """
        Initialize summarizer.

        Args:
            llm_client: LLMClient instance for generating summaries.
        """
        self.llm_client = llm_client
        logger.info("ResultSummarizer initialized")

    def summarize(
        self,
        question: str,
        results: List[Any],
        sql: str
    ) -> Tuple[bool, str]:
        """
        Summarize query results into natural language.

        Args:
            question: The original natural language question.
            results: List of result rows (dicts or tuples).
            sql: The SQL query that was executed.

        Returns:
            Tuple of (success, summary_or_error).
        """
        user_message = (
            f"User's question: {question}\n\n"
            f"SQL executed: {sql}\n\n"
            f"Results ({len(results)} rows):\n{json.dumps(results, indent=2, default=str)}"
        )

        logger.debug(f"Summarizing {len(results)} rows for question: {question}")

        success, response = self.llm_client.generate(SUMMARIZE_SYSTEM_PROMPT, user_message)

        if success:
            logger.info("Results summarized successfully")
        else:
            logger.error(f"Summarization failed: {response}")

        return success, response
