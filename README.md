# Odin - LLM-to-SQL Pipeline

Natural language to SQL conversion pipeline using local LLMs (LM Studio) with support for multiple databases (PostgreSQL, MongoDB, SQLite).

## Features

- **Natural Language Queries**: Convert plain English to SQL using LM Studio
- **Multi-Database Support**: PostgreSQL, MongoDB, SQLite through unified interface
- **Bridge Pattern Architecture**: Clean separation between query execution and database implementation
- **Automatic Schema Extraction**: Introspect database schemas from live databases
- **Type-Safe IR**: Pydantic-based Intermediate Representation with validation
- **Production Ready**: 180+ passing tests, comprehensive error handling

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup LM Studio (Optional for NL queries)

1. Download [LM Studio](https://lmstudio.ai/)
2. Load a model (recommended: 7B-14B parameter instruction-tuned models)
3. Start local server (default: `http://localhost:1234`)

See [LM Studio Integration Guide](docs/LM_STUDIO_INTEGRATION.md) for details.

### 3. Run the Demo

```bash
python main.py
```

This will:
- Extract schema from Chinook SQLite database
- Run natural language query examples (if LM Studio available)
- Run programmatic query examples (JOINs, filters, etc.)

## Architecture

```
┌─────────────────────┐
│  Natural Language   │
│     "Show all       │
│      artists"       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    LM Studio        │
│   (Local LLM)       │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   IR (Pydantic)     │  ◄──── Can also construct manually
│   QueryIR Model     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Query Builder     │
│  (PostgreSQL/       │
│   MongoDB/SQLite)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Query Executor     │
│  (Bridge Pattern)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  DB Connector       │
│  (PostgreSQL/       │
│   MongoDB/SQLite)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     Results         │
│  (Dict rows)        │
└─────────────────────┘
```

## Usage Examples

### Natural Language Queries

```python
from src.llm.nl_to_ir import NaturalLanguageToIR
from src.schema.extractor import SQLiteSchemaExtractor
from src.query.postgresql import PostgreSQLBuilder
from src.executor.executor import QueryExecutor
from src.executor.connectors.sqlite import SQLiteConnector

# Extract schema
extractor = SQLiteSchemaExtractor("Chinook.db")
schema = extractor.extract_schema()

# Initialize components
nl_converter = NaturalLanguageToIR()
builder = PostgreSQLBuilder()
connector = SQLiteConnector(database="Chinook.db")
executor = QueryExecutor(connector=connector)
connector.connect()

# Convert natural language to SQL and execute
query_ir = nl_converter.convert("Show me all artists", schema)
query_result = builder.build(query_ir)
result = executor.execute(query_result)

print(result.rows)
```

### Programmatic Queries

```python
from src.ir.models import QueryIR, TableSource, FieldExpr, ConditionExpr, JoinExpr

# Build query using IR
query_ir = QueryIR(
    operation="SELECT",
    source=TableSource(table="Artist"),
    fields=[
        FieldExpr(field="Name", table="Artist", alias="artist"),
        FieldExpr(field="Title", table="Album", alias="album"),
    ],
    joins=[
        JoinExpr(
            type="INNER",
            table="Album",
            on=ConditionExpr(
                field="ArtistId",
                table="Artist",
                op="=",
                value={"field": "ArtistId", "table": "Album"}
            )
        )
    ],
    filters=ConditionExpr(
        field="Name",
        table="Artist",
        op="=",
        value="AC/DC"
    )
)

# Build and execute
query_result = builder.build(query_ir)
result = executor.execute(query_result)
```

## Project Structure

```
odin/
├── src/
│   ├── ir/               # Intermediate Representation (IR) models
│   │   └── models.py     # QueryIR, FieldExpr, ConditionExpr, etc.
│   ├── query/            # Query builders (IR → SQL/MongoDB)
│   │   ├── postgresql.py # PostgreSQL builder (also works for SQLite)
│   │   └── mongodb.py    # MongoDB builder
│   ├── executor/         # Query execution layer
│   │   ├── executor.py   # QueryExecutor (Bridge abstraction)
│   │   ├── connector.py  # DatabaseConnector protocol
│   │   ├── errors.py     # Common exception hierarchy
│   │   └── connectors/
│   │       ├── postgresql.py
│   │       ├── mongodb.py
│   │       └── sqlite.py
│   ├── schema/           # Database schema management
│   │   ├── schema.py     # Schema models (DatabaseSchema, TableDef, ColumnDef)
│   │   └── extractor.py  # Schema extraction from live databases
│   └── llm/              # LLM integration
│       └── nl_to_ir.py   # Natural language to IR converter
├── tests/                # 180+ tests
│   ├── test_ir_*.py      # IR model tests
│   ├── test_postgresql_*.py
│   ├── test_mongodb_*.py
│   ├── test_sqlite_*.py
│   ├── test_executor.py
│   └── test_joins_integration.py
├── docs/
│   ├── LM_STUDIO_INTEGRATION.md
│   ├── JOIN_TESTS_SUMMARY.md
│   ├── SQLITE_CONNECTOR_SUMMARY.md
│   └── EDGE_CASES.md
├── main.py               # Complete demo (NL + programmatic)
└── demo_joins.py         # JOIN examples (no LLM required)
```

## Supported Features

### Query Operations
- ✅ SELECT with field selection and aliases
- ✅ WHERE clauses with operators: `=`, `!=`, `>`, `>=`, `<`, `<=`, `LIKE`, `IN`
- ✅ Logical operators: `AND`, `OR` (nested)
- ✅ JOINs: `INNER`, `LEFT`, `RIGHT`
- ✅ ORDER BY (ASC/DESC, multiple columns)
- ✅ LIMIT

### Databases
- ✅ **PostgreSQL** - Production SQL database
- ✅ **SQLite** - Embedded SQL (automatic placeholder conversion)
- ✅ **MongoDB** - NoSQL document database

### Architecture Patterns
- ✅ **Bridge Pattern** - Executor ↔ Connector separation
- ✅ **Visitor Pattern** - IR → SQL tree walking
- ✅ **Strategy Pattern** - Database-specific builders
- ✅ **Protocol Pattern** - Type-safe connector interface

### Production Features
- ✅ Parameterized queries (SQL injection prevention)
- ✅ Transaction support (ACID)
- ✅ Connection pooling ready
- ✅ Retry logic with exponential backoff
- ✅ Comprehensive error handling
- ✅ Type validation (Pydantic)

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_joins_integration.py

# Run with coverage
pytest --cov=src

# Current status: 180 tests passing
```

### Test Coverage

- **IR Models**: 101 tests (validation, edge cases)
- **PostgreSQL Builder**: 48 tests (queries, JOINs, edge cases)
- **MongoDB Builder**: 19 tests (NoSQL query generation)
- **SQLite Connector**: 15 tests (placeholder conversion, transactions)
- **Executor**: 11 tests (retry logic, error handling)
- **JOIN Integration**: 13 tests (real database queries)

## Key Components

### IR (Intermediate Representation)

Type-safe query representation using Pydantic:

```python
class QueryIR(BaseModel):
    operation: Literal["SELECT"]
    source: TableSource
    fields: List[FieldExpr]
    joins: List[JoinExpr] | None
    filters: FilterExpr | None
    order_by: List[OrderExpr] | None
    limit: int | None
```

### Query Builders

Convert IR to database-specific queries:

- **PostgreSQLBuilder**: Generates SQL with numbered placeholders ($1, $2)
- **MongoDBBuilder**: Generates MongoDB aggregation pipelines
- Both return **GenericQueryResult** for database-agnostic handling

### Executor & Connectors

**Executor** (Bridge abstraction):
- Retry logic
- Error translation
- Result mapping
- Transaction management

**Connectors** (Bridge implementations):
- PostgreSQLConnector
- MongoDBConnector
- SQLiteConnector (with automatic $1→? conversion)

## Configuration

### LM Studio

Edit `src/llm/nl_to_ir.py`:

```python
def __init__(
    self,
    base_url: str = "http://localhost:1234/v1",
    model_name: str = "your-model-name",
    temperature: float = 0.1,
):
```

### Database Connection

```python
# PostgreSQL
from src.executor.connectors.postgresql import PostgreSQLConnector
connector = PostgreSQLConnector(
    host="localhost",
    port=5432,
    database="mydb",
    user="user",
    password="pass"
)

# SQLite
from src.executor.connectors.sqlite import SQLiteConnector
connector = SQLiteConnector(database="path/to/db.sqlite")

# MongoDB
from src.executor.connectors.mongodb import MongoDBConnector
connector = MongoDBConnector(
    connection_string="mongodb://localhost:27017",
    database="mydb"
)
```

## Performance

### Query Execution
- Simple SELECT: <10ms (SQLite)
- Complex JOIN (4 tables): ~20-50ms (SQLite)
- 180 tests complete in 0.16s

### LLM Conversion (LM Studio)
- Simple query: 1-3 seconds
- Complex query: 3-5 seconds
- Depends on model size and hardware

## Error Handling

Unified exception hierarchy:

```python
DatabaseError
├── ConnectionError
├── QueryError (includes SQL, params, original exception)
└── TransactionError
```

All errors preserve:
- Original exception
- Query details
- Stack trace

## Documentation

- [LM Studio Integration](docs/LM_STUDIO_INTEGRATION.md) - Complete setup guide
- [JOIN Tests Summary](docs/JOIN_TESTS_SUMMARY.md) - JOIN functionality coverage
- [SQLite Connector](docs/SQLITE_CONNECTOR_SUMMARY.md) - Placeholder conversion details
- [Edge Cases](docs/EDGE_CASES.md) - Identified edge cases and handling

## Examples

See working examples in:
- `main.py` - Natural language + programmatic queries
- `demo_joins.py` - Complex JOIN scenarios
- `tests/test_joins_integration.py` - Real database queries

## Chinook Database

The demo uses the Chinook sample database (music store):

**Tables**: Artist, Album, Track, Genre, Customer, Invoice, InvoiceLine, Employee, etc.

**Sample Queries**:
- "Show me all artists"
- "Find AC/DC's albums"
- "Show rock tracks longer than 5 minutes"
- "List customers who spent more than $10"
- "Find the longest tracks by genre"

## Future Enhancements

- [ ] Streaming LLM responses
- [ ] Query result caching
- [ ] More database connectors (MySQL, Oracle, etc.)
- [ ] Aggregate functions (SUM, COUNT, AVG, etc.)
- [ ] GROUP BY support
- [ ] Subqueries
- [ ] UNION operations
- [ ] Multi-turn conversations with context
- [ ] Query explanation mode

## Contributing

The codebase follows these principles:

1. **Type Safety**: Use Pydantic models for validation
2. **Separation of Concerns**: IR, Builder, Executor are independent
3. **Testing**: Comprehensive test coverage required
4. **Documentation**: Document design decisions
5. **Error Handling**: Preserve context, use typed exceptions

## License

[Specify your license here]

## Credits

Built with:
- [Pydantic](https://pydantic.dev/) - Type validation
- [OpenAI Python SDK](https://github.com/openai/openai-python) - LM Studio client
- [LM Studio](https://lmstudio.ai/) - Local LLM inference
- [Chinook Database](https://github.com/lerocha/chinook-database) - Sample data
