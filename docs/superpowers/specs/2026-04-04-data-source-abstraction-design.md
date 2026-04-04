# Data Source Abstraction Design

Generalize Odin from a single-database SQL pipeline into a pluggable multi-source query platform. Each data source (PostgreSQL, CloudWatch, Elasticsearch, etc.) implements a common protocol. One source per query for v1; cross-source correlation comes later.

## Motivation

Odin currently only queries SQL databases. To support debugging across logs and databases ("find the error log and the matching DB row for request X"), we need a source-agnostic pipeline. This spec covers the foundational abstraction layer that makes all sources look the same to the pipeline.

## Scope

- `DataSource` protocol that all sources implement
- Shared IR with optional source-specific extensions (time range, full-text)
- Source registry with YAML config file support
- Pipeline changes to use the registry instead of a single `db_url`
- PostgreSQL and SQLite wrapped as `DataSource` implementations
- Backwards compatible with current `--db` CLI usage

**Out of scope:** New source implementations (CloudWatch, Elasticsearch), cross-source queries, LLM auto-routing between sources (uses simple selection for v1).

## DataSource Protocol

Every source implements this single protocol:

```python
class DataSource(Protocol):
    name: str                    # e.g., "main_db", "app_logs"
    source_type: str             # e.g., "database", "logs", "metrics"

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool: ...
    def get_schema(self) -> SourceSchema: ...
    def get_capabilities(self) -> SourceCapabilities: ...
    def build_query(self, ir: QueryIR) -> NativeQuery: ...
    def execute(self, query: NativeQuery) -> QueryResult: ...
```

### SourceSchema

Replaces the current `DatabaseSchema` with a more general model. For databases: tables and columns. For log sources: log groups and known fields. For search: indices and mappings. All expressed in the same Pydantic model.

```python
class SourceField(BaseModel):
    name: str
    type: str
    description: str | None = None

class SourceCollection(BaseModel):
    """A table, log group, index, or other queryable unit."""
    name: str
    fields: list[SourceField]
    description: str | None = None

class SourceSchema(BaseModel):
    collections: list[SourceCollection]
```

### SourceCapabilities

Extends the current `QueryCapabilities`:

```python
class SourceCapabilities(BaseModel):
    supports_joins: bool = False
    supports_aggregates: bool = False
    supports_time_range: bool = False
    supports_full_text: bool = False
    supports_filters: bool = True
    supported_operators: set[str] = {"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE"}
    max_results: int | None = None
```

### NativeQuery

Opaque per-source dataclass. PostgreSQL's is `(sql, params)`. A log source's would be `(query_string, log_group, time_range)`. The pipeline never inspects it — only the source that created it can execute it.

### QueryResult

Common output format — a list of dicts with column names, regardless of source:

```python
@dataclass
class QueryResult:
    rows: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    source_name: str
```

## Shared IR with Source Extensions

The existing `QueryIR` stays as the common language. Two new optional fields are added:

```python
class TimeRange(BaseModel):
    start: str   # ISO 8601 or relative ("1h ago")
    end: str | None = None  # None means "now"

class QueryIR(BaseModel):
    # ... existing fields unchanged ...
    time_range: TimeRange | None = None    # for log/metric sources
    full_text: str | None = None           # for full-text search sources
```

Each source's `build_query` reads what it needs and ignores what it doesn't. Database sources ignore `time_range`. Log sources ignore `joins`. The `SourceCapabilities` tells the LLM prompt which fields are relevant.

`TableSource.table` is reused across source types — for databases it's a table name, for CloudWatch it's a log group, for ES it's an index.

## Source Registry

Holds all configured sources, provides lookup:

```python
class SourceRegistry:
    def register(self, name: str, source: DataSource) -> None: ...
    def get(self, name: str) -> DataSource: ...
    def list_sources(self) -> list[SourceInfo]: ...
    def get_default(self) -> DataSource: ...
```

`SourceInfo` is a lightweight summary (name, type, collection count) for display in the UI and LLM prompting.

## Configuration

### Config file (sources.yaml)

```yaml
sources:
  main_db:
    type: postgresql
    url: postgresql://user:pass@localhost:5432/mydb

  app_logs:
    type: cloudwatch
    region: us-east-1
    log_group: /app/production
```

### CLI flags

- `--config sources.yaml` — load sources from config file
- `--db postgresql://...` — register a single database source named "default" (backwards compatible)
- Both can be combined: `--db` adds to config file sources

### Source type resolution

The `type` field in config maps to a built-in source class via a factory dict:

```python
SOURCE_TYPES = {
    "postgresql": PostgreSQLSource,
    "sqlite": SQLiteSource,
}
```

New sources register here. Eventually this becomes a plugin entry point mechanism.

## Pipeline Changes

The pipeline adds a "resolve source" step:

**Router → Resolve Source → Parse → Validate → Build → Execute → Summarize**

### Resolve Source

For v1, this is simple:
- If only one source is registered, use it (skip resolution).
- If multiple sources, the LLM picks which source to use based on the question and available source descriptions.
- User can override via the UI (future).

### PipelineContext changes

```python
@dataclass
class PipelineContext:
    natural_language: str
    source: DataSource          # replaces db_url
    schema: dict[str, Any]      # from source.get_schema()
    # ... rest unchanged ...
```

### Workflow changes

| Workflow | Change |
|---|---|
| `ParseWorkflow` | Uses `source.get_schema()` for LLM prompting. Already receives schema from context. |
| `ValidateWorkflow` | Uses `source.get_capabilities()` to check IR validity. |
| `BuildWorkflow` | Calls `source.build_query(ir)` instead of `SQLBuilder.build()`. |
| `ExecuteWorkflow` | Calls `source.execute(query)` instead of creating a connector. |
| `SummarizeWorkflow` | No change. |

### Orchestrator changes

Accepts `SourceRegistry` instead of `db_url`. Creates `PipelineContext` with the resolved source. For single-source setups, uses `registry.get_default()`.

### Server changes

Creates `SourceRegistry` from config file and/or `--db` flag. Passes registry to orchestrator.

## Source Implementations

### PostgreSQLSource

Wraps the existing `PostgreSQLBuilder` and `PostgreSQLConnector`:

```python
class PostgreSQLSource:
    name: str
    source_type = "database"

    def __init__(self, name: str, url: str): ...
    def connect(self): ...        # delegates to PostgreSQLConnector
    def get_schema(self): ...     # delegates to PostgreSQLSchemaExtractor
    def build_query(self, ir): ...  # delegates to PostgreSQLBuilder
    def execute(self, query): ...   # delegates to connector.execute_query
```

### SQLiteSource

Same pattern, wrapping `SQLiteConnector` and `SQLBuilder`.

No existing code is deleted — the source classes are wrappers that compose the existing components.

## Files Changed

| File | Action |
|---|---|
| `src/sources/__init__.py` | Create — package init |
| `src/sources/base.py` | Create — `DataSource` protocol, `SourceSchema`, `SourceCapabilities`, `NativeQuery`, `QueryResult` |
| `src/sources/registry.py` | Create — `SourceRegistry` class |
| `src/sources/postgresql.py` | Create — `PostgreSQLSource` wrapping existing builder + connector |
| `src/sources/sqlite.py` | Create — `SQLiteSource` wrapping existing builder + connector |
| `src/sources/config.py` | Create — YAML config loading, source factory |
| `src/ir/models.py` | Modify — add `TimeRange`, `time_range`, `full_text` to `QueryIR` |
| `src/orchestrator.py` | Modify — accept `SourceRegistry`, add source resolution |
| `src/workflows/base.py` | Modify — add `source` to `PipelineContext`, remove `db_url` |
| `src/workflows/build.py` | Modify — use `source.build_query()` |
| `src/workflows/execute.py` | Modify — use `source.execute()` |
| `src/server.py` | Modify — create registry from config/CLI |
| `src/config.py` | Modify — add `--config` flag |
| `pyproject.toml` | Modify — add `pyyaml` dependency |

**Not changed:** `src/graph.py`, `src/web/`, existing `src/query/` and `src/executor/` (kept as internal implementations used by source wrappers).

## Backwards Compatibility

- `--db postgresql://...` still works. Creates a single "default" source in the registry.
- Existing tests continue to work — source wrappers delegate to the same underlying code.
- The API contract (`/v1/query`, `/v1/sessions`) is unchanged.
- The web UI works without modification — it talks to the same API.
