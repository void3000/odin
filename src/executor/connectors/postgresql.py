"""
PostgreSQL connector implementation.

Wraps psycopg2 driver and implements DatabaseConnector protocol.
"""

from typing import Any, List, Tuple, Optional

from ..connector import DatabaseConnector, RawResult
from ..errors import (
    ConnectionError as DBConnectionError,
    QueryError,
    TransactionError
)


class PostgreSQLConnector:
    """
    PostgreSQL connector using psycopg2.

    Implements DatabaseConnector protocol for PostgreSQL databases.

    Features:
    - Connection management
    - Parameterized queries ($1, $2, ... style)
    - Transaction support
    - Error translation from psycopg2 to common exceptions
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 5432,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None
    ):
        """Initialize PostgreSQL connector.

        Can use either connection_string OR individual parameters.

        Args:
            connection_string: PostgreSQL connection string
                (e.g., "postgresql://user:pass@localhost/db")
            host: Database host
            port: Database port (default 5432)
            database: Database name
            user: Username
            password: Password

        Raises:
            ValueError: If neither connection_string nor host/database provided
        """
        if connection_string:
            self.connection_string = connection_string
        elif host and database:
            # Build connection string from parameters
            auth = f"{user}:{password}@" if user else ""
            self.connection_string = (
                f"postgresql://{auth}{host}:{port}/{database}"
            )
        else:
            raise ValueError(
                "Must provide either connection_string or host/database"
            )

        self.conn = None
        self.cursor = None
        self._in_transaction = False

    def connect(self) -> None:
        """Establish PostgreSQL connection.

        Raises:
            ConnectionError: If connection fails
        """
        try:
            import psycopg2
            self.conn = psycopg2.connect(self.connection_string)
            self.cursor = self.conn.cursor()
        except ImportError:
            raise DBConnectionError(
                "psycopg2 not installed. Install with: pip install psycopg2-binary"
            )
        except Exception as e:
            raise DBConnectionError(
                f"Failed to connect to PostgreSQL: {str(e)}",
                original=e
            )

    def disconnect(self) -> None:
        """Close PostgreSQL connection."""
        if self.cursor:
            try:
                self.cursor.close()
            except Exception:
                pass
            self.cursor = None

        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

        self._in_transaction = False

    def is_connected(self) -> bool:
        """Check if connected to PostgreSQL.

        Returns:
            True if connection is active
        """
        if not self.conn:
            return False

        try:
            # Test connection with simple query
            cursor = self.conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            return True
        except Exception:
            return False

    def execute_query(self, query: Any, params: List[Any] = None) -> RawResult:
        """Execute single PostgreSQL query.

        Args:
            query: SQL query (dict with 'sql' and 'params' keys, or string)
            params: Query parameters (optional, overrides query['params'])

        Returns:
            RawResult with rows, columns, rowcount

        Raises:
            ConnectionError: If not connected
            QueryError: If query execution fails
        """
        if not self.conn or not self.cursor:
            raise DBConnectionError("Not connected to database")

        # Extract SQL and params from query
        if isinstance(query, dict):
            sql = query.get("sql", query)
            if params is None:
                params = query.get("params", [])
        else:
            sql = str(query)
            if params is None:
                params = []

        try:
            # Execute query
            self.cursor.execute(sql, params)

            # Get results
            try:
                rows = self.cursor.fetchall()
                columns = [desc[0] for desc in self.cursor.description]
            except Exception:
                # Query didn't return results (INSERT, UPDATE, DELETE)
                rows = []
                columns = []

            rowcount = self.cursor.rowcount

            return RawResult(
                rows=rows,
                columns=columns,
                rowcount=rowcount
            )

        except Exception as e:
            # Translate psycopg2 errors to common exceptions
            error_msg = str(e)

            # Check if it's a connection error
            if "connection" in error_msg.lower() or "closed" in error_msg.lower():
                raise DBConnectionError(
                    f"Connection lost during query execution: {error_msg}",
                    original=e
                )

            # Otherwise it's a query error
            raise QueryError(
                message=f"Query execution failed: {error_msg}",
                sql=sql,
                params=params,
                original=e
            )

    def execute_many(
        self,
        queries: List[Tuple[str, List[Any]]]
    ) -> List[RawResult]:
        """Execute multiple PostgreSQL queries sequentially.

        Args:
            queries: List of (sql, params) tuples

        Returns:
            List of RawResult, one per query

        Raises:
            ConnectionError: If not connected
            QueryError: If any query fails
        """
        results = []

        for sql, params in queries:
            result = self.execute_query(sql, params)
            results.append(result)

        return results

    def begin_transaction(self) -> None:
        """Start PostgreSQL transaction.

        Raises:
            TransactionError: If transaction cannot be started
            ConnectionError: If not connected
        """
        if not self.conn:
            raise DBConnectionError("Not connected to database")

        if self._in_transaction:
            raise TransactionError("Transaction already in progress")

        try:
            # psycopg2 auto-starts transaction on first query
            # We just need to track state
            self._in_transaction = True

        except Exception as e:
            raise TransactionError(
                f"Failed to begin transaction: {str(e)}",
                original=e
            )

    def commit(self) -> None:
        """Commit PostgreSQL transaction.

        Raises:
            TransactionError: If commit fails
            ConnectionError: If not connected
        """
        if not self.conn:
            raise DBConnectionError("Not connected to database")

        try:
            self.conn.commit()
            self._in_transaction = False

        except Exception as e:
            raise TransactionError(
                f"Failed to commit transaction: {str(e)}",
                original=e
            )

    def rollback(self) -> None:
        """Rollback PostgreSQL transaction.

        Safe to call even if no transaction is active.

        Raises:
            TransactionError: If rollback fails
            ConnectionError: If not connected
        """
        if not self.conn:
            raise DBConnectionError("Not connected to database")

        try:
            self.conn.rollback()
            self._in_transaction = False

        except Exception as e:
            raise TransactionError(
                f"Failed to rollback transaction: {str(e)}",
                original=e
            )

    def get_metadata(self) -> dict:
        """Get PostgreSQL connector metadata.

        Returns:
            Dictionary with connector information
        """
        metadata = {
            "database_type": "postgresql",
            "driver": "psycopg2",
            "version": None,
            "connected": self.is_connected()
        }

        if self.is_connected():
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT version()")
                version = cursor.fetchone()[0]
                metadata["version"] = version
                cursor.close()
            except Exception:
                pass

        return metadata
