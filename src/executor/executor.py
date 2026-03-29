"""
Query executor using Bridge pattern (abstraction side).

Handles query execution orchestration, retry logic, and result mapping.
Delegates actual database operations to DatabaseConnector implementation.
"""

import time
from dataclasses import dataclass
from typing import Any, Dict, List

from .connector import DatabaseConnector, RawResult
from .errors import ConnectionError, QueryError, TransactionError


@dataclass
class ExecutionResult:
    """Processed result from query execution.

    Enhanced version of RawResult with additional metadata
    and rows mapped to dictionaries.
    """

    rows: List[Dict[str, Any]]
    """List of result rows as dictionaries (column -> value)"""

    columns: List[str]
    """Column names in result order"""

    rowcount: int
    """Number of rows affected/returned"""

    execution_time_ms: float
    """Query execution time in milliseconds"""

    query_sql: str
    """SQL query that was executed (for debugging)"""


class QueryExecutor:
    """
    High-level query execution with retry logic and result mapping.

    Bridge Pattern - Abstraction Side:
    - Delegates connection/execution to DatabaseConnector (implementation)
    - Provides retry logic, timeout, and error handling
    - Maps raw results to structured format

    Usage:
        connector = PostgreSQLConnector(connection_string)
        executor = QueryExecutor(connector)
        result = executor.execute(query_result)
    """

    def __init__(
        self,
        connector: DatabaseConnector,
        max_retries: int = 3,
        retry_delay_ms: int = 100,
        auto_connect: bool = True
    ):
        """Initialize query executor.

        Args:
            connector: Database connector implementation (Bridge)
            max_retries: Maximum retry attempts on transient failures
            retry_delay_ms: Initial retry delay (exponential backoff)
            auto_connect: Automatically connect on first execute
        """
        self.connector = connector
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms
        self.auto_connect = auto_connect

    def execute(self, query_result: Any) -> ExecutionResult:
        """Execute single query with retry logic.

        Args:
            query_result: Query result from builder (GenericQueryResult)

        Returns:
            ExecutionResult with mapped rows and metadata

        Raises:
            ConnectionError: If connection fails after retries
            QueryError: If query execution fails (syntax, permissions, etc.)
        """
        # Extract query from builder result (supports both SQL and NoSQL)
        query = query_result.query

        # For SQL databases, extract sql string for logging
        if isinstance(query, dict) and "sql" in query:
            query_str = query["sql"]
        else:
            query_str = str(query)

        # Ensure connected
        if self.auto_connect and not self.connector.is_connected():
            self.connector.connect()

        # Execute with retry logic
        for attempt in range(self.max_retries):
            try:
                start_time = time.perf_counter()
                raw_result = self.connector.execute_query(query, [])
                execution_time_ms = (time.perf_counter() - start_time) * 1000

                # Map raw result to execution result
                return self._map_result(raw_result, query_str, execution_time_ms)

            except ConnectionError as e:
                # Retry on connection errors
                if attempt == self.max_retries - 1:
                    raise  # Final attempt, give up

                # Exponential backoff
                delay_ms = self.retry_delay_ms * (2 ** attempt)
                time.sleep(delay_ms / 1000)

                # Try to reconnect
                try:
                    self.connector.connect()
                except ConnectionError:
                    if attempt == self.max_retries - 1:
                        raise

            except QueryError:
                # Don't retry syntax errors, permission errors, etc.
                raise

    def execute_batch(
        self,
        query_results: List[Any]
    ) -> List[ExecutionResult]:
        """Execute multiple queries sequentially (not in transaction).

        Args:
            query_results: List of query results from builder

        Returns:
            List of ExecutionResult, one per query

        Raises:
            ConnectionError: If connection fails
            QueryError: If any query fails
        """
        # Ensure connected
        if self.auto_connect and not self.connector.is_connected():
            self.connector.connect()

        # Extract queries from each result
        queries = [(qr.query, []) for qr in query_results]

        # Execute batch
        start_time = time.perf_counter()
        raw_results = self.connector.execute_many(queries)
        execution_time_ms = (time.perf_counter() - start_time) * 1000

        # Map each result
        return [
            self._map_result(
                raw_result,
                str(query_results[i].query),
                execution_time_ms / len(query_results)  # Average time per query
            )
            for i, raw_result in enumerate(raw_results)
        ]

    def execute_transaction(
        self,
        query_results: List[Any]
    ) -> List[ExecutionResult]:
        """Execute multiple queries in a transaction.

        All queries committed together, or all rolled back on failure.

        Args:
            query_results: List of query results from builder

        Returns:
            List of ExecutionResult, one per query

        Raises:
            ConnectionError: If connection fails
            QueryError: If any query fails
            TransactionError: If transaction begin/commit/rollback fails
        """
        # Ensure connected
        if self.auto_connect and not self.connector.is_connected():
            self.connector.connect()

        try:
            # Begin transaction
            self.connector.begin_transaction()

            # Execute all queries
            results = []
            for query_result in query_results:
                start_time = time.perf_counter()
                raw_result = self.connector.execute_query(
                    query_result.query,
                    []
                )
                execution_time_ms = (time.perf_counter() - start_time) * 1000

                results.append(
                    self._map_result(raw_result, str(query_result.query), execution_time_ms)
                )

            # Commit transaction
            self.connector.commit()

            return results

        except Exception as e:
            # Rollback on any error
            try:
                self.connector.rollback()
            except Exception:
                pass  # Rollback failed, but we're already handling an error

            # Re-raise original error
            raise

    def close(self) -> None:
        """Close database connection.

        Safe to call multiple times.
        """
        self.connector.disconnect()

    def get_metadata(self) -> dict:
        """Get executor and connector metadata.

        Returns:
            Dictionary with metadata:
            - connector_info: Connector metadata
            - max_retries: Retry configuration
            - retry_delay_ms: Retry delay configuration
        """
        return {
            "connector_info": self.connector.get_metadata(),
            "max_retries": self.max_retries,
            "retry_delay_ms": self.retry_delay_ms,
        }

    def _map_result(
        self,
        raw_result: RawResult,
        sql: str,
        execution_time_ms: float
    ) -> ExecutionResult:
        """Map raw result to execution result.

        Converts rows from tuples to dictionaries for easier access.

        Args:
            raw_result: Raw result from connector
            sql: SQL query that was executed
            execution_time_ms: Execution time

        Returns:
            ExecutionResult with mapped rows
        """
        # Map rows from tuples to dicts
        rows_as_dicts = [
            dict(zip(raw_result.columns, row))
            for row in raw_result.rows
        ]

        return ExecutionResult(
            rows=rows_as_dicts,
            columns=raw_result.columns,
            rowcount=raw_result.rowcount,
            execution_time_ms=execution_time_ms,
            query_sql=sql
        )
