"""
Query execution module using Bridge pattern.

Separates query execution abstraction (QueryExecutor) from
database connection implementation (DatabaseConnector).
"""

from .connector import DatabaseConnector, RawResult
from .executor import QueryExecutor, ExecutionResult
from .errors import (
    DatabaseError,
    ConnectionError,
    QueryError,
    TransactionError
)

__all__ = [
    "DatabaseConnector",
    "RawResult",
    "QueryExecutor",
    "ExecutionResult",
    "DatabaseError",
    "ConnectionError",
    "QueryError",
    "TransactionError",
]
