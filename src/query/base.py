"""
Base classes and protocols for query builders.

All database-specific builders inherit from QueryBuilder and return
a QueryResult implementation.
"""

from abc import ABC, abstractmethod
from typing import Protocol, Any, Set
from dataclasses import dataclass, field

from src.ir.models import QueryIR, FilterExpr, ConditionExpr, LogicalExpr


class QueryResult(Protocol):
    """Protocol for query results from any database.

    All concrete result types must implement this protocol.
    """

    def execute(self, connection: Any) -> Any:
        """Execute the query against a database connection.

        Args:
            connection: Database-specific connection object

        Returns:
            Database-specific result (rows, documents, etc.)
        """
        ...

    def to_dict(self) -> dict:
        """Get query as dictionary for inspection/logging.

        Returns:
            Dictionary representation of the query
        """
        ...

    def __str__(self) -> str:
        """Human-readable representation of the query."""
        ...


@dataclass
class QueryCapabilities:
    """Describes what features a database supports.

    Used for validating IR before attempting to build queries.
    """

    supports_joins: bool = True
    supports_complex_filters: bool = True
    supports_aggregates: bool = True
    supports_subqueries: bool = True
    max_join_depth: int | None = None
    supported_operators: Set[str] = field(default_factory=lambda: {
        "=", "!=", ">", ">=", "<", "<=", "IN", "LIKE"
    })


class QueryBuildError(Exception):
    """Base exception for query building errors."""
    pass


class UnsupportedFeatureError(QueryBuildError):
    """Feature in IR is not supported by this database."""
    pass


class InvalidIRError(QueryBuildError):
    """IR is invalid (should have been caught by validator)."""
    pass


class QueryBuilder(ABC):
    """Abstract base class for all query builders.

    Each database type (PostgreSQL, MySQL, MongoDB, DynamoDB) implements
    this interface to translate IR into database-specific queries.
    """

    @abstractmethod
    def build(self, query_ir: QueryIR) -> QueryResult:
        """Build a query from IR.

        Args:
            query_ir: Validated intermediate representation

        Returns:
            Database-specific query result

        Raises:
            UnsupportedFeatureError: If IR uses unsupported features
            QueryBuildError: If query cannot be built
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> QueryCapabilities:
        """Get capabilities of this database.

        Returns:
            QueryCapabilities describing supported features
        """
        pass

    def validate_ir(self, query_ir: QueryIR) -> None:
        """Validate that IR is supported by this builder.

        Args:
            query_ir: IR to validate

        Raises:
            UnsupportedFeatureError: If IR uses unsupported features
        """
        capabilities = self.get_capabilities()

        # Check joins
        if query_ir.joins and not capabilities.supports_joins:
            raise UnsupportedFeatureError(
                f"This database does not support JOINs"
            )

        # Check join depth
        if query_ir.joins and capabilities.max_join_depth:
            if len(query_ir.joins) > capabilities.max_join_depth:
                raise UnsupportedFeatureError(
                    f"Maximum join depth is {capabilities.max_join_depth}, "
                    f"but query has {len(query_ir.joins)} joins"
                )

        # Check operators
        if query_ir.filters:
            self._validate_operators(query_ir.filters, capabilities.supported_operators)

    def _validate_operators(self, filters: FilterExpr, supported: Set[str]) -> None:
        """Recursively validate operators in filters.

        Args:
            filters: Filter expression to validate
            supported: Set of supported operator strings

        Raises:
            UnsupportedFeatureError: If unsupported operator is found
        """
        if isinstance(filters, ConditionExpr):
            if filters.op not in supported:
                raise UnsupportedFeatureError(
                    f"Operator '{filters.op}' not supported by this database. "
                    f"Supported operators: {', '.join(sorted(supported))}"
                )
        elif isinstance(filters, LogicalExpr):
            for condition in filters.conditions:
                self._validate_operators(condition, supported)
