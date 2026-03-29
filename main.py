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
    print("\n" + "=" * 80)
    print("NATURAL LANGUAGE QUERY DEMO")
    print("=" * 80)

    queries = [
        "Show me all artists",
        "Find AC/DC's albums",
        "Show rock tracks longer than 5 minutes",
    ]

    for nl_query in queries:
        print(f"\n🗣️  Natural Language: \"{nl_query}\"")
        print("-" * 80)

        try:
            # Step 1: NL → IR (using LLM)
            query_ir = nl_converter.convert(nl_query, nl_converter.schema)
            print(f"✓ IR Generated")

            # Step 2: IR → SQL
            query_result = builder.build(query_ir)
            print(f"✓ SQL Generated:\n{query_result.query['sql']}")

            if query_result.query['params']:
                print(f"Parameters: {query_result.query['params']}")

            # Step 3: Execute
            result = executor.execute(query_result)
            print(f"\n✓ Results ({len(result.rows)} rows):")

            # Show first 3 rows
            for i, row in enumerate(result.rows[:3]):
                print(f"  {i+1}. {row}")

            if len(result.rows) > 3:
                print(f"  ... and {len(result.rows) - 3} more")

        except Exception as e:
            print(f"❌ Error: {e}")


def main():
    # Connection string for Chinook sample database
    db_path = "/home/void-3000/.local/share/DBeaverData/workspace6/.metadata/sample-database-sqlite-1/Chinook.db"

    print("=" * 80)
    print("Odin LLM-to-SQL Pipeline - SQLite Chinook Database Demo")
    print("=" * 80)
    print()

    # Initialize connector and executor
    print(f"Connecting to: {db_path}")
    connector = SQLiteConnector(database=db_path)
    executor = QueryExecutor(connector=connector)
    builder = PostgreSQLBuilder()

    # Extract database schema for LLM context
    print("Extracting database schema...")
    schema_extractor = SQLiteSchemaExtractor(db_path)
    schema = schema_extractor.extract_schema()
    print(f"✓ Found {len(schema.tables)} tables")

    # Initialize LM Studio converter
    nl_converter = None
    print("Initializing LM Studio converter...")
    try:
        nl_converter = NaturalLanguageToIR(api_key="lmstudio")
        nl_converter.schema = schema  # Store schema for demo function
        print("✓ LM Studio ready (http://localhost:1234)")
    except Exception as e:
        print(f"⚠ LM Studio initialization failed: {e}")
        print("  Make sure LM Studio is running on port 1234")
        print("  Natural language demo will be skipped")

    try:
        connector.connect()
        print("✓ Connected successfully")

        # Run Natural Language Demo (if available)
        if nl_converter:
            run_natural_language_demo(nl_converter, builder, executor)
        else:
            print("\n⚠ Skipping Natural Language demo (LM Studio not available)")

        # Manual IR Examples
        print("\n" + "=" * 80)
        print("MANUAL IR CONSTRUCTION DEMO (Programmatic Queries)")
        print("=" * 80)
        print()

        # Example 1: Get all artists
        print("-" * 80)
        print("Example 1: Get all artists (limited to 5)")
        print("-" * 80)

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

        print(f"Generated SQL: {query_result.query['sql']}")
        print()

        # Execute query
        result = executor.execute(query_result)

        print(f"Results ({result.rowcount} rows):")
        for row in result.rows:
            print(f"  {row}")
        print()

        # Example 2: Filter albums by artist
        print("-" * 80)
        print("Example 2: Get albums by AC/DC (ArtistId = 1)")
        print("-" * 80)

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

        print(f"Generated SQL: {query_result.query['sql']}")
        print(f"Parameters: {query_result.query['params']}")
        print()

        result = executor.execute(query_result)

        print(f"Results ({result.rowcount} rows):")
        for row in result.rows:
            print(f"  {row}")
        print()

        # Example 3: Search tracks with LIKE
        print("-" * 80)
        print("Example 3: Search tracks containing 'Love'")
        print("-" * 80)

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

        print(f"Generated SQL: {query_result.query['sql']}")
        print(f"Parameters: {query_result.query['params']}")
        print()

        result = executor.execute(query_result)

        print(f"Results ({result.rowcount} rows):")
        for row in result.rows:
            print(f"  {row}")
        print()

        # Example 4: INNER JOIN - Artists and Albums
        print("-" * 80)
        print("Example 4: INNER JOIN - AC/DC's Albums")
        print("-" * 80)

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

        print(f"Generated SQL:\n{query_result.query['sql']}")
        print(f"\nParameters: {query_result.query['params']}")
        print()

        result = executor.execute(query_result)

        print(f"Results ({len(result.rows)} rows):")
        for row in result.rows:
            print(f"  {row['artist']:20} - {row['album']}")
        print()

        # Example 5: Triple JOIN - Artists → Albums → Tracks
        print("-" * 80)
        print("Example 5: Triple JOIN - Rock songs over 4 minutes")
        print("-" * 80)

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

        print(f"Generated SQL:\n{query_result.query['sql']}")
        print()

        result = executor.execute(query_result)

        print(f"Results ({len(result.rows)} rows):")
        for row in result.rows:
            duration_min = row['duration_ms'] / 60000
            print(f"  {row['artist']:20} | {row['track']:45} | {duration_min:.2f} min")
        print()

        print("=" * 80)
        print("All examples completed successfully!")
        print("=" * 80)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        connector.disconnect()
        print("\nDatabase connection closed")


if __name__ == "__main__":
    main()
