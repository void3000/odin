"""
SQLite connector implementation.

Wraps sqlite3 driver and implements DatabaseConnector protocol.
"""

import sqlite3
from typing import Any, List, Tuple, Optional

from ..connector import DatabaseConnector, RawResult
from ..errors import (
    ConnectionError as DBConnectionError,
    QueryError,
    TransactionError
)


class SQLiteConnector:
    """
    SQLite connector using sqlite3.

    Implements DatabaseConnector protocol for SQLite databases.

    Features:
    - Connection management (file-based or in-memory)
    - Parameterized queries (? style placeholders)
    - Transaction support
    - Error translation from sqlite3 to common exceptions
    - Automatic conversion from PostgreSQL-style ($1, $2) to SQLite-style (?, ?)

    Note: SQLite uses ? placeholders, but we auto-convert from $1, $2, etc.
    """

    def __init__(
        self,
        database: str = ":memory:",
        timeout: float = 5.0,
        check_same_thread: bool = True
    ):
        """Initialize SQLite connector.

        Args:
            database: Database file path or ":memory:" for in-memory database
            timeout: Database lock timeout in seconds (default 5.0)
            check_same_thread: Only allow same thread to use connection (default True)

        Examples:
            # In-memory database
            SQLiteConnector()

            # File-based database
            SQLiteConnector(database="/path/to/db.sqlite")
        """
        self.database = database
        self.timeout = timeout
        self.check_same_thread = check_same_thread
        self.conn = None
        self.cursor = None
        self._in_transaction = False

    def connect(self) -> None:
        """Establish SQLite connection.

        Raises:
            ConnectionError: If connection fails
        """
        try:
            self.conn = sqlite3.connect(
                self.database,
                timeout=self.timeout,
                check_same_thread=self.check_same_thread
            )
            # Return rows as Row objects (dict-like access)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()

        except Exception as e:
            raise DBConnectionError(
                f"Failed to connect to SQLite: {str(e)}",
                original=e
            )

    def disconnect(self) -> None:
        """Close SQLite connection."""
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
        """Check if connected to SQLite.

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
        """Execute single SQLite query.

        Args:
            query: SQL query (dict with 'sql' and 'params' keys, or string)
            params: Query parameters (optional, overrides query['params'])

        Returns:
            RawResult with rows, columns, rowcount

        Raises:
            ConnectionError: If not connected
            QueryError: If query execution fails

        Note:
            Automatically converts PostgreSQL-style ($1, $2) placeholders
            to SQLite-style (?, ?) placeholders.
        """
        if not self.conn or not self.cursor:
            raise DBConnectionError("Not connected to database")

        # Extract SQL and params from query
        if isinstance(query, dict):
            sql = query.get("sql", query)
            # Only override params if explicitly provided and not empty list
            if params is None or (isinstance(params, list) and len(params) == 0 and "params" in query):
                params = query.get("params", [])
        else:
            sql = str(query)
            if params is None:
                params = []

        # Convert PostgreSQL-style placeholders ($1, $2) to SQLite-style (?, ?)
        sql, params = self._convert_placeholders(sql, params)

        try:
            # Execute query
            self.cursor.execute(sql, params)

            # Get results
            try:
                rows_raw = self.cursor.fetchall()
                if rows_raw and len(rows_raw) > 0:
                    # Convert Row objects to tuples
                    columns = list(rows_raw[0].keys())
                    rows = [tuple(row) for row in rows_raw]
                else:
                    # Query didn't return results (INSERT, UPDATE, DELETE)
                    rows = []
                    columns = []
            except Exception:
                # No results
                rows = []
                columns = []

            rowcount = self.cursor.rowcount

            return RawResult(
                rows=rows,
                columns=columns,
                rowcount=rowcount
            )

        except Exception as e:
            # Translate sqlite3 errors to common exceptions
            error_msg = str(e)

            # Check if it's a connection error
            if "database is locked" in error_msg.lower():
                raise DBConnectionError(
                    f"Database is locked: {error_msg}",
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
        queries: List[Tuple[Any, List[Any]]]
    ) -> List[RawResult]:
        """Execute multiple SQLite queries sequentially.

        Args:
            queries: List of (query, params) tuples

        Returns:
            List of RawResult, one per query

        Raises:
            ConnectionError: If not connected
            QueryError: If any query fails
        """
        results = []

        for query, params in queries:
            result = self.execute_query(query, params)
            results.append(result)

        return results

    def begin_transaction(self) -> None:
        """Start SQLite transaction.

        Raises:
            TransactionError: If transaction cannot be started
            ConnectionError: If not connected
        """
        if not self.conn:
            raise DBConnectionError("Not connected to database")

        if self._in_transaction:
            raise TransactionError("Transaction already in progress")

        try:
            # SQLite auto-starts transaction on first INSERT/UPDATE/DELETE
            # We explicitly BEGIN to be consistent
            self.cursor.execute("BEGIN")
            self._in_transaction = True

        except Exception as e:
            raise TransactionError(
                f"Failed to begin transaction: {str(e)}",
                original=e
            )

    def commit(self) -> None:
        """Commit SQLite transaction.

        Raises:
            TransactionError: If commit fails
            ConnectionError: If not connected
        """
        if not self.conn:
            raise DBConnectionError("Not connected to database")

        if not self._in_transaction:
            raise TransactionError("No transaction active")

        try:
            self.conn.commit()
            self._in_transaction = False

        except Exception as e:
            raise TransactionError(
                f"Failed to commit transaction: {str(e)}",
                original=e
            )

    def rollback(self) -> None:
        """Rollback SQLite transaction.

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
        """Get SQLite connector metadata.

        Returns:
            Dictionary with connector information
        """
        metadata = {
            "database_type": "sqlite",
            "driver": "sqlite3",
            "version": None,
            "connected": self.is_connected(),
            "database": self.database
        }

        if self.is_connected():
            try:
                cursor = self.conn.cursor()
                cursor.execute("SELECT sqlite_version()")
                version = cursor.fetchone()[0]
                metadata["version"] = version
                cursor.close()
            except Exception:
                pass

        return metadata

    def _convert_placeholders(self, sql: str, params: List[Any]) -> Tuple[str, List[Any]]:
        """Convert PostgreSQL-style placeholders to SQLite-style.

        PostgreSQL uses $1, $2, $3, ...
        SQLite uses ?, ?, ?, ...

        Args:
            sql: SQL with PostgreSQL-style placeholders
            params: Parameters list

        Returns:
            Tuple of (converted_sql, params)

        Examples:
            ("SELECT * FROM users WHERE id = $1", [42])
            -> ("SELECT * FROM users WHERE id = ?", [42])

            ("INSERT INTO users (name, age) VALUES ($1, $2)", ["Alice", 25])
            -> ("INSERT INTO users (name, age) VALUES (?, ?)", ["Alice", 25])
        """
        import re

        # Find all $N placeholders
        placeholder_pattern = r'\$(\d+)'
        matches = re.findall(placeholder_pattern, sql)

        if not matches:
            # No PostgreSQL-style placeholders, return as-is
            return sql, params

        # Convert $1, $2, etc. to ?
        # Need to handle them in reverse order to avoid issues with $10 vs $1
        matches_sorted = sorted(set(int(m) for m in matches), reverse=True)

        for n in matches_sorted:
            sql = sql.replace(f'${n}', '?')

        return sql, params
