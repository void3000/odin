"""
Query Builder Factory.

Factory pattern for creating database-specific query builders.
"""

from typing import Dict, Type

from .base import QueryBuilder


class QueryBuilderFactory:
    """Factory for creating query builders.

    Builders are registered by database type and can be created
    using the create() method.
    """

    _builders: Dict[str, Type[QueryBuilder]] = {}

    @classmethod
    def register(cls, database_type: str, builder_class: Type[QueryBuilder]) -> None:
        """Register a builder for a database type.

        Args:
            database_type: Database type identifier (e.g., 'postgresql', 'mongodb')
            builder_class: QueryBuilder subclass to register

        Example:
            QueryBuilderFactory.register('postgresql', PostgreSQLBuilder)
        """
        cls._builders[database_type.lower()] = builder_class

    @classmethod
    def create(cls, database_type: str, **kwargs) -> QueryBuilder:
        """Create a builder for the specified database type.

        Args:
            database_type: Type of database (e.g., 'postgresql', 'mongodb')
            **kwargs: Additional arguments passed to builder constructor

        Returns:
            Appropriate query builder instance

        Raises:
            ValueError: If database type is not registered

        Example:
            builder = QueryBuilderFactory.create('postgresql')
            result = builder.build(query_ir)
        """
        builder_class = cls._builders.get(database_type.lower())
        if not builder_class:
            available = ", ".join(sorted(cls._builders.keys()))
            raise ValueError(
                f"Unknown database type: '{database_type}'. "
                f"Available types: {available}"
            )
        return builder_class(**kwargs)

    @classmethod
    def list_supported(cls) -> list[str]:
        """List all supported database types.

        Returns:
            List of registered database type identifiers
        """
        return sorted(cls._builders.keys())

    @classmethod
    def is_supported(cls, database_type: str) -> bool:
        """Check if a database type is supported.

        Args:
            database_type: Database type to check

        Returns:
            True if database type is registered, False otherwise
        """
        return database_type.lower() in cls._builders

    @classmethod
    def clear_registry(cls) -> None:
        """Clear all registered builders.

        Primarily used for testing.
        """
        cls._builders.clear()
