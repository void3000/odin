# QueryExecutor - Bridge Pattern Design

## Overview

The QueryExecutor uses the **Bridge Pattern** to separate the query execution abstraction from the database-specific connection implementations.

```
QueryExecutor (Abstraction)
    |
    v
DatabaseConnector (Implementation)
    |
    +-- PostgreSQLConnector
    +-- MySQLConnector
    +-- MongoDBConnector
    +-- DynamoDBConnector
```

## Why Bridge Pattern?

### Problem
- Query execution logic (retry, timeout, result mapping) is independent of connection details
- Different databases have different connection libraries (psycopg2, pymysql, pymongo, boto3)
- We want to change connection implementation without affecting execution logic
- We want to add new databases without modifying executor code

### Solution
The Bridge Pattern decouples:
- **Abstraction**: QueryExecutor (what to execute)
- **Implementation**: DatabaseConnector (how to connect)

This allows independent variation on both sides.

---

## Architecture

### 1. Abstraction Layer

```python
class QueryExecutor:
    """
    High-level query execution with retry logic, timeout, result mapping.

    Bridge pattern: Delegates connection/execution to DatabaseConnector.
    """

    def __init__(self, connector: DatabaseConnector):
        self.connector = connector  # Bridge to implementation

    def execute(self, query_result: QueryResult) -> ExecutionResult:
        """Execute query with retry and timeout logic."""

    def execute_batch(self, queries: List[QueryResult]) -> List[ExecutionResult]:
        """Execute multiple queries in batch."""

    def execute_transaction(self, queries: List[QueryResult]) -> List[ExecutionResult]:
        """Execute queries in a transaction."""
```

### 2. Implementation Interface

```python
class DatabaseConnector(Protocol):
    """
    Interface for database-specific connection implementations.

    Each connector wraps a specific database driver (psycopg2, pymysql, etc.)
    """

    def connect(self) -> None:
        """Establish database connection."""

    def disconnect(self) -> None:
        """Close database connection."""

    def execute_query(self, sql: str, params: List[Any]) -> RawResult:
        """Execute single query and return raw results."""

    def execute_many(self, queries: List[Tuple[str, List[Any]]]) -> List[RawResult]:
        """Execute multiple queries."""

    def begin_transaction(self) -> None:
        """Start transaction."""

    def commit(self) -> None:
        """Commit transaction."""

    def rollback(self) -> None:
        """Rollback transaction."""

    def is_connected(self) -> bool:
        """Check if connected."""
```

### 3. Concrete Implementations

```python
class PostgreSQLConnector(DatabaseConnector):
    """PostgreSQL connector using psycopg2."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.conn = None

class MySQLConnector(DatabaseConnector):
    """MySQL connector using pymysql."""

    def __init__(self, host: str, user: str, password: str, database: str):
        self.config = {...}
        self.conn = None
```

---

## Component Design

### QueryExecutor (Abstraction)

**Responsibilities**:
- Query execution orchestration
- Retry logic (on connection failure, deadlock, timeout)
- Timeout enforcement
- Result mapping (raw → structured)
- Error handling and logging
- Metrics collection (execution time, row count)

**Does NOT**:
- Know about specific database drivers
- Handle connection pooling (delegated to connector)
- Know SQL dialect (already handled by QueryBuilder)

### DatabaseConnector (Implementation)

**Responsibilities**:
- Database connection management
- Connection pooling (if needed)
- Execute SQL with parameters
- Transaction management
- Database-specific error translation

**Does NOT**:
- Build SQL queries (handled by QueryBuilder)
- Implement retry logic (handled by QueryExecutor)
- Format results (handled by QueryExecutor)

---

## Data Flow

```
IR → QueryBuilder → QueryResult(sql, params)
                        ↓
                  QueryExecutor
                        ↓
                DatabaseConnector → Database
                        ↓
                   RawResult
                        ↓
                  QueryExecutor (maps to)
                        ↓
                  ExecutionResult
```

### Key Types

```python
@dataclass
class RawResult:
    """Raw result from database connector."""
    rows: List[Tuple[Any, ...]]
    columns: List[str]
    rowcount: int

@dataclass
class ExecutionResult:
    """Processed result from executor."""
    rows: List[Dict[str, Any]]  # Mapped to dicts
    columns: List[str]
    rowcount: int
    execution_time_ms: float
    query_sql: str  # For debugging
```

---

## Usage Examples

### Basic Usage

```python
# Create connector
connector = PostgreSQLConnector(
    connection_string="postgresql://user:pass@localhost/db"
)

# Create executor with connector (Bridge pattern)
executor = QueryExecutor(connector)

# Build query
builder = PostgreSQLBuilder()
query_result = builder.build(query_ir)

# Execute
result = executor.execute(query_result)

print(f"Returned {result.rowcount} rows in {result.execution_time_ms}ms")
for row in result.rows:
    print(row)  # Dict: {"id": 1, "name": "Alice"}
```

### With Transaction

```python
executor = QueryExecutor(connector)

queries = [
    builder.build(insert_ir),
    builder.build(update_ir),
    builder.build(select_ir)
]

results = executor.execute_transaction(queries)
# All committed or all rolled back
```

### Switching Databases (Bridge Benefit)

```python
# Same executor code, different connector
postgres_executor = QueryExecutor(PostgreSQLConnector(...))
mysql_executor = QueryExecutor(MySQLConnector(...))

# Execute same IR on different databases
result1 = postgres_executor.execute(query_result)
result2 = mysql_executor.execute(query_result)
```

---

## Implementation Strategy

### Phase 1: Core Abstraction
1. Define `DatabaseConnector` Protocol
2. Implement `QueryExecutor` base class
3. Define result types (`RawResult`, `ExecutionResult`)

### Phase 2: PostgreSQL Connector
1. Implement `PostgreSQLConnector` with psycopg2
2. Connection pooling (optional)
3. Error translation

### Phase 3: Additional Connectors
1. `MySQLConnector` with pymysql
2. (Future) `MongoDBConnector`, `DynamoDBConnector`

### Phase 4: Advanced Features
1. Connection pooling
2. Retry logic with exponential backoff
3. Query timeout enforcement
4. Metrics and logging

---

## Error Handling Strategy

### Connector Level
- Translate database-specific errors to common exceptions
- `ConnectionError`, `QueryError`, `TransactionError`

### Executor Level
- Retry on transient errors (connection lost, deadlock)
- Fail fast on syntax errors, permission errors
- Detailed error context (query, params, execution time)

```python
class DatabaseError(Exception):
    """Base exception for database errors."""
    pass

class ConnectionError(DatabaseError):
    """Connection failed or lost."""
    pass

class QueryError(DatabaseError):
    """Query execution failed."""
    def __init__(self, sql: str, params: List[Any], original: Exception):
        self.sql = sql
        self.params = params
        self.original = original
```

---

## Connection Pooling

### Approach
- Each connector manages its own pool
- PostgreSQL: use psycopg2.pool
- MySQL: use pymysql with pooling library

```python
class PostgreSQLConnector:
    def __init__(self, connection_string: str, pool_size: int = 10):
        self.pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=pool_size,
            dsn=connection_string
        )

    def execute_query(self, sql: str, params: List[Any]) -> RawResult:
        conn = self.pool.getconn()
        try:
            # Execute query
            ...
        finally:
            self.pool.putconn(conn)
```

---

## Retry Logic

### Executor Retry Strategy

```python
class QueryExecutor:
    def __init__(
        self,
        connector: DatabaseConnector,
        max_retries: int = 3,
        retry_delay_ms: int = 100
    ):
        self.connector = connector
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms

    def execute(self, query_result: QueryResult) -> ExecutionResult:
        for attempt in range(self.max_retries):
            try:
                return self._execute_once(query_result)
            except ConnectionError as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(self.retry_delay_ms * (2 ** attempt) / 1000)
                self.connector.connect()  # Reconnect
            except QueryError:
                raise  # Don't retry syntax errors
```

---

## Testing Strategy

### Unit Tests
- Mock `DatabaseConnector` for testing `QueryExecutor`
- Test retry logic with simulated failures
- Test transaction commit/rollback

### Integration Tests
- Real database connections (use Docker containers)
- Test with actual PostgreSQL, MySQL
- Test connection pooling under load

### Example Mock

```python
class MockConnector(DatabaseConnector):
    def __init__(self):
        self.calls = []
        self.should_fail = False

    def execute_query(self, sql: str, params: List[Any]) -> RawResult:
        self.calls.append((sql, params))
        if self.should_fail:
            raise ConnectionError("Mock failure")
        return RawResult(rows=[], columns=[], rowcount=0)

def test_executor_retry():
    mock = MockConnector()
    mock.should_fail = True

    executor = QueryExecutor(mock, max_retries=3)

    with pytest.raises(ConnectionError):
        executor.execute(query_result)

    assert len(mock.calls) == 3  # Retried 3 times
```

---

## Comparison: Bridge vs Other Patterns

### Why NOT Adapter?
- Adapter converts one interface to another
- We don't have an existing interface to adapt
- We're designing both abstraction AND implementation

### Why NOT Strategy?
- Strategy is for algorithms (retry strategies, timeout strategies)
- We'll use Strategy WITHIN executor for retry logic
- Bridge is for separating abstraction from implementation

### Why Bridge?
- Two dimensions of variation:
  1. Execution logic (simple, transactional, batch)
  2. Database type (PostgreSQL, MySQL, MongoDB)
- Allows extending both independently
- Clean separation of concerns

---

## Class Diagram

```
┌─────────────────────────┐
│   QueryExecutor         │
│  (Abstraction)          │
├─────────────────────────┤
│ - connector: Connector  │◆────────┐
│ - max_retries: int      │         │
│ - timeout_ms: int       │         │
├─────────────────────────┤         │
│ + execute()             │         │
│ + execute_batch()       │         │
│ + execute_transaction() │         │
└─────────────────────────┘         │
                                    │ Bridge
        ┌───────────────────────────┘
        │
        ▼
┌──────────────────────────┐
│  DatabaseConnector       │
│  (Implementation)        │
├──────────────────────────┤
│ + connect()              │
│ + disconnect()           │
│ + execute_query()        │
│ + execute_many()         │
│ + begin_transaction()    │
│ + commit()               │
│ + rollback()             │
└──────────────────────────┘
        △
        │
        ├────────────────────┬────────────────────┐
        │                    │                    │
┌──────────────────┐  ┌─────────────────┐  ┌────────────────┐
│ PostgreSQL       │  │ MySQL           │  │ MongoDB        │
│ Connector        │  │ Connector       │  │ Connector      │
└──────────────────┘  └─────────────────┘  └────────────────┘
```

---

## Benefits

1. **Flexibility**: Add new databases without changing executor
2. **Testability**: Mock connectors for unit testing
3. **Maintainability**: Clear separation of concerns
4. **Reusability**: Same executor with different connectors
5. **Extensibility**: Add features to either side independently

---

## Next Steps

1. Implement `DatabaseConnector` Protocol
2. Implement `QueryExecutor` with retry logic
3. Implement `PostgreSQLConnector` with psycopg2
4. Write comprehensive tests (unit + integration)
5. Add connection pooling
6. Implement additional connectors (MySQL, MongoDB)
