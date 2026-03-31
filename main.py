"""
Odin LLM-to-SQL Pipeline - Main Entry Point

Demonstrates the complete pipeline using QueryOrchestrator:
1. Natural language query input
2. LLM converts NL to IR (Intermediate Representation)
3. IR validation against schema
4. Query building (SQLite)
5. Query execution
6. LLM summarizes results
"""
import os
import logging
from datetime import datetime

# Custom formatter matching: YYYY-MM-DD HH:MM:SS  [LEVEL] message
class OdinFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created)
        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')}"

    def format(self, record):
        timestamp = self.formatTime(record)
        level = record.levelname
        message = record.getMessage()
        return f"{timestamp}  [{level}] {message}"

def setup_logging(level=logging.INFO):
    """Configure logging with the Odin format."""
    logger = logging.getLogger("odin")
    logger.setLevel(level)

    if logger.handlers:
        logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(OdinFormatter())
    logger.addHandler(console_handler)

    return logger

# Setup logging at module level
logger = setup_logging(logging.INFO)

# Set env var so src.logging_config doesn't override our level on import
os.environ.setdefault("ODIN_LOG_LEVEL", "INFO")

import json

from src.llm_client import LLMClient
from src.llm.nl_to_ir import NaturalLanguageToIR
from src.schema.extractor import SQLiteSchemaExtractor
from src.orchestrator import QueryOrchestrator


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Odin LLM-to-SQL Pipeline")
    parser.add_argument("--db", required=True, help="Database connection string")
    parser.add_argument("--query", action="append", help="Natural language query (can be repeated)")
    args = parser.parse_args()

    db_url = args.db

    logger.info("Odin LLM-to-SQL Pipeline")

    # Extract database schema
    logger.info(f"Connecting to: {db_url}")
    logger.info("Extracting database schema...")
    schema_extractor = SQLiteSchemaExtractor(db_url)
    schema = schema_extractor.extract_schema()
    logger.info(f"Found {len(schema.tables)} tables")

    # Initialize LLM client for local LM Studio
    logger.info("Initializing LM Studio LLM client...")
    llm_client = LLMClient(
        base_url="http://localhost:1234/v1",
        api_key="lmstudio",
        model="qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
        temperature=0.1,
    )
    logger.info("LM Studio ready (http://localhost:1234)")

    # Build system prompt with schema context
    nl_converter = NaturalLanguageToIR(api_key="lmstudio")
    system_prompt = nl_converter._build_system_prompt(schema)

    # Convert schema to validator format: {"table": {"columns": {"col": {"type": "..."}}}}
    validator_schema = {
        table.name: {
            "columns": {col.name: {"type": col.type} for col in table.columns}
        }
        for table in schema.tables
    }

    # Initialize orchestrator
    orchestrator = QueryOrchestrator(
        db_url=db_url,
        llm_client=llm_client,
        system_prompt=system_prompt,
        schema=validator_schema,
    )

    # Run natural language queries
    queries = args.query or [
        "Show me all artists",
        "Find AC/DC's albums",
        "Show rock tracks longer than 5 minutes",
    ]

    for nl_query in queries:
        logger.info("")
        logger.info(f"Query: \"{nl_query}\"")

        result = orchestrator.process_query(nl_query)
        logger.debug("Result:\n%s", json.dumps(result, indent=2, default=str))

        if result["success"]:
            logger.info(result["summary"])
        else:
            logger.error(f"Failed at stage '{result['metadata'].get('stage')}': {result['error']}")

    logger.info("")
    logger.info("All queries completed!")


if __name__ == "__main__":
    main()
