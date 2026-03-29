# SQLBuilder Design

## Overview

The SQLBuilder is a deterministic translator that converts validated IR (Intermediate Representation) to safe, parameterized SQL queries. It sits between the IR validator and the database executor in the Odin pipeline.

## Responsibilities

1. **Deterministic Translation**: IR → SQL is always consistent and predictable
2. **SQL Generation**: Build syntactically correct SQL for target dialect
3. **Parameterization**: Use parameterized queries to prevent SQL injection
4. **Identifier Safety**: Properly escape table/column names
5. **Dialect Support**: Handle differences between SQL databases

## Architecture

```
┌─────────────┐
│  QueryIR    │ (validated)
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────┐
│      SQLBuilder                 │
│  ┌───────────────────────────┐  │
│  │  Dialect Strategy         │  │  (PostgreSQL, MySQL, SQLite)
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  Component Builders       │  │  (SELECT, FROM, JOIN, WHERE, etc.)
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  Identifier Escaper       │  │  (quotes table/column names)
│  └───────────────────────────┘  │
│  ┌───────────────────────────┐  │
│  │  Parameter Manager        │  │  (tracks placeholders & values)
│  └───────────────────────────┘  │
└─────────────┬───────────────────┘
              │
              ▼
┌─────────────────────────────────┐
│   SQLQuery                      │
│   - sql: str                    │
│   - params: list | dict         │
└─────────────────────────────────┘
```

## Class Design

### Core Classes

```python
from typing import Protocol, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum

@dataclass
class SQLQuery:
    """Result of SQL generation."""
    sql: str                          # The SQL query string
    params: List[Any] | Dict[str, Any]  # Parameter values
    param_style: str                  # 'qmark', 'numeric', 'named', etc.

class SQLDialect(Enum):
    """Supported SQL dialects."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"

class IdentifierQuoter(Protocol):
    """Protocol for quoting identifiers (table/column names)."""

    def quote_identifier(self, name: str) -> str:
        """Quote a single identifier."""
        ...

    def quote_qualified(self, table: str, column: str) -> str:
        """Quote a qualified identifier (table.column)."""
        ...

class ParameterManager:
    """Manages SQL parameter placeholders and values."""

    def __init__(self, style: str = "qmark"):
        self.style = style  # 'qmark' (?), 'numeric' ($1), 'named' (:name)
        self.params: List[Any] = []
        self.param_names: Dict[str, Any] = {}

    def add_param(self, value: Any) -> str:
        """Add a parameter and return its placeholder."""
        ...

    def get_params(self) -> List[Any] | Dict[str, Any]:
        """Get all parameter values."""
        ...

class SQLBuilder:
    """Main SQL builder class."""

    def __init__(self, dialect: SQLDialect = SQLDialect.POSTGRESQL):
        self.dialect = dialect
        self.quoter = self._get_quoter(dialect)
        self.param_manager = ParameterManager(self._get_param_style(dialect))

    def build(self, query_ir: QueryIR) -> SQLQuery:
        """Build SQL from IR."""
        ...

    # Component builders
    def _build_select(self, fields: List[FieldExpr]) -> str:
        """Build SELECT clause."""
        ...

    def _build_from(self, source: TableSource) -> str:
        """Build FROM clause."""
        ...

    def _build_joins(self, joins: List[JoinExpr]) -> str:
        """Build JOIN clauses."""
        ...

    def _build_where(self, filters: FilterExpr) -> str:
        """Build WHERE clause."""
        ...

    def _build_order_by(self, order_by: List[OrderExpr]) -> str:
        """Build ORDER BY clause."""
        ...

    def _build_limit(self, limit: int) -> str:
        """Build LIMIT clause."""
        ...
```

## Component Builders

### 1. SELECT Clause Builder

**Input:** `List[FieldExpr]`

**Logic:**
```python
def _build_select(self, fields: List[FieldExpr]) -> str:
    field_parts = []

    for field_expr in fields:
        # Handle wildcard
        if field_expr.field == "*":
            if field_expr.table:
                field_parts.append(f"{self.quoter.quote_identifier(field_expr.table)}.*")
            else:
                field_parts.append("*")
            continue

        # Build qualified field
        if field_expr.table:
            field_str = self.quoter.quote_qualified(field_expr.table, field_expr.field)
        else:
            field_str = self.quoter.quote_identifier(field_expr.field)

        # Add alias if present
        if field_expr.alias:
            field_str += f" AS {self.quoter.quote_identifier(field_expr.alias)}"

        field_parts.append(field_str)

    return "SELECT " + ", ".join(field_parts)
```

**Examples:**
```python
# Simple
[{"field": "name"}] → "SELECT \"name\""

# Qualified
[{"field": "email", "table": "users"}] → "SELECT \"users\".\"email\""

# With alias
[{"field": "total", "alias": "price"}] → "SELECT \"total\" AS \"price\""

# Wildcard
[{"field": "*"}] → "SELECT *"

# Multiple fields
[
    {"field": "name", "table": "users"},
    {"field": "total", "table": "orders", "alias": "order_total"}
]
→ "SELECT \"users\".\"name\", \"orders\".\"total\" AS \"order_total\""
```

### 2. FROM Clause Builder

**Input:** `TableSource`

**Logic:**
```python
def _build_from(self, source: TableSource) -> str:
    return f"FROM {self.quoter.quote_identifier(source.table)}"
```

**Examples:**
```python
{"table": "users"} → "FROM \"users\""
{"table": "orders"} → "FROM \"orders\""
```

### 3. JOIN Clause Builder

**Input:** `List[JoinExpr]`

**Logic:**
```python
def _build_joins(self, joins: List[JoinExpr] | None) -> str:
    if not joins:
        return ""

    join_parts = []
    for join_expr in joins:
        join_type = join_expr.type  # "INNER", "LEFT", "RIGHT"
        table = self.quoter.quote_identifier(join_expr.table)
        condition = self._build_condition(join_expr.on)

        join_parts.append(f"{join_type} JOIN {table} ON {condition}")

    return "\n".join(join_parts)
```

**Examples:**
```python
[{
    "type": "INNER",
    "table": "orders",
    "on": {"field": "id", "table": "users", "op": "=", "value": {"field": "user_id", "table": "orders"}}
}]
→ "INNER JOIN \"orders\" ON \"users\".\"id\" = \"orders\".\"user_id\""
```

### 4. WHERE Clause Builder (Recursive)

**Input:** `FilterExpr` (ConditionExpr | LogicalExpr)

**Logic:**
```python
def _build_where(self, filters: FilterExpr | None) -> str:
    if not filters:
        return ""

    condition_str = self._build_filter_expr(filters)
    return f"WHERE {condition_str}"

def _build_filter_expr(self, expr: FilterExpr) -> str:
    if isinstance(expr, ConditionExpr):
        return self._build_condition(expr)
    elif isinstance(expr, LogicalExpr):
        return self._build_logical_expr(expr)

def _build_condition(self, cond: ConditionExpr) -> str:
    # Build left side (field reference)
    if cond.table:
        left = self.quoter.quote_qualified(cond.table, cond.field)
    else:
        left = self.quoter.quote_identifier(cond.field)

    # Build operator
    op = cond.op

    # Build right side (value or field reference)
    if isinstance(cond.value, dict):
        # Field reference
        if "table" in cond.value:
            right = self.quoter.quote_qualified(cond.value["table"], cond.value["field"])
        else:
            right = self.quoter.quote_identifier(cond.value["field"])
    elif op == "IN":
        # IN operator with list
        placeholders = [self.param_manager.add_param(v) for v in cond.value]
        right = f"({', '.join(placeholders)})"
    else:
        # Regular value
        right = self.param_manager.add_param(cond.value)

    return f"{left} {op} {right}"

def _build_logical_expr(self, expr: LogicalExpr) -> str:
    logic_op = expr.logic  # "AND" or "OR"

    sub_conditions = [self._build_filter_expr(cond) for cond in expr.conditions]

    # Join with appropriate operator and parentheses
    joined = f" {logic_op} ".join(f"({c})" for c in sub_conditions)

    return f"({joined})"
```

**Examples:**
```python
# Simple condition
{"field": "status", "op": "=", "value": "active"}
→ "WHERE \"status\" = ?" with params=['active']

# IN operator
{"field": "category", "op": "IN", "value": ["a", "b", "c"]}
→ "WHERE \"category\" IN (?, ?, ?)" with params=['a', 'b', 'c']

# AND condition
{
    "logic": "AND",
    "conditions": [
        {"field": "status", "op": "=", "value": "active"},
        {"field": "age", "op": ">=", "value": 18}
    ]
}
→ "WHERE ((\"status\" = ?) AND (\"age\" >= ?))" with params=['active', 18]

# Nested OR with AND
{
    "logic": "OR",
    "conditions": [
        {"field": "tier", "op": "=", "value": "VIP"},
        {
            "logic": "AND",
            "conditions": [
                {"field": "status", "op": "=", "value": "active"},
                {"field": "age", "op": ">", "value": 10}
            ]
        }
    ]
}
→ "WHERE ((\"tier\" = ?) OR ((\"status\" = ?) AND (\"age\" > ?)))"
  with params=['VIP', 'active', 10]
```

### 5. ORDER BY Clause Builder

**Input:** `List[OrderExpr]`

**Logic:**
```python
def _build_order_by(self, order_by: List[OrderExpr] | None) -> str:
    if not order_by:
        return ""

    order_parts = []
    for order_expr in order_by:
        if order_expr.table:
            field = self.quoter.quote_qualified(order_expr.table, order_expr.field)
        else:
            field = self.quoter.quote_identifier(order_expr.field)

        direction = order_expr.direction  # "ASC" or "DESC"
        order_parts.append(f"{field} {direction}")

    return "ORDER BY " + ", ".join(order_parts)
```

**Examples:**
```python
[{"field": "created_at", "direction": "DESC"}]
→ "ORDER BY \"created_at\" DESC"

[
    {"field": "status", "direction": "ASC"},
    {"field": "created_at", "direction": "DESC"}
]
→ "ORDER BY \"status\" ASC, \"created_at\" DESC"
```

### 6. LIMIT Clause Builder

**Input:** `int`

**Logic:**
```python
def _build_limit(self, limit: int | None) -> str:
    if not limit:
        return ""

    # Different dialects handle LIMIT differently
    if self.dialect == SQLDialect.POSTGRESQL or self.dialect == SQLDialect.SQLITE:
        return f"LIMIT {limit}"
    elif self.dialect == SQLDialect.MYSQL:
        return f"LIMIT {limit}"
    # SQL Server uses TOP instead
```

**Examples:**
```python
10 → "LIMIT 10"
```

## Identifier Quoting

Different SQL databases use different quoting styles:

| Dialect | Quote Character | Example |
|---------|----------------|---------|
| PostgreSQL | `"` (double quote) | `"users"."email"` |
| MySQL | `` ` `` (backtick) | `` `users`.`email` `` |
| SQLite | `"` (double quote) | `"users"."email"` |
| SQL Server | `[]` (brackets) | `[users].[email]` |

**Implementation:**

```python
class PostgreSQLQuoter:
    def quote_identifier(self, name: str) -> str:
        # Escape internal quotes
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def quote_qualified(self, table: str, column: str) -> str:
        return f'{self.quote_identifier(table)}.{self.quote_identifier(column)}'

class MySQLQuoter:
    def quote_identifier(self, name: str) -> str:
        escaped = name.replace('`', '``')
        return f'`{escaped}`'

    def quote_qualified(self, table: str, column: str) -> str:
        return f'{self.quote_identifier(table)}.{self.quote_identifier(column)}'
```

## Parameter Styles

Different database adapters use different parameter styles:

| Style | Format | Example | Used By |
|-------|--------|---------|---------|
| `qmark` | `?` | `WHERE id = ?` | SQLite, MySQL |
| `numeric` | `$1, $2` | `WHERE id = $1` | PostgreSQL |
| `named` | `:name` | `WHERE id = :id` | Oracle |
| `format` | `%s` | `WHERE id = %s` | PostgreSQL (psycopg2) |
| `pyformat` | `%(name)s` | `WHERE id = %(id)s` | PostgreSQL (psycopg2) |

**Implementation:**

```python
class ParameterManager:
    def __init__(self, style: str = "qmark"):
        self.style = style
        self.params: List[Any] = []
        self.param_count = 0

    def add_param(self, value: Any) -> str:
        """Add parameter and return placeholder."""
        self.params.append(value)
        self.param_count += 1

        if self.style == "qmark":
            return "?"
        elif self.style == "numeric":
            return f"${self.param_count}"
        elif self.style == "named":
            param_name = f"param_{self.param_count}"
            return f":{param_name}"
        elif self.style == "format":
            return "%s"
        elif self.style == "pyformat":
            param_name = f"param_{self.param_count}"
            return f"%({param_name})s"

    def get_params(self) -> List[Any]:
        return self.params
```

## Complete Build Process

```python
def build(self, query_ir: QueryIR) -> SQLQuery:
    """Build complete SQL query from IR."""

    # Reset parameter manager for new query
    self.param_manager = ParameterManager(self._get_param_style(self.dialect))

    # Build components
    select_clause = self._build_select(query_ir.fields)
    from_clause = self._build_from(query_ir.source)
    join_clause = self._build_joins(query_ir.joins)
    where_clause = self._build_where(query_ir.filters)
    order_clause = self._build_order_by(query_ir.order_by)
    limit_clause = self._build_limit(query_ir.limit)

    # Combine into final query
    parts = [select_clause, from_clause]

    if join_clause:
        parts.append(join_clause)
    if where_clause:
        parts.append(where_clause)
    if order_clause:
        parts.append(order_clause)
    if limit_clause:
        parts.append(limit_clause)

    sql = "\n".join(parts)
    params = self.param_manager.get_params()

    return SQLQuery(
        sql=sql,
        params=params,
        param_style=self.param_manager.style
    )
```

## Example Translations

### Example 1: Simple Query

**IR:**
```json
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [{"field": "*"}],
  "filters": {"field": "status", "op": "=", "value": "active"}
}
```

**PostgreSQL Output:**
```python
SQLQuery(
    sql='SELECT *\nFROM "users"\nWHERE "status" = $1',
    params=['active'],
    param_style='numeric'
)
```

**MySQL Output:**
```python
SQLQuery(
    sql='SELECT *\nFROM `users`\nWHERE `status` = ?',
    params=['active'],
    param_style='qmark'
)
```

### Example 2: Complex Join Query

**IR:**
```json
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [
    {"field": "name", "table": "users"},
    {"field": "total", "table": "orders", "alias": "order_total"}
  ],
  "joins": [{
    "type": "INNER",
    "table": "orders",
    "on": {
      "field": "id", "table": "users", "op": "=",
      "value": {"field": "user_id", "table": "orders"}
    }
  }],
  "filters": {
    "logic": "AND",
    "conditions": [
      {"field": "tier", "table": "users", "op": "=", "value": "premium"},
      {"field": "total", "table": "orders", "op": ">", "value": 100}
    ]
  },
  "order_by": [{"field": "total", "table": "orders", "direction": "DESC"}],
  "limit": 10
}
```

**PostgreSQL Output:**
```sql
SELECT "users"."name", "orders"."total" AS "order_total"
FROM "users"
INNER JOIN "orders" ON "users"."id" = "orders"."user_id"
WHERE (("users"."tier" = $1) AND ("orders"."total" > $2))
ORDER BY "orders"."total" DESC
LIMIT 10
```
**Params:** `['premium', 100]`

## Security Considerations

### 1. Identifier Injection Prevention

**ALWAYS quote identifiers:**
```python
# GOOD
self.quoter.quote_identifier(field_name)

# BAD - vulnerable to injection
f'SELECT {field_name} FROM users'
```

**Validate against schema before building:**
```python
# IR should be validated by IRValidator first
# This ensures all table/field names exist in schema
# Schema acts as whitelist
```

### 2. Value Parameterization

**ALWAYS use parameters for values:**
```python
# GOOD
placeholder = self.param_manager.add_param(value)
sql = f"WHERE status = {placeholder}"

# BAD - vulnerable to SQL injection
sql = f"WHERE status = '{value}'"
```

### 3. No Dynamic SQL Construction

**Never concatenate user values:**
```python
# GOOD
WHERE "status" = ? with params=['active']

# BAD
WHERE "status" = 'active'
```

## Error Handling

```python
class SQLBuildError(Exception):
    """Base exception for SQL building errors."""
    pass

class UnsupportedOperationError(SQLBuildError):
    """Operation not supported by dialect."""
    pass

class InvalidIRError(SQLBuildError):
    """IR is invalid (should have been caught by validator)."""
    pass
```

## Testing Strategy

### Unit Tests
- Test each component builder in isolation
- Test parameter management
- Test identifier quoting
- Test each SQL dialect

### Integration Tests
- Test complete IR → SQL translation
- Test all examples from IR documentation
- Compare output with expected SQL

### Security Tests
- Verify all identifiers are quoted
- Verify all values are parameterized
- Test with malicious input (after validation)

## Usage Example

```python
from src.sql.builder import SQLBuilder, SQLDialect
from src.ir.models import QueryIR

# Load and validate IR
query_ir = QueryIR(**json.load(open('query.json')))
validator.validate(query_ir)

# Build SQL
builder = SQLBuilder(dialect=SQLDialect.POSTGRESQL)
result = builder.build(query_ir)

print(result.sql)
print(result.params)

# Execute with database
cursor.execute(result.sql, result.params)
```

## Performance Considerations

1. **No unnecessary string allocations** - Build lists and join once
2. **Reuse quoter and param manager** - Don't create new instances per build
3. **Lazy evaluation** - Only build components that exist in IR
4. **String formatting** - Use f-strings for best performance

## Future Extensions

### Aggregate Functions
```python
def _build_aggregate_field(self, field_expr: FieldExpr) -> str:
    if field_expr.function:
        field = self.quoter.quote_identifier(field_expr.field)
        return f"{field_expr.function}({field})"
    # ... normal field handling
```

### GROUP BY
```python
def _build_group_by(self, group_by: List[FieldExpr]) -> str:
    # Similar to ORDER BY but without direction
    ...
```

### Subqueries
```python
def _build_subquery(self, subquery_ir: QueryIR) -> str:
    # Recursively build subquery
    sub_result = self.build(subquery_ir)
    return f"({sub_result.sql})"
```

## Implementation Checklist

- [ ] SQLQuery dataclass
- [ ] SQLDialect enum
- [ ] IdentifierQuoter protocol and implementations
- [ ] ParameterManager class
- [ ] SQLBuilder class
- [ ] SELECT clause builder
- [ ] FROM clause builder
- [ ] JOIN clause builder
- [ ] WHERE clause builder (recursive)
- [ ] ORDER BY clause builder
- [ ] LIMIT clause builder
- [ ] Complete build() method
- [ ] Unit tests for each component
- [ ] Integration tests with IR examples
- [ ] Security tests
- [ ] Documentation and examples
