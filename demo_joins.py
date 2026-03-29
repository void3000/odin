"""
Demo: JOIN operations with Chinook database

This demonstrates complex JOIN queries working through the complete Odin pipeline.
"""
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


def demo_simple_join():
    """Demo 1: Simple INNER JOIN - Artists and their Albums"""
    print("=" * 80)
    print("Demo 1: INNER JOIN - Artists and Albums")
    print("=" * 80)

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

    return query_ir


def demo_triple_join():
    """Demo 2: Triple JOIN - Artists → Albums → Tracks"""
    print("\n" + "=" * 80)
    print("Demo 2: Triple JOIN - Artists → Albums → Tracks (Rock songs)")
    print("=" * 80)

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
                    value=250000  # > ~4 minutes
                )
            ]
        ),
        order_by=[
            OrderExpr(field="Milliseconds", table="Track", direction="DESC")
        ],
        limit=5
    )

    return query_ir


def demo_customer_analytics():
    """Demo 3: Customer Purchase Analytics"""
    print("\n" + "=" * 80)
    print("Demo 3: Customer Purchase Analytics (Top 5 purchases)")
    print("=" * 80)

    query_ir = QueryIR(
        operation="SELECT",
        source=TableSource(table="Customer"),
        fields=[
            FieldExpr(field="FirstName", table="Customer", alias="first_name"),
            FieldExpr(field="LastName", table="Customer", alias="last_name"),
            FieldExpr(field="InvoiceId", table="Invoice", alias="invoice_id"),
            FieldExpr(field="Total", table="Invoice", alias="total"),
        ],
        joins=[
            JoinExpr(
                type="INNER",
                table="Invoice",
                on=ConditionExpr(
                    field="CustomerId",
                    table="Customer",
                    op="=",
                    value={"field": "CustomerId", "table": "Invoice"}
                )
            )
        ],
        filters=ConditionExpr(
            field="Total",
            table="Invoice",
            op=">",
            value=10.00
        ),
        order_by=[
            OrderExpr(field="Total", table="Invoice", direction="DESC")
        ],
        limit=5
    )

    return query_ir


def main():
    db_path = "/home/void-3000/.local/share/DBeaverData/workspace6/.metadata/sample-database-sqlite-1/Chinook.db"

    connector = SQLiteConnector(database=db_path)
    executor = QueryExecutor(connector=connector)
    builder = PostgreSQLBuilder()

    try:
        connector.connect()
        print("Connected to Chinook database\n")

        # Demo 1: Simple JOIN
        query_ir = demo_simple_join()
        result_query = builder.build(query_ir)

        print("\nGenerated SQL:")
        print(result_query.query['sql'])
        print(f"\nParameters: {result_query.query['params']}")

        result = executor.execute(result_query)
        print(f"\nResults ({len(result.rows)} rows):")
        for row in result.rows:
            print(f"  {row['artist']:20} - {row['album']}")

        # Demo 2: Triple JOIN
        query_ir = demo_triple_join()
        result_query = builder.build(query_ir)

        print("\nGenerated SQL:")
        print(result_query.query['sql'])

        result = executor.execute(result_query)
        print(f"\nResults ({len(result.rows)} rows):")
        for row in result.rows:
            duration_min = row['duration_ms'] / 60000
            print(f"  {row['artist']:20} | {row['album']:30} | {row['track']:40} | {duration_min:.2f} min")

        # Demo 3: Customer Analytics
        query_ir = demo_customer_analytics()
        result_query = builder.build(query_ir)

        print("\nGenerated SQL:")
        print(result_query.query['sql'])

        result = executor.execute(result_query)
        print(f"\nResults ({len(result.rows)} rows):")
        for row in result.rows:
            print(f"  {row['first_name']} {row['last_name']:15} | Invoice #{row['invoice_id']:3} | ${row['total']:6.2f}")

        print("\n" + "=" * 80)
        print("All JOIN demos completed successfully!")
        print("=" * 80)

    finally:
        connector.disconnect()


if __name__ == "__main__":
    main()
