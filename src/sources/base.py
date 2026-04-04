"""Base protocol and models for data sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class SourceField(BaseModel):
    """A queryable field in a data source."""
    name: str
    type: str
    description: str | None = None


class SourceCollection(BaseModel):
    """A queryable unit — a table, log group, index, etc."""
    name: str
    fields: list[SourceField]
    description: str | None = None


class SourceSchema(BaseModel):
    """Schema describing what is queryable in a source."""
    collections: list[SourceCollection]


class SourceCapabilities(BaseModel):
    """Describes what query features a source supports."""
    supports_joins: bool = False
    supports_aggregates: bool = False
    supports_time_range: bool = False
    supports_full_text: bool = False
    supports_filters: bool = True
    supported_operators: set[str] = Field(
        default_factory=lambda: {"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE"}
    )
    max_results: int | None = None


@dataclass
class NativeQuery:
    """Base for source-specific query representations.

    Each source subclasses this with its own fields.
    The pipeline treats it as opaque — only the source that
    created it can execute it.
    """
    pass


@dataclass
class QueryResult:
    """Common result format from any data source."""
    rows: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    source_name: str


@runtime_checkable
class DataSource(Protocol):
    """Protocol that every data source must implement."""
    name: str
    source_type: str

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def get_schema(self) -> SourceSchema: ...
    def get_capabilities(self) -> SourceCapabilities: ...
    def build_query(self, ir: Any) -> NativeQuery: ...
    def execute(self, query: NativeQuery) -> QueryResult: ...
