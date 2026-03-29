"""
Generic query result for database-agnostic query representation.

Supports both SQL databases (PostgreSQL, MySQL) and NoSQL databases (MongoDB, DynamoDB).
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class GenericQueryResult:
    """
    Database-agnostic query result.

    The 'query' field contains database-specific query representation:
    - SQL databases: {"sql": str, "params": list}
    - MongoDB: {"collection": str, "filter": dict, "projection": dict, ...}
    - DynamoDB: {"table": str, "key_condition": dict, ...}
    """

    database_type: str
    """Type of database: "postgresql", "mysql", "mongodb", "dynamodb", etc."""

    query: Dict[str, Any]
    """Database-specific query structure"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata (builder info, IR hash, etc.)"""

    def to_dict(self) -> dict:
        """Get query as dictionary for inspection/logging.

        Returns:
            Dictionary with all query information
        """
        return {
            "database_type": self.database_type,
            "query": self.query,
            "metadata": self.metadata
        }

    def __str__(self) -> str:
        """Human-readable representation of the query."""
        if self.database_type in ("postgresql", "mysql", "sqlite"):
            sql = self.query.get("sql", "")
            params = self.query.get("params", [])
            return f"{self.database_type.upper()} Query:\n{sql}\nParams: {params}"

        elif self.database_type == "mongodb":
            collection = self.query.get("collection", "")
            filter_dict = self.query.get("filter", {})
            return f"MongoDB Query:\nCollection: {collection}\nFilter: {filter_dict}"

        else:
            return f"{self.database_type} Query: {self.query}"
