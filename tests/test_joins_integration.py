"""
Integration tests for JOIN operations with SQLite Chinook database.

These tests verify that the complete pipeline (IR → Builder → Executor → Connector)
works correctly with JOIN queries on the Chinook sample database.
"""
import pytest
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


# Path to Chinook database
CHINOOK_DB = "/home/void-3000/.local/share/DBeaverData/workspace6/.metadata/sample-database-sqlite-1/Chinook.db"


@pytest.fixture
def chinook_connector():
    """Fixture to provide connected Chinook database."""
    if not os.path.exists(CHINOOK_DB):
        pytest.skip(f"Chinook database not found at {CHINOOK_DB}")

    connector = SQLiteConnector(database=CHINOOK_DB)
    connector.connect()
    yield connector
    connector.disconnect()


@pytest.fixture
def executor(chinook_connector):
    """Fixture to provide QueryExecutor with Chinook connector."""
    return QueryExecutor(connector=chinook_connector)


@pytest.fixture
def builder():
    """Fixture to provide PostgreSQL builder."""
    return PostgreSQLBuilder()


class TestBasicJoins:
    """Test basic JOIN operations."""

    def test_inner_join_artist_album(self, builder, executor):
        """Test INNER JOIN between Artist and Album tables."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Artist"),
            fields=[
                FieldExpr(field="ArtistId", table="Artist", alias="artist_id"),
                FieldExpr(field="Name", table="Artist", alias="artist_name"),
                FieldExpr(field="Title", table="Album", alias="album_title"),
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
            limit=5
        )

        result_query = builder.build(query_ir)

        # Verify SQL structure
        sql = result_query.query['sql']
        assert 'INNER JOIN "Album"' in sql
        assert '"Artist"."ArtistId" = "Album"."ArtistId"' in sql

        # Execute and verify results
        result = executor.execute(result_query)
        assert len(result.rows) == 5

        # Verify row structure
        first_row = result.rows[0]
        assert 'artist_id' in first_row
        assert 'artist_name' in first_row
        assert 'album_title' in first_row

    def test_left_join_artist_album(self, builder, executor):
        """Test LEFT JOIN to include artists without albums."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Artist"),
            fields=[
                FieldExpr(field="ArtistId", table="Artist", alias="artist_id"),
                FieldExpr(field="Name", table="Artist", alias="artist_name"),
                FieldExpr(field="Title", table="Album", alias="album_title"),
            ],
            joins=[
                JoinExpr(
                    type="LEFT",
                    table="Album",
                    on=ConditionExpr(
                        field="ArtistId",
                        table="Artist",
                        op="=",
                        value={"field": "ArtistId", "table": "Album"}
                    )
                )
            ],
            limit=10
        )

        result_query = builder.build(query_ir)

        # Verify SQL structure
        sql = result_query.query['sql']
        assert 'LEFT JOIN "Album"' in sql

        # Execute query
        result = executor.execute(result_query)
        assert len(result.rows) <= 10


class TestMultipleJoins:
    """Test queries with multiple JOIN operations."""

    def test_three_table_join_artist_album_track(self, builder, executor):
        """Test joining Artist → Album → Track."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Artist"),
            fields=[
                FieldExpr(field="Name", table="Artist", alias="artist"),
                FieldExpr(field="Title", table="Album", alias="album"),
                FieldExpr(field="Name", table="Track", alias="track"),
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
            limit=5
        )

        result_query = builder.build(query_ir)

        # Verify SQL has both joins
        sql = result_query.query['sql']
        assert 'INNER JOIN "Album"' in sql
        assert 'INNER JOIN "Track"' in sql
        assert '"Artist"."ArtistId" = "Album"."ArtistId"' in sql
        assert '"Album"."AlbumId" = "Track"."AlbumId"' in sql

        # Execute and verify
        result = executor.execute(result_query)
        assert len(result.rows) == 5

        # Verify all three table columns present
        first_row = result.rows[0]
        assert 'artist' in first_row
        assert 'album' in first_row
        assert 'track' in first_row

    def test_four_table_join_with_invoice(self, builder, executor):
        """Test complex join: Track → Album → Artist + InvoiceLine."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Track"),
            fields=[
                FieldExpr(field="Name", table="Track", alias="track_name"),
                FieldExpr(field="Title", table="Album", alias="album_title"),
                FieldExpr(field="Name", table="Artist", alias="artist_name"),
                FieldExpr(field="UnitPrice", table="InvoiceLine", alias="price"),
            ],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="Album",
                    on=ConditionExpr(
                        field="AlbumId",
                        table="Track",
                        op="=",
                        value={"field": "AlbumId", "table": "Album"}
                    )
                ),
                JoinExpr(
                    type="INNER",
                    table="Artist",
                    on=ConditionExpr(
                        field="ArtistId",
                        table="Album",
                        op="=",
                        value={"field": "ArtistId", "table": "Artist"}
                    )
                ),
                JoinExpr(
                    type="INNER",
                    table="InvoiceLine",
                    on=ConditionExpr(
                        field="TrackId",
                        table="Track",
                        op="=",
                        value={"field": "TrackId", "table": "InvoiceLine"}
                    )
                )
            ],
            limit=5
        )

        result_query = builder.build(query_ir)

        # Execute query
        result = executor.execute(result_query)
        assert len(result.rows) <= 5

        # Verify all columns present
        if len(result.rows) > 0:
            first_row = result.rows[0]
            assert 'track_name' in first_row
            assert 'album_title' in first_row
            assert 'artist_name' in first_row
            assert 'price' in first_row


class TestJoinsWithFilters:
    """Test JOIN operations combined with WHERE clauses."""

    def test_join_with_simple_filter(self, builder, executor):
        """Test JOIN with WHERE filter on base table."""
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
                field="ArtistId",
                table="Artist",
                op="=",
                value=1  # AC/DC
            )
        )

        result_query = builder.build(query_ir)

        # Verify SQL has both JOIN and WHERE
        sql = result_query.query['sql']
        assert 'INNER JOIN' in sql
        assert 'WHERE' in sql
        assert result_query.query['params'] == [1]

        # Execute and verify
        result = executor.execute(result_query)

        # All results should be for AC/DC
        for row in result.rows:
            assert row['artist'] == 'AC/DC'

    def test_join_with_filter_on_joined_table(self, builder, executor):
        """Test JOIN with WHERE filter on joined table."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Album"),
            fields=[
                FieldExpr(field="Title", table="Album", alias="album"),
                FieldExpr(field="Name", table="Track", alias="track"),
            ],
            joins=[
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
            filters=ConditionExpr(
                field="Name",
                table="Track",
                op="LIKE",
                value="%Rock%"
            ),
            limit=5
        )

        result_query = builder.build(query_ir)

        # Execute query
        result = executor.execute(result_query)
        assert len(result.rows) <= 5

        # All tracks should contain "Rock"
        for row in result.rows:
            assert 'Rock' in row['track']

    def test_join_with_and_filter(self, builder, executor):
        """Test JOIN with AND condition in WHERE clause."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Track"),
            fields=[
                FieldExpr(field="Name", table="Track", alias="track"),
                FieldExpr(field="Milliseconds", table="Track", alias="duration"),
                FieldExpr(field="Title", table="Album", alias="album"),
            ],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="Album",
                    on=ConditionExpr(
                        field="AlbumId",
                        table="Track",
                        op="=",
                        value={"field": "AlbumId", "table": "Album"}
                    )
                )
            ],
            filters=LogicalExpr(
                logic="AND",
                conditions=[
                    ConditionExpr(
                        field="Milliseconds",
                        table="Track",
                        op=">",
                        value=300000  # > 5 minutes
                    ),
                    ConditionExpr(
                        field="Name",
                        table="Track",
                        op="LIKE",
                        value="%Love%"
                    )
                ]
            ),
            limit=5
        )

        result_query = builder.build(query_ir)

        # Execute query
        result = executor.execute(result_query)

        # Verify all results match both conditions
        for row in result.rows:
            assert row['duration'] > 300000
            assert 'Love' in row['track']


class TestJoinsWithOrderBy:
    """Test JOIN operations with ORDER BY clauses."""

    def test_join_with_order_by_base_table(self, builder, executor):
        """Test JOIN with ORDER BY on base table."""
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
            order_by=[
                OrderExpr(field="Name", table="Artist", direction="ASC")
            ],
            limit=5
        )

        result_query = builder.build(query_ir)

        # Verify SQL has ORDER BY
        sql = result_query.query['sql']
        assert 'ORDER BY' in sql

        # Execute and verify ordering
        result = executor.execute(result_query)
        assert len(result.rows) <= 5

        # Verify results are in ascending order
        artist_names = [row['artist'] for row in result.rows]
        assert artist_names == sorted(artist_names)

    def test_join_with_order_by_joined_table(self, builder, executor):
        """Test JOIN with ORDER BY on joined table."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Album"),
            fields=[
                FieldExpr(field="Title", table="Album", alias="album"),
                FieldExpr(field="Name", table="Track", alias="track"),
                FieldExpr(field="Milliseconds", table="Track", alias="duration"),
            ],
            joins=[
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
            order_by=[
                OrderExpr(field="Milliseconds", table="Track", direction="DESC")
            ],
            limit=10
        )

        result_query = builder.build(query_ir)

        # Execute and verify
        result = executor.execute(result_query)
        assert len(result.rows) <= 10

        # Verify descending order by duration
        durations = [row['duration'] for row in result.rows]
        assert durations == sorted(durations, reverse=True)

    def test_join_with_multiple_order_by(self, builder, executor):
        """Test JOIN with multiple ORDER BY columns."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Artist"),
            fields=[
                FieldExpr(field="Name", table="Artist", alias="artist"),
                FieldExpr(field="Title", table="Album", alias="album"),
                FieldExpr(field="AlbumId", table="Album", alias="album_id"),
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
            order_by=[
                OrderExpr(field="Name", table="Artist", direction="ASC"),
                OrderExpr(field="Title", table="Album", direction="ASC")
            ],
            limit=10
        )

        result_query = builder.build(query_ir)

        # Verify SQL structure
        sql = result_query.query['sql']
        assert 'ORDER BY' in sql
        assert '"Artist"."Name" ASC' in sql
        assert '"Album"."Title" ASC' in sql

        # Execute query
        result = executor.execute(result_query)
        assert len(result.rows) <= 10


class TestComplexJoinScenarios:
    """Test complex real-world JOIN scenarios."""

    def test_find_tracks_by_genre(self, builder, executor):
        """Test finding tracks by genre name (requires JOIN)."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Track"),
            fields=[
                FieldExpr(field="Name", table="Track", alias="track"),
                FieldExpr(field="Name", table="Genre", alias="genre"),
            ],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="Genre",
                    on=ConditionExpr(
                        field="GenreId",
                        table="Track",
                        op="=",
                        value={"field": "GenreId", "table": "Genre"}
                    )
                )
            ],
            filters=ConditionExpr(
                field="Name",
                table="Genre",
                op="=",
                value="Rock"
            ),
            limit=5
        )

        result_query = builder.build(query_ir)
        result = executor.execute(result_query)

        # All results should be Rock genre
        for row in result.rows:
            assert row['genre'] == 'Rock'

    def test_customer_purchases(self, builder, executor):
        """Test finding customer purchases (Customer → Invoice → InvoiceLine)."""
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
                field="CustomerId",
                table="Customer",
                op="=",
                value=1
            ),
            order_by=[
                OrderExpr(field="Total", table="Invoice", direction="DESC")
            ],
            limit=5
        )

        result_query = builder.build(query_ir)
        result = executor.execute(result_query)

        # Verify all results are for the same customer
        if len(result.rows) > 0:
            first_name = result.rows[0]['first_name']
            last_name = result.rows[0]['last_name']
            for row in result.rows:
                assert row['first_name'] == first_name
                assert row['last_name'] == last_name

    def test_tracks_never_purchased(self, builder, executor):
        """Test finding tracks that were never purchased (LEFT JOIN with NULL check)."""
        # Note: This would require IS NULL support in filters, which we'll test structurally
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="Track"),
            fields=[
                FieldExpr(field="Name", table="Track", alias="track"),
                FieldExpr(field="TrackId", table="InvoiceLine", alias="invoice_track"),
            ],
            joins=[
                JoinExpr(
                    type="LEFT",
                    table="InvoiceLine",
                    on=ConditionExpr(
                        field="TrackId",
                        table="Track",
                        op="=",
                        value={"field": "TrackId", "table": "InvoiceLine"}
                    )
                )
            ],
            limit=10
        )

        result_query = builder.build(query_ir)

        # Verify SQL structure has LEFT JOIN
        sql = result_query.query['sql']
        assert 'LEFT JOIN "InvoiceLine"' in sql

        # Execute query
        result = executor.execute(result_query)
        assert len(result.rows) <= 10
