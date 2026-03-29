"""
Database connector interface (Bridge pattern implementation side).

Defines the protocol for database-specific connection implementations.
"""

from dataclasses import dataclass
from typing import Any, List, Tuple, Protocol


@dataclass
class RawResult:
    """Raw result from database connector.

    Minimal structure returned by connectors, before processing
    by QueryExecutor.
    """

    rows: List[Tuple[Any, ...]]
    """List of result rows as tuples"""

    columns: List[str]
    """Column names in result order"""

    rowcount: int
    """Number of rows affected/returned"""


class DatabaseConnector(Protocol):
    """
    Protocol for database connection implementations.

    This is the implementation side of the Bridge pattern.
    Each database type (PostgreSQL, MySQL, etc.) provides a
    concrete implementation.

    Design:
    - Handles connection lifecycle
    - Executes SQL with parameters
    - Manages transactions
    - Translates database-specific errors to common exceptions
    """

    def connect(self) -> None:
        """Establish database connection.

        Raises:
            ConnectionError: If connection cannot be established
        """
        ...

    def disconnect(self) -> None:
        """Close database connection.

        Safe to call multiple times. Does nothing if not connected.
        """
        ...

    def is_connected(self) -> bool:
        """Check if currently connected.

        Returns:
            True if connection is active, False otherwise
        """
        ...

    def execute_query(self, sql: str, params: List[Any]) -> RawResult:
        """Execute single query and return raw results.

        Args:
            sql: SQL query string
            params: Query parameters (positional)

        Returns:
            RawResult with rows, columns, and rowcount

        Raises:
            ConnectionError: If connection lost during execution
            QueryError: If query execution fails
        """
        ...

    def execute_many(
        self,
        queries: List[Tuple[str, List[Any]]]
    ) -> List[RawResult]:
        """Execute multiple queries sequentially.

        NOT in a transaction unless begin_transaction() called first.

        Args:
            queries: List of (sql, params) tuples

        Returns:
            List of RawResult, one per query

        Raises:
            ConnectionError: If connection lost during execution
            QueryError: If any query fails
        """
        ...

    def begin_transaction(self) -> None:
        """Start a transaction.

        Subsequent queries will be part of the transaction until
        commit() or rollback() is called.

        Raises:
            TransactionError: If transaction cannot be started
            ConnectionError: If not connected
        """
        ...

    def commit(self) -> None:
        """Commit current transaction.

        Raises:
            TransactionError: If commit fails
            ConnectionError: If not connected
        """
        ...

    def rollback(self) -> None:
        """Rollback current transaction.

        Safe to call even if no transaction is active.

        Raises:
            TransactionError: If rollback fails
            ConnectionError: If not connected
        """
        ...

    def get_metadata(self) -> dict:
        """Get connector metadata.

        Returns:
            Dictionary with connector information:
            - database_type: "postgresql", "mysql", etc.
            - version: Database version
            - driver: Driver name and version
        """
        ...
