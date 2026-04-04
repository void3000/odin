"""SQLite data source — wraps existing builder and connector."""

from src.executor.connectors.sqlite import SQLiteConnector
from src.ir.models import QueryIR
from src.query_builder import SQLBuilder
from src.schema.extractor import SQLiteSchemaExtractor
from src.sources.base import (
    QueryResult,
    SourceCapabilities,
    SourceCollection,
    SourceField,
    SourceSchema,
)
from src.sources.postgresql import SQLNativeQuery


class SQLiteSource:
    """SQLite data source."""

    source_type = "database"

    def __init__(self, name: str, path: str):
        self.name = name
        self.path = path
        self._connector = None
        self._builder = SQLBuilder()

    def connect(self) -> None:
        self._connector = SQLiteConnector(database=self.path, check_same_thread=False)
        self._connector.connect()

    def disconnect(self) -> None:
        if self._connector:
            self._connector.disconnect()
            self._connector = None

    def is_connected(self) -> bool:
        return self._connector is not None

    def get_schema(self) -> SourceSchema:
        extractor = SQLiteSchemaExtractor(self.path)
        db_schema = extractor.extract_schema()
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
        sql, params = self._builder.build(ir)
        return SQLNativeQuery(sql=sql, params=params)

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
