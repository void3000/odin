# Data Source Abstraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-database pipeline with a pluggable `DataSource` protocol and source registry, so any query-based data source can be added without changing pipeline code.

**Architecture:** A `DataSource` protocol defines connect/schema/build/execute for any source. A `SourceRegistry` holds configured sources. Existing PostgreSQL/SQLite code is wrapped into `DataSource` implementations. The pipeline workflows use the resolved source instead of hardcoded SQL builders and connectors.

**Tech Stack:** Python protocols, Pydantic models, PyYAML for config

---

### Task 1: Create the sources base module with protocol and models

**Files:**
- Create: `src/sources/__init__.py`
- Create: `src/sources/base.py`
- Test: `tests/test_sources_base.py`

- [ ] **Step 1: Write failing tests for the base models**

Create `tests/test_sources_base.py`:

```python
from src.sources.base import (
    SourceField,
    SourceCollection,
    SourceSchema,
    SourceCapabilities,
    QueryResult,
)


class TestSourceModels:
    def test_source_field(self):
        field = SourceField(name="id", type="int")
        assert field.name == "id"
        assert field.type == "int"
        assert field.description is None

    def test_source_field_with_description(self):
        field = SourceField(name="status", type="str", description="User status")
        assert field.description == "User status"

    def test_source_collection(self):
        col = SourceCollection(
            name="users",
            fields=[SourceField(name="id", type="int"), SourceField(name="name", type="str")],
        )
        assert col.name == "users"
        assert len(col.fields) == 2

    def test_source_schema(self):
        schema = SourceSchema(collections=[
            SourceCollection(name="users", fields=[SourceField(name="id", type="int")]),
            SourceCollection(name="orders", fields=[SourceField(name="total", type="float")]),
        ])
        assert len(schema.collections) == 2

    def test_source_capabilities_defaults(self):
        caps = SourceCapabilities()
        assert caps.supports_joins is False
        assert caps.supports_aggregates is False
        assert caps.supports_time_range is False
        assert caps.supports_full_text is False
        assert caps.supports_filters is True

    def test_source_capabilities_database(self):
        caps = SourceCapabilities(
            supports_joins=True,
            supports_aggregates=True,
            supported_operators={"=", "!=", ">", "<", ">=", "<=", "IN", "LIKE"},
        )
        assert caps.supports_joins is True
        assert "IN" in caps.supported_operators

    def test_query_result(self):
        result = QueryResult(
            rows=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            columns=["id", "name"],
            row_count=2,
            source_name="main_db",
        )
        assert result.row_count == 2
        assert result.source_name == "main_db"
        assert result.rows[0]["name"] == "Alice"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sources_base.py -v`
Expected: FAIL — `src.sources.base` does not exist.

- [ ] **Step 3: Create src/sources/__init__.py**

```python
"""Pluggable data source abstraction layer."""
```

- [ ] **Step 4: Create src/sources/base.py**

```python
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
    """Protocol that every data source must implement.

    Covers the full lifecycle: connect, describe schema,
    build native queries from IR, and execute them.
    """
    name: str
    source_type: str

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def get_schema(self) -> SourceSchema: ...
    def get_capabilities(self) -> SourceCapabilities: ...
    def build_query(self, ir: Any) -> NativeQuery: ...
    def execute(self, query: NativeQuery) -> QueryResult: ...
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_sources_base.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/sources/__init__.py src/sources/base.py tests/test_sources_base.py
git commit -m "feat: add DataSource protocol and base models"
```

---

### Task 2: Create the SourceRegistry

**Files:**
- Create: `src/sources/registry.py`
- Test: `tests/test_sources_registry.py`

- [ ] **Step 1: Write failing tests for the registry**

Create `tests/test_sources_registry.py`:

```python
import pytest
from unittest.mock import MagicMock
from src.sources.registry import SourceRegistry, SourceInfo


def _make_mock_source(name="test_db", source_type="database"):
    source = MagicMock()
    source.name = name
    source.source_type = source_type
    return source


class TestSourceRegistry:
    def test_register_and_get(self):
        registry = SourceRegistry()
        source = _make_mock_source()
        registry.register("test_db", source)
        assert registry.get("test_db") is source

    def test_get_unknown_raises(self):
        registry = SourceRegistry()
        with pytest.raises(KeyError, match="test_db"):
            registry.get("test_db")

    def test_list_sources(self):
        registry = SourceRegistry()
        registry.register("db1", _make_mock_source("db1", "database"))
        registry.register("logs1", _make_mock_source("logs1", "logs"))
        sources = registry.list_sources()
        assert len(sources) == 2
        names = {s.name for s in sources}
        assert names == {"db1", "logs1"}

    def test_list_sources_returns_source_info(self):
        registry = SourceRegistry()
        registry.register("db1", _make_mock_source("db1", "database"))
        info = registry.list_sources()[0]
        assert isinstance(info, SourceInfo)
        assert info.name == "db1"
        assert info.source_type == "database"

    def test_get_default_single_source(self):
        registry = SourceRegistry()
        source = _make_mock_source()
        registry.register("only_one", source)
        assert registry.get_default() is source

    def test_get_default_named_default(self):
        registry = SourceRegistry()
        source1 = _make_mock_source("db1")
        source2 = _make_mock_source("default")
        registry.register("db1", source1)
        registry.register("default", source2)
        assert registry.get_default() is source2

    def test_get_default_multiple_no_default_raises(self):
        registry = SourceRegistry()
        registry.register("db1", _make_mock_source("db1"))
        registry.register("db2", _make_mock_source("db2"))
        with pytest.raises(ValueError, match="multiple sources"):
            registry.get_default()

    def test_register_duplicate_raises(self):
        registry = SourceRegistry()
        registry.register("db1", _make_mock_source())
        with pytest.raises(ValueError, match="already registered"):
            registry.register("db1", _make_mock_source())

    def test_is_empty(self):
        registry = SourceRegistry()
        assert len(registry.list_sources()) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sources_registry.py -v`
Expected: FAIL — `src.sources.registry` does not exist.

- [ ] **Step 3: Create src/sources/registry.py**

```python
"""Source registry — holds configured data sources."""

from dataclasses import dataclass
from typing import Any

from src.sources.base import DataSource


@dataclass
class SourceInfo:
    """Lightweight summary of a registered source."""
    name: str
    source_type: str


class SourceRegistry:
    """Registry of configured data sources.

    Sources are registered at startup and looked up by name
    during query processing.
    """

    def __init__(self):
        self._sources: dict[str, DataSource] = {}

    def register(self, name: str, source: DataSource) -> None:
        """Register a source under a given name."""
        if name in self._sources:
            raise ValueError(f"Source '{name}' is already registered")
        self._sources[name] = source

    def get(self, name: str) -> DataSource:
        """Get a source by name. Raises KeyError if not found."""
        if name not in self._sources:
            raise KeyError(f"Source '{name}' not found")
        return self._sources[name]

    def get_default(self) -> DataSource:
        """Get the default source.

        Returns the only source if there's just one, or the source
        named 'default' if multiple exist.
        """
        if len(self._sources) == 1:
            return next(iter(self._sources.values()))
        if "default" in self._sources:
            return self._sources["default"]
        raise ValueError(
            "Cannot determine default source: multiple sources registered "
            "and none named 'default'"
        )

    def list_sources(self) -> list[SourceInfo]:
        """List all registered sources."""
        return [
            SourceInfo(name=name, source_type=source.source_type)
            for name, source in self._sources.items()
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sources_registry.py -v`
Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sources/registry.py tests/test_sources_registry.py
git commit -m "feat: add SourceRegistry for managing data sources"
```

---

### Task 3: Add IR extensions (TimeRange, full_text)

**Files:**
- Modify: `src/ir/models.py`
- Test: `tests/test_ir_models.py` (existing — add new tests)

- [ ] **Step 1: Write failing tests for the new IR fields**

Append to `tests/test_ir_models.py`:

```python
from src.ir.models import TimeRange


class TestTimeRange:
    def test_time_range_relative(self):
        tr = TimeRange(start="1h ago")
        assert tr.start == "1h ago"
        assert tr.end is None

    def test_time_range_absolute(self):
        tr = TimeRange(start="2026-04-04T00:00:00Z", end="2026-04-04T12:00:00Z")
        assert tr.end == "2026-04-04T12:00:00Z"


class TestQueryIRExtensions:
    def test_query_ir_with_time_range(self):
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="app_logs"),
            fields=[FieldExpr(field="message")],
            time_range=TimeRange(start="1h ago"),
        )
        assert ir.time_range.start == "1h ago"

    def test_query_ir_with_full_text(self):
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="app_logs"),
            fields=[FieldExpr(field="message")],
            full_text="NullPointerException",
        )
        assert ir.full_text == "NullPointerException"

    def test_query_ir_extensions_default_none(self):
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
        )
        assert ir.time_range is None
        assert ir.full_text is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ir_models.py::TestTimeRange -v`
Expected: FAIL — `TimeRange` not found.

- [ ] **Step 3: Add TimeRange and new fields to src/ir/models.py**

Add the `TimeRange` model before `QueryIR` in `src/ir/models.py`:

```python
class TimeRange(BaseModel):
    """Time window for log/metric queries."""
    start: str = Field(..., description="Start time (ISO 8601 or relative, e.g. '1h ago')")
    end: str | None = Field(None, description="End time (None means 'now')")
```

Add two new fields to the `QueryIR` class, after the `limit` field:

```python
    time_range: TimeRange | None = Field(None, description="Optional time window for log/metric sources")
    full_text: str | None = Field(None, description="Optional full-text search string")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ir_models.py::TestTimeRange tests/test_ir_models.py::TestQueryIRExtensions -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Run full IR test suite to check nothing broke**

Run: `pytest tests/test_ir_models.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ir/models.py tests/test_ir_models.py
git commit -m "feat: add TimeRange and full_text extensions to QueryIR"
```

---

### Task 4: Create PostgreSQLSource wrapper

**Files:**
- Create: `src/sources/postgresql.py`
- Test: `tests/test_sources_postgresql.py`

- [ ] **Step 1: Write failing tests for PostgreSQLSource**

Create `tests/test_sources_postgresql.py`:

```python
from unittest.mock import MagicMock, patch
from src.sources.postgresql import PostgreSQLSource, SQLNativeQuery
from src.sources.base import SourceSchema, SourceCapabilities, QueryResult, DataSource
from src.ir.models import QueryIR, TableSource, FieldExpr, ConditionExpr


class TestPostgreSQLSource:
    def test_implements_datasource_protocol(self):
        source = PostgreSQLSource(name="test_db", url="postgresql://localhost/test")
        assert isinstance(source, DataSource)

    def test_name_and_type(self):
        source = PostgreSQLSource(name="main_db", url="postgresql://localhost/test")
        assert source.name == "main_db"
        assert source.source_type == "database"

    def test_get_capabilities(self):
        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        caps = source.get_capabilities()
        assert isinstance(caps, SourceCapabilities)
        assert caps.supports_joins is True
        assert caps.supports_aggregates is True
        assert caps.supports_time_range is False

    def test_build_query_returns_native_query(self):
        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10,
        )
        query = source.build_query(ir)
        assert isinstance(query, SQLNativeQuery)
        assert "users" in query.sql.lower() or "users" in query.sql
        assert isinstance(query.params, list)

    def test_build_query_with_filter(self):
        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="name")],
            filters=ConditionExpr(field="status", op="=", value="active"),
            limit=10,
        )
        query = source.build_query(ir)
        assert isinstance(query, SQLNativeQuery)
        assert len(query.params) >= 1

    @patch("src.sources.postgresql.create_connector")
    def test_connect_and_disconnect(self, mock_create):
        mock_connector = MagicMock()
        mock_create.return_value = mock_connector
        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        source.connect()
        mock_connector.connect.assert_called_once()
        assert source.is_connected() is True
        source.disconnect()
        mock_connector.disconnect.assert_called_once()

    @patch("src.sources.postgresql.create_connector")
    def test_execute_returns_query_result(self, mock_create):
        mock_connector = MagicMock()
        mock_raw = MagicMock()
        mock_raw.rows = [(1, "Alice"), (2, "Bob")]
        mock_raw.columns = ["id", "name"]
        mock_connector.execute_query.return_value = mock_raw
        mock_create.return_value = mock_connector

        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        source.connect()

        query = SQLNativeQuery(sql="SELECT id, name FROM users", params=[])
        result = source.execute(query)

        assert isinstance(result, QueryResult)
        assert result.row_count == 2
        assert result.source_name == "db"
        assert result.rows[0] == {"id": 1, "name": "Alice"}
        assert result.columns == ["id", "name"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sources_postgresql.py -v`
Expected: FAIL — `src.sources.postgresql` does not exist.

- [ ] **Step 3: Create src/sources/postgresql.py**

```python
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
    """PostgreSQL data source.

    Wraps the existing PostgreSQLBuilder and PostgreSQLConnector
    into the DataSource interface.
    """

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
        return SQLNativeQuery(sql=result.sql, params=result.params)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sources_postgresql.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sources/postgresql.py tests/test_sources_postgresql.py
git commit -m "feat: add PostgreSQLSource wrapping existing builder and connector"
```

---

### Task 5: Create SQLiteSource wrapper

**Files:**
- Create: `src/sources/sqlite.py`
- Test: `tests/test_sources_sqlite.py`

- [ ] **Step 1: Write failing tests for SQLiteSource**

Create `tests/test_sources_sqlite.py`:

```python
from unittest.mock import MagicMock, patch
from src.sources.sqlite import SQLiteSource
from src.sources.postgresql import SQLNativeQuery
from src.sources.base import SourceSchema, SourceCapabilities, QueryResult, DataSource
from src.ir.models import QueryIR, TableSource, FieldExpr


class TestSQLiteSource:
    def test_implements_datasource_protocol(self):
        source = SQLiteSource(name="test_db", path="/tmp/test.db")
        assert isinstance(source, DataSource)

    def test_name_and_type(self):
        source = SQLiteSource(name="local_db", path="/tmp/test.db")
        assert source.name == "local_db"
        assert source.source_type == "database"

    def test_get_capabilities(self):
        source = SQLiteSource(name="db", path="/tmp/test.db")
        caps = source.get_capabilities()
        assert isinstance(caps, SourceCapabilities)
        assert caps.supports_joins is True
        assert caps.supports_aggregates is True
        assert caps.supports_time_range is False

    def test_build_query_returns_native_query(self):
        source = SQLiteSource(name="db", path="/tmp/test.db")
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10,
        )
        query = source.build_query(ir)
        assert isinstance(query, SQLNativeQuery)
        assert "users" in query.sql.lower() or "users" in query.sql

    @patch("src.sources.sqlite.SQLiteConnector")
    def test_connect_and_disconnect(self, mock_cls):
        mock_connector = MagicMock()
        mock_cls.return_value = mock_connector
        source = SQLiteSource(name="db", path="/tmp/test.db")
        source.connect()
        mock_connector.connect.assert_called_once()
        assert source.is_connected() is True
        source.disconnect()
        mock_connector.disconnect.assert_called_once()

    @patch("src.sources.sqlite.SQLiteConnector")
    def test_execute_returns_query_result(self, mock_cls):
        mock_connector = MagicMock()
        mock_raw = MagicMock()
        mock_raw.rows = [(1, "Alice")]
        mock_raw.columns = ["id", "name"]
        mock_connector.execute_query.return_value = mock_raw
        mock_cls.return_value = mock_connector

        source = SQLiteSource(name="db", path="/tmp/test.db")
        source.connect()

        query = SQLNativeQuery(sql="SELECT id, name FROM users", params=[])
        result = source.execute(query)

        assert isinstance(result, QueryResult)
        assert result.row_count == 1
        assert result.source_name == "db"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sources_sqlite.py -v`
Expected: FAIL — `src.sources.sqlite` does not exist.

- [ ] **Step 3: Create src/sources/sqlite.py**

```python
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
    """SQLite data source.

    Wraps the existing SQLBuilder and SQLiteConnector
    into the DataSource interface.
    """

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sources_sqlite.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/sources/sqlite.py tests/test_sources_sqlite.py
git commit -m "feat: add SQLiteSource wrapping existing builder and connector"
```

---

### Task 6: Create config loading with YAML support

**Files:**
- Create: `src/sources/config.py`
- Modify: `pyproject.toml`
- Test: `tests/test_sources_config.py`

- [ ] **Step 1: Add pyyaml to pyproject.toml**

Add `"pyyaml",` to the `dependencies` list in `pyproject.toml`, after `"python-multipart",`.

- [ ] **Step 2: Install**

Run: `pip install -e .`

- [ ] **Step 3: Write failing tests for config loading**

Create `tests/test_sources_config.py`:

```python
import tempfile
import os
import pytest
from src.sources.config import load_sources_from_config, create_source_from_db_url
from src.sources.registry import SourceRegistry


class TestCreateSourceFromDbUrl:
    def test_postgresql_url(self):
        source = create_source_from_db_url("postgresql://user:pass@localhost:5432/mydb")
        assert source.name == "default"
        assert source.source_type == "database"

    def test_sqlite_url(self):
        source = create_source_from_db_url("sqlite:///tmp/test.db")
        assert source.name == "default"
        assert source.source_type == "database"

    def test_plain_path(self):
        source = create_source_from_db_url("/tmp/test.db")
        assert source.name == "default"
        assert source.source_type == "database"

    def test_custom_name(self):
        source = create_source_from_db_url("sqlite:///tmp/test.db", name="my_db")
        assert source.name == "my_db"

    def test_unsupported_scheme(self):
        with pytest.raises(ValueError, match="Unsupported"):
            create_source_from_db_url("mysql://localhost/db")


class TestLoadSourcesFromConfig:
    def test_load_yaml_config(self):
        config_content = """
sources:
  main_db:
    type: postgresql
    url: postgresql://user:pass@localhost:5432/mydb
  local_db:
    type: sqlite
    path: /tmp/test.db
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            try:
                registry = load_sources_from_config(f.name)
                sources = registry.list_sources()
                assert len(sources) == 2
                names = {s.name for s in sources}
                assert names == {"main_db", "local_db"}
            finally:
                os.unlink(f.name)

    def test_load_empty_config(self):
        config_content = "sources: {}\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            try:
                registry = load_sources_from_config(f.name)
                assert len(registry.list_sources()) == 0
            finally:
                os.unlink(f.name)

    def test_unsupported_type_raises(self):
        config_content = """
sources:
  bad:
    type: dynamodb
    region: us-east-1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            try:
                with pytest.raises(ValueError, match="Unsupported source type"):
                    load_sources_from_config(f.name)
            finally:
                os.unlink(f.name)
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_sources_config.py -v`
Expected: FAIL — `src.sources.config` does not exist.

- [ ] **Step 5: Create src/sources/config.py**

```python
"""Source configuration — load sources from YAML config or DB URL."""

import yaml

from src.db import parse_db_url
from src.sources.base import DataSource
from src.sources.postgresql import PostgreSQLSource
from src.sources.registry import SourceRegistry
from src.sources.sqlite import SQLiteSource

SOURCE_TYPES = {
    "postgresql": lambda name, cfg: PostgreSQLSource(
        name=name,
        url=cfg["url"],
        search_path=cfg.get("search_path"),
    ),
    "sqlite": lambda name, cfg: SQLiteSource(
        name=name,
        path=cfg["path"],
    ),
}


def create_source_from_db_url(db_url: str, name: str = "default") -> DataSource:
    """Create a DataSource from a database URL (backwards compatible)."""
    scheme, connection_info = parse_db_url(db_url)

    if scheme in ("postgresql", "postgres"):
        return PostgreSQLSource(name=name, url=db_url)
    elif scheme == "sqlite":
        return SQLiteSource(name=name, path=connection_info)
    else:
        raise ValueError(f"Unsupported database scheme: {scheme}")


def load_sources_from_config(config_path: str) -> SourceRegistry:
    """Load sources from a YAML config file.

    Config format:
        sources:
          name:
            type: postgresql|sqlite
            url: ...  (for postgresql)
            path: ... (for sqlite)
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    registry = SourceRegistry()
    sources = config.get("sources", {})

    for name, cfg in sources.items():
        source_type = cfg.get("type", "")
        factory = SOURCE_TYPES.get(source_type)
        if factory is None:
            raise ValueError(
                f"Unsupported source type: '{source_type}' for source '{name}'. "
                f"Supported types: {', '.join(SOURCE_TYPES.keys())}"
            )
        source = factory(name, cfg)
        registry.register(name, source)

    return registry
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_sources_config.py -v`
Expected: All 7 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/sources/config.py tests/test_sources_config.py
git commit -m "feat: add YAML config loading and source factory"
```

---

### Task 7: Update PipelineContext and workflows to use DataSource

**Files:**
- Modify: `src/workflows/base.py`
- Modify: `src/workflows/build.py`
- Modify: `src/workflows/execute.py`
- Test: `tests/test_workflow_build.py` (new)
- Test: `tests/test_workflow_execute.py` (new)

- [ ] **Step 1: Write failing tests for the updated build workflow**

Create `tests/test_workflow_build.py`:

```python
from unittest.mock import MagicMock
from src.workflows.base import PipelineContext
from src.workflows.build import BuildWorkflow
from src.sources.postgresql import SQLNativeQuery
from src.ir.models import QueryIR, TableSource, FieldExpr


class TestBuildWorkflow:
    def test_uses_source_build_query(self):
        mock_source = MagicMock()
        mock_source.build_query.return_value = SQLNativeQuery(
            sql="SELECT * FROM users LIMIT 10;", params=[]
        )

        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10,
        )

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.query_ir = ir

        workflow = BuildWorkflow(default_limit=100)
        result = workflow.run(context)

        mock_source.build_query.assert_called_once_with(ir)
        assert result.native_query is not None
        assert result.error is None

    def test_applies_default_limit(self):
        mock_source = MagicMock()
        mock_source.build_query.return_value = SQLNativeQuery(sql="SELECT *", params=[])

        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
        )

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.query_ir = ir

        workflow = BuildWorkflow(default_limit=50)
        workflow.run(context)

        assert ir.limit == 50
```

- [ ] **Step 2: Write failing tests for the updated execute workflow**

Create `tests/test_workflow_execute.py`:

```python
from unittest.mock import MagicMock
from src.workflows.base import PipelineContext
from src.workflows.execute import ExecuteWorkflow
from src.sources.base import QueryResult
from src.sources.postgresql import SQLNativeQuery


class TestExecuteWorkflow:
    def test_uses_source_execute(self):
        mock_source = MagicMock()
        mock_source.is_connected.return_value = False
        mock_source.execute.return_value = QueryResult(
            rows=[{"id": 1, "name": "Alice"}],
            columns=["id", "name"],
            row_count=1,
            source_name="test_db",
        )

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.native_query = SQLNativeQuery(sql="SELECT * FROM users", params=[])

        workflow = ExecuteWorkflow()
        result = workflow.run(context)

        mock_source.connect.assert_called_once()
        mock_source.execute.assert_called_once_with(context.native_query)
        mock_source.disconnect.assert_called_once()
        assert result.rows == [{"id": 1, "name": "Alice"}]
        assert result.error is None

    def test_skips_connect_if_already_connected(self):
        mock_source = MagicMock()
        mock_source.is_connected.return_value = True
        mock_source.execute.return_value = QueryResult(
            rows=[], columns=[], row_count=0, source_name="db",
        )

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.native_query = SQLNativeQuery(sql="SELECT 1", params=[])

        workflow = ExecuteWorkflow()
        workflow.run(context)

        mock_source.connect.assert_not_called()

    def test_handles_execution_error(self):
        mock_source = MagicMock()
        mock_source.is_connected.return_value = True
        mock_source.execute.side_effect = Exception("Connection lost")

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.native_query = SQLNativeQuery(sql="SELECT 1", params=[])

        workflow = ExecuteWorkflow()
        result = workflow.run(context)

        assert result.error is not None
        assert "Connection lost" in result.error
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_workflow_build.py tests/test_workflow_execute.py -v`
Expected: FAIL — `PipelineContext` doesn't have `source` or `native_query` fields.

- [ ] **Step 4: Update src/workflows/base.py**

Replace the `PipelineContext` dataclass:

```python
@dataclass
class PipelineContext:
    """Shared state that flows through the pipeline."""

    # Input (set before pipeline starts)
    natural_language: str
    source: Any  # DataSource instance
    schema: Dict[str, Any]

    # Conversation history (for multi-turn sessions)
    conversation_history: Optional[List[Any]] = None

    # Stage outputs
    query_ir: Optional[QueryIR] = None
    native_query: Any = None  # NativeQuery from source.build_query()
    sql: Optional[str] = None  # Kept for backwards compat / logging
    params: Optional[List] = None  # Kept for backwards compat / logging
    rows: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None

    # Metadata
    timings: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    failed_stage: Optional[str] = None
```

- [ ] **Step 5: Update src/workflows/build.py**

```python
"""BuildWorkflow — converts validated QueryIR to a native query via the source."""

from src.workflows.base import Workflow, PipelineContext


class BuildWorkflow(Workflow):
    name = "build"

    def __init__(self, default_limit: int = 100):
        self.default_limit = default_limit

    def run(self, context: PipelineContext) -> PipelineContext:
        if context.query_ir and context.query_ir.limit is None:
            context.query_ir.limit = self.default_limit
        context.native_query = context.source.build_query(context.query_ir)
        # Store sql/params for logging if available
        if hasattr(context.native_query, "sql"):
            context.sql = context.native_query.sql
            context.params = getattr(context.native_query, "params", None)
        return context
```

- [ ] **Step 6: Update src/workflows/execute.py**

```python
"""ExecuteWorkflow — executes a native query via the data source."""

from src.workflows.base import Workflow, PipelineContext


class ExecuteWorkflow(Workflow):
    name = "execute"

    def run(self, context: PipelineContext) -> PipelineContext:
        source = context.source
        try:
            if not source.is_connected():
                source.connect()
            result = source.execute(context.native_query)
            context.rows = result.rows
        except Exception as e:
            context.error = str(e)
            context.failed_stage = self.name
        finally:
            source.disconnect()
        return context
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_workflow_build.py tests/test_workflow_execute.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add src/workflows/base.py src/workflows/build.py src/workflows/execute.py tests/test_workflow_build.py tests/test_workflow_execute.py
git commit -m "feat: update workflows to use DataSource instead of hardcoded SQL"
```

---

### Task 8: Update orchestrator and server to use SourceRegistry

**Files:**
- Modify: `src/orchestrator.py`
- Modify: `src/server.py`
- Modify: `src/config.py`

- [ ] **Step 1: Update src/config.py to add --config flag**

Add `config` field to `ServerSettings`:

```python
    config: str | None = Field(default=None, description="Path to sources YAML config file")
```

Make `db` optional (it has no default currently):

```python
    db: str | None = Field(default=None, description="Database connection string")
```

- [ ] **Step 2: Update src/orchestrator.py**

```python
"""
Query Orchestrator.

Coordinates the complete query processing pipeline using Workflow steps:
1. Parse natural language to IR
2. Validate IR against schema
3. Build native query from validated IR
4. Execute native query and return results
5. Summarize results using LLM
"""

from typing import Any, Dict, List

from src.ir.parser import IRParser
from src.sources.base import DataSource
from src.sources.registry import SourceRegistry
from src.summarizer import ResultSummarizer
from src.workflows import (
    Workflow,
    PipelineContext,
    ParseWorkflow,
    ValidateWorkflow,
    BuildWorkflow,
    ExecuteWorkflow,
    SummarizeWorkflow,
)
from src.logging_config import get_component_logger

logger = get_component_logger("orchestrator")


class QueryOrchestrator:
    """
    Orchestrates the complete query processing pipeline.

    Pipeline stages are Workflow instances chained together.
    Each stage reads from and writes to a shared PipelineContext.
    """

    def __init__(
        self,
        source: DataSource,
        llm_client: Any,
        system_prompt: str,
        schema: Dict[str, Any],
        default_limit: int = 100,
    ):
        self.source = source
        self.schema = schema

        parser = IRParser(llm_client, system_prompt)
        summarizer = ResultSummarizer(llm_client)

        self.steps: List[Workflow] = [
            ParseWorkflow(parser),
            ValidateWorkflow(),
            BuildWorkflow(default_limit=default_limit),
            ExecuteWorkflow(),
            SummarizeWorkflow(summarizer),
        ]

        logger.info(f"QueryOrchestrator initialized for source: {source.name}")
        logger.debug(f"Schema contains {len(schema)} tables")

    def process_query(self, natural_language: str, conversation_history=None) -> Dict[str, Any]:
        """Process a natural language query through the complete pipeline."""
        logger.info(f"Processing query: {natural_language}")

        context = PipelineContext(
            natural_language=natural_language,
            source=self.source,
            schema=self.schema,
            conversation_history=conversation_history,
        )

        for step in self.steps:
            context = step.execute(context)
            if context.error:
                break

        context.timings["total_ms"] = sum(context.timings.values())
        return self._to_result_dict(context)

    def _to_result_dict(self, context: PipelineContext) -> Dict[str, Any]:
        """Convert PipelineContext to the existing result dict format."""
        result: Dict[str, Any] = {
            "success": context.error is None,
            "error": context.error,
        }
        if context.summary:
            result["summary"] = context.summary
        return result

    def get_schema_summary(self) -> Dict[str, Any]:
        """Get a summary of the database schema."""
        summary = {}
        for table_name, table_info in self.schema.items():
            columns = table_info.get("columns", {})
            summary[table_name] = {
                "column_count": len(columns),
                "columns": list(columns.keys()),
            }
        return summary
```

- [ ] **Step 3: Update src/server.py create_app()**

Replace the `create_app` function body. The key changes:
- Import `SourceRegistry` and `create_source_from_db_url` from `src.sources.config`
- Import `load_sources_from_config` from `src.sources.config`
- Create a `SourceRegistry` from `--config` or `--db`
- Get the default source for the orchestrator
- Use `source.get_schema()` instead of `create_schema_extractor()`

```python
def create_app(
    db_url: str | None = None,
    config_path: str | None = None,
    llm_base_url: str = "http://localhost:1234/v1",
    llm_api_key: str = "lmstudio",
    llm_model: str = "qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
    temperature: float = 0.1,
    default_limit: int = 100,
) -> FastAPI:
    """Create and configure the FastAPI app."""
    global orchestrator, sessions, graph

    from src.sources.config import create_source_from_db_url, load_sources_from_config

    # Build source registry
    if config_path:
        registry = load_sources_from_config(config_path)
    else:
        registry = SourceRegistry()

    if db_url:
        source = create_source_from_db_url(db_url)
        registry.register(source.name, source)

    default_source = registry.get_default()

    # Extract schema from source
    source_schema = default_source.get_schema()

    llm_client = LLMClient(
        base_url=llm_base_url,
        api_key=llm_api_key,
        model=llm_model,
        temperature=temperature,
    )

    nl_converter = NaturalLanguageToIR(api_key=llm_api_key)
    system_prompt = nl_converter._build_system_prompt(source_schema)

    validator_schema = {
        col.name: {
            "columns": {f.name: {"type": f.type} for f in col.fields}
        }
        for col in source_schema.collections
    }

    orchestrator = QueryOrchestrator(
        source=default_source,
        llm_client=llm_client,
        system_prompt=system_prompt,
        schema=validator_schema,
        default_limit=default_limit,
    )

    sessions = set()

    checkpointer = InMemorySaver()
    graph = create_graph(
        orchestrator=orchestrator,
        llm_client=llm_client,
        system_prompt=system_prompt,
        checkpointer=checkpointer,
    )

    return app
```

- [ ] **Step 4: Update create_app_from_settings()**

```python
def create_app_from_settings(settings) -> FastAPI:
    """Create and configure the FastAPI app from a ServerSettings instance."""
    return create_app(
        db_url=settings.db,
        config_path=settings.config,
        llm_base_url=settings.llm_url,
        llm_api_key=settings.llm_key,
        llm_model=settings.llm_model,
        temperature=settings.temperature,
        default_limit=settings.default_limit,
    )
```

- [ ] **Step 5: Update NaturalLanguageToIR._build_system_prompt to accept SourceSchema**

The `_build_system_prompt` method currently expects a `DatabaseSchema` object. It needs to also accept `SourceSchema`. Check the method signature and update if needed — it may require a small adapter or the method may already work if it just iterates over tables/columns.

Read `src/llm/nl_to_ir.py` to check the `_build_system_prompt` method, then make the minimal change so it accepts `SourceSchema` (which has `.collections` with `.fields` instead of `.tables` with `.columns`).

- [ ] **Step 6: Verify the server still starts**

Run: `ODIN_LOG_LEVEL=WARNING python -c "from src.server import app; print('OK')"`
Expected: `OK`

- [ ] **Step 7: Run all tests**

Run: `pytest tests/test_server.py tests/test_web.py tests/test_sources_base.py tests/test_sources_registry.py tests/test_sources_config.py tests/test_sources_postgresql.py tests/test_sources_sqlite.py tests/test_workflow_build.py tests/test_workflow_execute.py -v`
Expected: All tests PASS. Some existing tests may need small fixes due to changed `PipelineContext` fields (e.g., `db_url` → `source`). Fix as needed.

- [ ] **Step 8: Commit**

```bash
git add src/orchestrator.py src/server.py src/config.py src/llm/nl_to_ir.py
git commit -m "feat: wire SourceRegistry into orchestrator and server"
```

---

### Task 9: Update existing tests for the new PipelineContext

**Files:**
- Modify: Various test files that create `PipelineContext` with `db_url`

- [ ] **Step 1: Find and fix all tests using old PipelineContext fields**

Run: `grep -r "db_url" tests/` to find all test files that reference the old field.

For each test that creates a `PipelineContext(... db_url=..., ...)`, change `db_url` to `source` and pass a `MagicMock()` instead:

```python
# Old:
context = PipelineContext(natural_language="test", db_url="sqlite:///test.db", schema={})

# New:
from unittest.mock import MagicMock
mock_source = MagicMock()
context = PipelineContext(natural_language="test", source=mock_source, schema={})
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: All tests pass (excluding pre-existing failures unrelated to this change).

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "fix: update tests for new PipelineContext with source field"
```
