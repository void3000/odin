"""
Database execution errors.

Provides common exception hierarchy for database operations,
abstracting database-specific errors.
"""

from typing import Any, List, Optional


class DatabaseError(Exception):
    """Base exception for all database errors."""

    def __init__(self, message: str, original: Optional[Exception] = None):
        """Initialize database error.

        Args:
            message: Error description
            original: Original exception from database driver
        """
        super().__init__(message)
        self.original = original


class ConnectionError(DatabaseError):
    """Connection failed or lost.

    Raised when:
    - Cannot establish connection
    - Connection lost during execution
    - Connection pool exhausted
    """

    pass


class QueryError(DatabaseError):
    """Query execution failed.

    Includes query context for debugging.
    """

    def __init__(
        self,
        message: str,
        sql: str,
        params: List[Any],
        original: Optional[Exception] = None
    ):
        """Initialize query error.

        Args:
            message: Error description
            sql: SQL query that failed
            params: Query parameters
            original: Original exception from database driver
        """
        super().__init__(message, original)
        self.sql = sql
        self.params = params

    def __str__(self) -> str:
        """Include query context in error message."""
        return (
            f"{super().__str__()}\n"
            f"SQL: {self.sql}\n"
            f"Params: {self.params}"
        )


class TransactionError(DatabaseError):
    """Transaction operation failed.

    Raised when:
    - Cannot begin transaction
    - Commit fails
    - Rollback fails
    """

    pass
