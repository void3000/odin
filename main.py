"""
Odin LLM-to-SQL Pipeline - Main Entry Point

This demonstrates the complete pipeline:
1. Natural language query input
2. LLM converts NL to IR (Intermediate Representation)
3. Query building (SQLite)
4. Query execution
5. Result display
"""
import os
import logging
from datetime import datetime

# Custom formatter matching: YYYY-MM-DD HH:MM:SS  [LEVEL] message
class OdinFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        # Format: 2026-03-30 17:56:07
        dt = datetime.fromtimestamp(record.created)
        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')}"

    def format(self, record):
        # Format: YYYY-MM-DD HH:MM:SS  [LEVEL] message
        timestamp = self.formatTime(record)
        level = record.levelname
        message = record.getMessage()
        return f"{timestamp}  [{level}] {message}"

def setup_logging(level=logging.INFO):
    """Configure logging with the Odin format."""
    logger = logging.getLogger("odin")
    logger.setLevel(level)

    # Clear any existing handlers
    if logger.handlers:
        logger.handlers.clear()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(OdinFormatter())
    logger.addHandler(console_handler)

    return logger

# Setup logging at module level
logger = setup_logging(logging.INFO)

from src.ir.models import (
    QueryIR,
    TableSource,
    FieldExpr,
    ConditionExpr,
    LogicalExpr,
    JoinExpr,
    OrderExpr,
)
from src.query.postgresql import PostgreSQLBuilder
from src.executor.executor import QueryExecutor
from src.executor.connectors.sqlite import SQLiteConnector
from src.llm.nl_to_ir import NaturalLanguageToIR
from src.schema.extractor import SQLiteSchemaExtractor


def run_natural_language_demo(nl_converter, builder, executor):
    """Demo: Natural Language to SQL conversion."""
    logger.info("=" * 80)
    logger.info("NATURAL LANGUAGE QUERY DEMO")
    logger.info("=" * 80)

    queries = [
        "Show me all artists",
        "Find AC/DC's albums",
        "Show rock tracks longer than 5 minutes",
    ]

    for nl_query in queries:
        logger.info(f"\nNatural Language: \"{nl_query}\"")
        logger.info("-" * 80)

        try:
            # Step 1: NL → IR (using LLM)
            logger.debug(f"Converting natural language to IR...")
            query_ir = nl_converter.convert(nl_query, nl_converter.schema)
            logger.info("IR Generated")

            # Step 2: IR → SQL
            logger.debug(f"Building SQL from IR...")
            query_result = builder.build(query_ir)
            logger.info(f"SQL Generated:\n{query_result.query['sql']}")

            if query_result.query['params']:
                logger.debug(f"Parameters: {query_result.query['params']}")

            # Step 3: Execute
            logger.debug("Executing query...")
            result = executor.execute(query_result)
            logger.info(f"Results ({len(result.rows)} rows):")

            # Show first 3 rows
            for i, row in enumerate(result.rows[:3]):
                logger.info(f"  {i+1}. {row}")

            if len(result.rows) > 3:
                logger.info(f"  ... and {len(result.rows) - 3} more")

        except Exception as e:
            logger.error(f"Error: {e}")


def main():
    # Connection string for Chinook sample database
    db_path = "/home/void-3000/.local/share/DBeaverData/workspace6/.metadata/sample-database-sqlite-1/Chinook.db"

    logger.info("=" * 80)
    logger.info("Odin LLM-to-SQL Pipeline - SQLite Chinook Database Demo")
    logger.info("=" * 80)

    # Initialize connector and executor
    logger.info(f"Connecting to: {db_path}")
    connector = SQLiteConnector(database=db_path)
    executor = QueryExecutor(connector=connector)
    builder = PostgreSQLBuilder()

    # Extract database schema for LLM context
    logger.info("Extracting database schema...")
    schema_extractor = SQLiteSchemaExtractor(db_path)
    schema = schema_extractor.extract_schema()
    logger.info(f"Found {len(schema.tables)} tables")

    # Initialize LM Studio converter
    nl_converter = None
    logger.info("Initializing LM Studio converter...")
    try:
        nl_converter = NaturalLanguageToIR(api_key="lmstudio")
        nl_converter.schema = schema  # Store schema for demo function
        logger.info("LM Studio ready (http://localhost:1234)")
    except Exception as e:
        logger.warning(f"LM Studio initialization failed: {e}")
        logger.warning("  Make sure LM Studio is running on port 1234")
        logger.warning("  Natural language demo will be skipped")

    try:
        connector.connect()
        logger.info("Connected successfully")

        # Run Natural Language Demo (if available)
        if nl_converter:
            run_natural_language_demo(nl_converter, builder, executor)
        else:
            logger.warning("Skipping Natural Language demo (LM Studio not available)")

        # Manual IR Examples
        logger.info("=" * 80)
        logger.info("MANUAL IR CONSTRUCTION DEMO (Programmatic Queries)")
        logger.info("=" * 80)

        # Example 1: Get all artists
        logger.info("-" * 80)
        logger.info("Example 1: Get all artists (limited to 5)")
        logger.info("-" * 80)

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Artist"),
            fields=[
                FieldExpr(field="ArtistId", alias="id"),
                FieldExpr(field="Name", alias="artist_name"),
            ],
            limit=5
        )

        # Build query using PostgreSQL builder (will be auto-converted to SQLite)
        builder = PostgreSQLBuilder()
        query_result = builder.build(query_ir)

        logger.info(f"Generated SQL: {query_result.query['sql']}")

        # Execute query
        result = executor.execute(query_result)

        logger.info(f"Results ({result.rowcount} rows):")
        for row in result.rows:
            logger.info(f"  {row}")

        # Example 2: Filter albums by artist
        logger.info("-" * 80)
        logger.info("Example 2: Get albums by AC/DC (ArtistId = 1)")
        logger.info("-" * 80)

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Album"),
            fields=[
                FieldExpr(field="AlbumId", alias="id"),
                FieldExpr(field="Title", alias="album_title"),
                FieldExpr(field="ArtistId", alias="artist_id"),
            ],
            filters=ConditionExpr(
                field="ArtistId",
                op="=",
                value=1
            )
        )

        query_result = builder.build(query_ir)

        logger.info(f"Generated SQL: {query_result.query['sql']}")
        logger.debug(f"Parameters: {query_result.query['params']}")

        result = executor.execute(query_result)

        logger.info(f"Results ({result.rowcount} rows):")
        for row in result.rows:
            logger.info(f"  {row}")

        # Example 3: Search tracks with LIKE
        logger.info("-" * 80)
        logger.info("Example 3: Search tracks containing 'Love'")
        logger.info("-" * 80)

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Track"),
            fields=[
                FieldExpr(field="TrackId", alias="id"),
                FieldExpr(field="Name", alias="track_name"),
            ],
            filters=ConditionExpr(
                field="Name",
                op="LIKE",
                value="%Love%"
            ),
            limit=5
        )

        query_result = builder.build(query_ir)

        logger.info(f"Generated SQL: {query_result.query['sql']}")
        logger.debug(f"Parameters: {query_result.query['params']}")

        result = executor.execute(query_result)

        logger.info(f"Results ({result.rowcount} rows):")
        for row in result.rows:
            logger.info(f"  {row}")

        # Example 4: INNER JOIN - Artists and Albums
        logger.info("-" * 80)
        logger.info("Example 4: INNER JOIN - AC/DC's Albums")
        logger.info("-" * 80)

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Artist"),
            fields=[
                FieldExpr(field="Name", table="Artist", alias="artist"),
                FieldExpr(field="Title", table="Album", alias="album"),
            ],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="Album",
                    on=ConditionExpr(
                        field="ArtistId",
                        table="Artist",
                        op="=",
                        value={"field": "ArtistId", "table": "Album"}
                    )
                )
            ],
            filters=ConditionExpr(
                field="Name",
                table="Artist",
                op="=",
                value="AC/DC"
            )
        )

        query_result = builder.build(query_ir)

        logger.info(f"Generated SQL:\n{query_result.query['sql']}")
        logger.debug(f"Parameters: {query_result.query['params']}")

        result = executor.execute(query_result)

        logger.info(f"Results ({len(result.rows)} rows):")
        for row in result.rows:
            logger.info(f"  {row['artist']:20} - {row['album']}")

        # Example 5: Triple JOIN - Artists → Albums → Tracks
        logger.info("-" * 80)
        logger.info("Example 5: Triple JOIN - Rock songs over 4 minutes")
        logger.info("-" * 80)

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Artist"),
            fields=[
                FieldExpr(field="Name", table="Artist", alias="artist"),
                FieldExpr(field="Title", table="Album", alias="album"),
                FieldExpr(field="Name", table="Track", alias="track"),
                FieldExpr(field="Milliseconds", table="Track", alias="duration_ms"),
            ],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="Album",
                    on=ConditionExpr(
                        field="ArtistId",
                        table="Artist",
                        op="=",
                        value={"field": "ArtistId", "table": "Album"}
                    )
                ),
                JoinExpr(
                    type="INNER",
                    table="Track",
                    on=ConditionExpr(
                        field="AlbumId",
                        table="Album",
                        op="=",
                        value={"field": "AlbumId", "table": "Track"}
                    )
                )
            ],
            filters=LogicalExpr(
                logic="AND",
                conditions=[
                    ConditionExpr(
                        field="Name",
                        table="Track",
                        op="LIKE",
                        value="%Rock%"
                    ),
                    ConditionExpr(
                        field="Milliseconds",
                        table="Track",
                        op=">",
                        value=240000  # > 4 minutes
                    )
                ]
            ),
            order_by=[
                OrderExpr(field="Milliseconds", table="Track", direction="DESC")
            ],
            limit=5
        )

        query_result = builder.build(query_ir)

        logger.info(f"Generated SQL:\n{query_result.query['sql']}")

        result = executor.execute(query_result)

        logger.info(f"Results ({len(result.rows)} rows):")
        for row in result.rows:
            duration_min = row['duration_ms'] / 60000
            logger.info(f"  {row['artist']:20} | {row['track']:45} | {duration_min:.2f} min")

        logger.info("=" * 80)
        logger.info("All examples completed successfully!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        connector.disconnect()
        logger.info("Database connection closed")


if __name__ == "__main__":
    main()
