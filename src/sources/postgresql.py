"""PostgreSQL data source — wraps existing builder and connector."""

from dataclasses import dataclass
from typing import Any

from src.db import create_connector, create_schema_extractor
from src.ir.models import QueryIR
from src.query.postgresql import PostgreSQLBuilder
from src.sources.base import (
    DataSource,
    NativeQuery,
    QueryResult,
    SourceCapabilities,
    SourceCollection,
    SourceField,
    SourceSchema,
)


@dataclass
class SQLNativeQuery(NativeQuery):
    """Native query for SQL databases."""
    sql: str = ""
    params: list = None

    def __post_init__(self):
        if self.params is None:
            self.params = []


class PostgreSQLSource:
    """PostgreSQL data source."""

    source_type = "database"

    def __init__(self, name: str, url: str, search_path: list[str] | None = None):
        self.name = name
        self.url = url
        self.search_path = search_path
        self._connector = None
        self._builder = PostgreSQLBuilder()

    def connect(self) -> None:
        self._connector = create_connector(self.url, search_path=self.search_path)
        self._connector.connect()

    def disconnect(self) -> None:
        if self._connector:
            self._connector.disconnect()
            self._connector = None

    def is_connected(self) -> bool:
        return self._connector is not None

    def get_schema(self) -> SourceSchema:
        extractor = create_schema_extractor(self.url)
        db_schema = extractor.extract_schema()
        # Capture discovered schemas as search_path for queries
        if hasattr(extractor, "schemas") and extractor.schemas:
            self.search_path = extractor.schemas
        collections = []
        for table in db_schema.tables:
            fields = [
                SourceField(name=col.name, type=col.type)
                for col in table.columns
            ]
            collections.append(SourceCollection(name=table.name, fields=fields))
        return SourceSchema(collections=collections)

    def get_capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            supports_joins=True,
            supports_aggregates=True,
            supports_time_range=False,
            supports_full_text=False,
            supports_filters=True,
            supported_operators={"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE"},
        )

    def build_query(self, ir: QueryIR) -> SQLNativeQuery:
        result = self._builder.build(ir)
        return SQLNativeQuery(sql=result.query["sql"], params=result.query["params"])

    def execute(self, query: SQLNativeQuery) -> QueryResult:
        raw = self._connector.execute_query(
            {"sql": query.sql, "params": query.params}
        )
        rows = [dict(zip(raw.columns, row)) for row in raw.rows]
        return QueryResult(
            rows=rows,
            columns=list(raw.columns),
            row_count=len(rows),
            source_name=self.name,
        )
