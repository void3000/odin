"""
Tests for SQLite connector.

Tests the SQLite connector implementation with in-memory databases.
"""

import pytest
from src.executor.connectors.sqlite import SQLiteConnector
from src.executor.connector import RawResult
from src.executor.errors import ConnectionError, QueryError, TransactionError


class TestSQLiteConnector:
    """Test SQLite connector basic functionality."""

    def test_connect_in_memory(self):
        """Test connecting to in-memory database."""
        connector = SQLiteConnector()
        connector.connect()

        assert connector.is_connected()

        connector.disconnect()
        assert not connector.is_connected()

    def test_connect_file_based(self, tmp_path):
        """Test connecting to file-based database."""
        db_file = tmp_path / "test.db"
        connector = SQLiteConnector(database=str(db_file))
        connector.connect()

        assert connector.is_connected()
        assert db_file.exists()

        connector.disconnect()

    def test_execute_simple_query(self):
        """Test executing a simple query."""
        connector = SQLiteConnector()
        connector.connect()

        # Create table
        query = {"sql": "CREATE TABLE users (id INTEGER, name TEXT)", "params": []}
        connector.execute_query(query)

        # Insert data
        query = {"sql": "INSERT INTO users VALUES (?, ?)", "params": [1, "Alice"]}
        result = connector.execute_query(query)
        assert result.rowcount in [-1, 1]  # SQLite returns -1 for SELECT

        # Select data
        query = {"sql": "SELECT * FROM users", "params": []}
        result = connector.execute_query(query)

        assert isinstance(result, RawResult)
        assert len(result.rows) == 1
        assert result.rows[0] == (1, "Alice")
        assert result.columns == ["id", "name"]

        connector.disconnect()

    def test_postgresql_placeholder_conversion(self):
        """Test automatic conversion of PostgreSQL $1 placeholders to SQLite ?."""
        connector = SQLiteConnector()
        connector.connect()

        # Create table
        connector.execute_query({
            "sql": "CREATE TABLE users (id INTEGER, name TEXT, age INTEGER)",
            "params": []
        })

        # Insert with PostgreSQL-style placeholders
        query = {
            "sql": "INSERT INTO users VALUES ($1, $2, $3)",
            "params": [1, "Alice", 25]
        }
        result = connector.execute_query(query)
        assert result.rowcount in [-1, 1]  # SQLite returns -1 for SELECT

        # Query with PostgreSQL-style placeholders
        query = {
            "sql": "SELECT * FROM users WHERE age > $1",
            "params": [20]
        }
        result = connector.execute_query(query)

        assert len(result.rows) == 1
        assert result.rows[0] == (1, "Alice", 25)

        connector.disconnect()

    def test_execute_many(self):
        """Test executing multiple queries."""
        connector = SQLiteConnector()
        connector.connect()

        # Create table
        connector.execute_query({
            "sql": "CREATE TABLE users (id INTEGER, name TEXT)",
            "params": []
        })

        # Execute multiple inserts
        queries = [
            ({"sql": "INSERT INTO users VALUES (?, ?)", "params": [1, "Alice"]}, []),
            ({"sql": "INSERT INTO users VALUES (?, ?)", "params": [2, "Bob"]}, []),
            ({"sql": "INSERT INTO users VALUES (?, ?)", "params": [3, "Charlie"]}, []),
        ]

        results = connector.execute_many(queries)

        assert len(results) == 3
        assert all(r.rowcount == 1 for r in results)

        # Verify data
        result = connector.execute_query({
            "sql": "SELECT COUNT(*) FROM users",
            "params": []
        })
        assert result.rows[0][0] == 3

        connector.disconnect()

    def test_transaction_commit(self):
        """Test transaction commit."""
        connector = SQLiteConnector()
        connector.connect()

        # Create table
        connector.execute_query({
            "sql": "CREATE TABLE users (id INTEGER, name TEXT)",
            "params": []
        })

        # Begin transaction
        connector.begin_transaction()

        # Insert data
        connector.execute_query({
            "sql": "INSERT INTO users VALUES (?, ?)",
            "params": [1, "Alice"]
        })

        # Commit
        connector.commit()

        # Verify data persisted
        result = connector.execute_query({
            "sql": "SELECT * FROM users",
            "params": []
        })
        assert len(result.rows) == 1

        connector.disconnect()

    def test_transaction_rollback(self):
        """Test transaction rollback."""
        connector = SQLiteConnector()
        connector.connect()

        # Create table
        connector.execute_query({
            "sql": "CREATE TABLE users (id INTEGER, name TEXT)",
            "params": []
        })

        # Begin transaction
        connector.begin_transaction()

        # Insert data
        connector.execute_query({
            "sql": "INSERT INTO users VALUES (?, ?)",
            "params": [1, "Alice"]
        })

        # Rollback
        connector.rollback()

        # Verify data was rolled back
        result = connector.execute_query({
            "sql": "SELECT * FROM users",
            "params": []
        })
        assert len(result.rows) == 0

        connector.disconnect()

    def test_query_error(self):
        """Test that invalid queries raise QueryError."""
        connector = SQLiteConnector()
        connector.connect()

        with pytest.raises(QueryError, match="Query execution failed"):
            connector.execute_query({
                "sql": "SELECT * FROM nonexistent_table",
                "params": []
            })

        connector.disconnect()

    def test_transaction_error_no_active_transaction(self):
        """Test that committing without transaction raises error."""
        connector = SQLiteConnector()
        connector.connect()

        with pytest.raises(TransactionError, match="No transaction active"):
            connector.commit()

        connector.disconnect()

    def test_transaction_error_already_active(self):
        """Test that beginning transaction twice raises error."""
        connector = SQLiteConnector()
        connector.connect()

        connector.begin_transaction()

        with pytest.raises(TransactionError, match="Transaction already in progress"):
            connector.begin_transaction()

        connector.rollback()
        connector.disconnect()

    def test_get_metadata(self):
        """Test getting connector metadata."""
        connector = SQLiteConnector(database=":memory:")
        connector.connect()

        metadata = connector.get_metadata()

        assert metadata["database_type"] == "sqlite"
        assert metadata["driver"] == "sqlite3"
        assert metadata["connected"] is True
        assert metadata["database"] == ":memory:"
        assert "version" in metadata
        assert metadata["version"] is not None

        connector.disconnect()

    def test_connection_error_when_not_connected(self):
        """Test that executing query without connection raises error."""
        connector = SQLiteConnector()

        with pytest.raises(ConnectionError, match="Not connected to database"):
            connector.execute_query({"sql": "SELECT 1", "params": []})


class TestSQLiteConnectorWithPostgreSQLBuilder:
    """Test SQLite connector with PostgreSQL builder output."""

    def test_works_with_postgresql_builder_output(self):
        """Test that SQLite connector works with PostgreSQL builder output."""
        from src.ir.models import QueryIR, TableSource, FieldExpr, ConditionExpr
        from src.query.postgresql import PostgreSQLBuilder

        # Create connector and table
        connector = SQLiteConnector()
        connector.connect()

        connector.execute_query({
            "sql": "CREATE TABLE users (id INTEGER, name TEXT, status TEXT)",
            "params": []
        })

        # Insert test data
        connector.execute_query({
            "sql": "INSERT INTO users VALUES (?, ?, ?)",
            "params": [1, "Alice", "active"]
        })
        connector.execute_query({
            "sql": "INSERT INTO users VALUES (?, ?, ?)",
            "params": [2, "Bob", "inactive"]
        })

        # Build query with PostgreSQL builder (uses $1 placeholders)
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="active")
        )

        builder = PostgreSQLBuilder()
        query_result = builder.build(query_ir)

        # Execute with SQLite connector (auto-converts $1 to ?)
        result = connector.execute_query(query_result.query)

        assert len(result.rows) == 1
        assert result.rows[0][1] == "Alice"  # name column

        connector.disconnect()

    def test_complex_query_with_builder(self):
        """Test complex query with multiple conditions."""
        from src.ir.models import QueryIR, TableSource, FieldExpr, LogicalExpr, ConditionExpr, OrderExpr
        from src.query.postgresql import PostgreSQLBuilder

        # Setup
        connector = SQLiteConnector()
        connector.connect()

        connector.execute_query({
            "sql": "CREATE TABLE users (id INTEGER, name TEXT, age INTEGER, status TEXT)",
            "params": []
        })

        # Insert test data
        test_users = [
            (1, "Alice", 25, "active"),
            (2, "Bob", 30, "active"),
            (3, "Charlie", 20, "inactive"),
            (4, "David", 35, "active"),
        ]

        for user in test_users:
            connector.execute_query({
                "sql": "INSERT INTO users VALUES (?, ?, ?, ?)",
                "params": list(user)
            })

        # Build complex query
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="name"),
                FieldExpr(field="age")
            ],
            filters=LogicalExpr(
                logic="AND",
                conditions=[
                    ConditionExpr(field="age", op=">=", value=25),
                    ConditionExpr(field="status", op="=", value="active")
                ]
            ),
            order_by=[OrderExpr(field="age", direction="DESC")],
            limit=2
        )

        builder = PostgreSQLBuilder()
        query_result = builder.build(query_ir)

        # Execute
        result = connector.execute_query(query_result.query)

        # Should return David (35) and Bob (30), ordered by age DESC, limit 2
        assert len(result.rows) == 2
        assert result.rows[0][0] == "David"
        assert result.rows[0][1] == 35
        assert result.rows[1][0] == "Bob"
        assert result.rows[1][1] == 30

        connector.disconnect()


class TestSQLiteConnectorWithExecutor:
    """Test SQLite connector with QueryExecutor."""

    def test_executor_with_sqlite(self):
        """Test full pipeline: IR → Builder → Executor → SQLite."""
        from src.ir.models import QueryIR, TableSource, FieldExpr, ConditionExpr
        from src.query.postgresql import PostgreSQLBuilder
        from src.executor.executor import QueryExecutor

        # Setup database
        connector = SQLiteConnector()
        connector.connect()

        connector.execute_query({
            "sql": "CREATE TABLE users (id INTEGER, name TEXT, email TEXT)",
            "params": []
        })

        connector.execute_query({
            "sql": "INSERT INTO users VALUES (?, ?, ?)",
            "params": [1, "Alice", "alice@example.com"]
        })

        # Create executor
        executor = QueryExecutor(connector, auto_connect=False)

        # Build and execute query
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="name"),
                FieldExpr(field="email")
            ],
            filters=ConditionExpr(field="id", op="=", value=1)
        )

        builder = PostgreSQLBuilder()
        query_result = builder.build(query_ir)

        result = executor.execute(query_result)

        # Check ExecutionResult
        assert len(result.rows) == 1
        assert result.rows[0] == {"name": "Alice", "email": "alice@example.com"}
        assert result.columns == ["name", "email"]
        assert result.rowcount in [-1, 1]  # SQLite returns -1 for SELECT
        assert result.execution_time_ms > 0

        connector.disconnect()
