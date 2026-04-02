# Odin: LLM-to-SQL Pipeline Design

## Overview

Odin is a safe, structured pipeline for converting natural language queries into SQL. It uses a two-stage architecture that separates LLM output from SQL generation, ensuring security, predictability, and testability.

## Architecture

```
                    ┌─────────────────────────┐
                    │     REST API Layer       │
                    │  POST /v1/query          │
                    │  POST /v1/sessions       │
                    │  DELETE /v1/sessions/{id} │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Session Manager        │
                    │  (in-memory, TTL-based)  │
                    │  Conversation history    │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Query Orchestrator     │
                    │  Runs pipeline stages    │
                    └────────────┬────────────┘
                                 │
           ┌─────────────────────┼─────────────────────┐
           │                     │                     │
  ┌────────▼────────┐  ┌────────▼────────┐  ┌────────▼────────┐
  │   Parse (LLM)   │  │    Validate     │  │   Build (SQL)   │
  │  NL → IR        │  │  IR → Schema    │  │  IR → SQL       │
  │  + conversation │  │  check          │  │  deterministic  │
  │    history      │  │                 │  │                 │
  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘
           │                     │                     │
           └─────────────────────┼─────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Execute (Database)     │
                    │  SQLite / PostgreSQL     │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Summarize (LLM)       │
                    │  Results → NL summary   │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   JSON Response          │
                    │  { summary, success }    │
                    └─────────────────────────┘
```

### Components

1. **REST API Layer**: FastAPI server exposing query and session endpoints
2. **Session Manager**: In-memory session store with TTL-based expiry; tracks conversation history (question + summary pairs) for multi-turn follow-ups
3. **Query Orchestrator**: Runs the pipeline stages sequentially, managing `PipelineContext`
4. **Parse (LLM)**: Converts natural language to structured IR; includes conversation history when a session is active
5. **Validate**: Validates IR structure and semantics against the database schema
6. **Build (SQL)**: Deterministically translates validated IR to parameterized SQL
7. **Execute (Database)**: Runs the generated SQL against SQLite or PostgreSQL
8. **Summarize (LLM)**: Converts query results into a natural language summary

## Key Benefits

- **Security**: LLM never generates SQL directly, preventing injection attacks
- **Predictability**: IR format is strictly defined and validated
- **Testability**: Deterministic IR→SQL translation is easy to unit test
- **Database-agnostic**: SQLBuilder can target different SQL dialects
- **Debuggability**: IR can be inspected, logged, and modified before SQL generation
- **Type Safety**: IR enforces type constraints that prevent malformed queries

## Intermediate Representation (IR) Specification

### QueryIR

The root structure representing a complete SQL query.

```
QueryIR
├── operation        : "SELECT"                          (required)
├── source           : TableSource                       (required)
├── fields           : [FieldExpr, ...]                  (required, min 1)
├── joins            : [JoinExpr, ...]                   (optional)
├── filters          : FilterExpr                        (optional)
├── order_by         : [OrderExpr, ...]                  (optional)
└── limit            : int                               (optional)
```

**Fields:**
- `operation`: Currently only "SELECT" is supported (future: INSERT, UPDATE, DELETE)
- `source`: The primary table to query
- `fields`: List of fields to retrieve (minimum 1 required)
- `joins`: Optional list of table joins
- `filters`: Optional WHERE clause conditions (supports AND/OR trees)
- `order_by`: Optional sorting specifications
- `limit`: Optional row limit

### TableSource

Represents a table in the query.

```
TableSource
└── table            : string                            (required)
```

**Fields:**
- `table`: Name of the table (will be validated against schema)

### FieldExpr

Represents a field to be selected.

```
FieldExpr
├── field            : string                            (required)
├── table            : string                            (optional, for joins)
└── alias            : string                            (optional)
```

**Fields:**
- `field`: Column name or `*` for all columns
- `table`: Table qualifier (required when joining tables with overlapping column names)
- `alias`: Optional alias for the field in results (AS clause)

**Examples:**
```python
# Simple field
{"field": "name"}

# Qualified field from join
{"field": "email", "table": "users"}

# Field with alias
{"field": "total_price", "alias": "price"}
```

### JoinExpr

Represents a JOIN operation.

```
JoinExpr
├── type             : "INNER" | "LEFT" | "RIGHT"        (required)
├── table            : string                            (required)
└── on               : ConditionExpr                     (required)
```

**Fields:**
- `type`: Type of join (INNER, LEFT, RIGHT)
- `table`: Table to join
- `on`: Join condition (single ConditionExpr, not LogicalExpr)

**Example:**
```python
{
  "type": "INNER",
  "table": "orders",
  "on": {
    "field": "user_id",
    "table": "users",
    "op": "=",
    "value": {"field": "id", "table": "orders"}
  }
}
```

### FilterExpr (Recursive)

Represents WHERE clause conditions. Supports both leaf conditions and logical trees.

#### Leaf: ConditionExpr

```
ConditionExpr
├── field            : string                            (required)
├── table            : string                            (optional)
├── op               : "=" | "!=" | ">" | ">="          (required)
│                      "<" | "<=" | "LIKE" | "IN"
└── value            : string | int | float | [...]      (required)
```

**Fields:**
- `field`: Column name to filter on
- `table`: Table qualifier (for joins)
- `op`: Comparison operator
  - `=`, `!=`: Equality/inequality
  - `>`, `>=`, `<`, `<=`: Numeric comparisons
  - `LIKE`: Pattern matching (use `%` wildcards)
  - `IN`: Set membership
- `value`: Value to compare against
  - For `IN` operator: array of values `[1, 2, 3]`
  - For other operators: scalar value

**Examples:**
```python
# Simple equality
{"field": "status", "op": "=", "value": "active"}

# Numeric comparison
{"field": "age", "op": ">=", "value": 18}

# Pattern matching
{"field": "email", "op": "LIKE", "value": "%@example.com"}

# Set membership
{"field": "category", "op": "IN", "value": ["electronics", "books"]}
```

#### Node: LogicalExpr

```
LogicalExpr
├── logic            : "AND" | "OR"                      (required)
└── conditions       : [FilterExpr, ...]                 (required, min 2)
```

**Fields:**
- `logic`: Logical operator (AND/OR)
- `conditions`: Array of FilterExpr (can be ConditionExpr or nested LogicalExpr)

**Examples:**
```python
# AND condition
{
  "logic": "AND",
  "conditions": [
    {"field": "status", "op": "=", "value": "active"},
    {"field": "age", "op": ">=", "value": 18}
  ]
}

# Nested conditions: (status = 'active' AND age >= 18) OR role = 'admin'
{
  "logic": "OR",
  "conditions": [
    {
      "logic": "AND",
      "conditions": [
        {"field": "status", "op": "=", "value": "active"},
        {"field": "age", "op": ">=", "value": 18}
      ]
    },
    {"field": "role", "op": "=", "value": "admin"}
  ]
}
```

### OrderExpr

Represents an ORDER BY clause.

```
OrderExpr
├── field            : string                            (required)
├── table            : string                            (optional)
└── direction        : "ASC" | "DESC"                   (required)
```

**Fields:**
- `field`: Column name to sort by
- `table`: Table qualifier (for joins)
- `direction`: Sort direction (ASC for ascending, DESC for descending)

**Example:**
```python
[
  {"field": "created_at", "direction": "DESC"},
  {"field": "name", "direction": "ASC"}
]
```

## Complete IR Examples

### Example 1: Simple Query

**Natural Language:**
"Get all active users"

**IR:**
```python
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [{"field": "*"}],
  "filters": {
    "field": "status",
    "op": "=",
    "value": "active"
  }
}
```

**Generated SQL:**
```sql
SELECT * FROM users WHERE status = 'active';
```

### Example 2: Join with Filters

**Natural Language:**
"Show me all orders from premium users with order total over $100"

**IR:**
```python
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [
    {"field": "name", "table": "users"},
    {"field": "total", "table": "orders"},
    {"field": "created_at", "table": "orders", "alias": "order_date"}
  ],
  "joins": [
    {
      "type": "INNER",
      "table": "orders",
      "on": {
        "field": "id",
        "table": "users",
        "op": "=",
        "value": {"field": "user_id", "table": "orders"}
      }
    }
  ],
  "filters": {
    "logic": "AND",
    "conditions": [
      {"field": "tier", "table": "users", "op": "=", "value": "premium"},
      {"field": "total", "table": "orders", "op": ">", "value": 100}
    ]
  },
  "order_by": [
    {"field": "created_at", "table": "orders", "direction": "DESC"}
  ]
}
```

**Generated SQL:**
```sql
SELECT
  users.name,
  orders.total,
  orders.created_at AS order_date
FROM users
INNER JOIN orders ON users.id = orders.user_id
WHERE users.tier = 'premium' AND orders.total > 100
ORDER BY orders.created_at DESC;
```

### Example 3: Complex Nested Conditions

**Natural Language:**
"Find users who are either VIP members or have made more than 10 purchases and are active"

**IR:**
```python
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [
    {"field": "id"},
    {"field": "name"},
    {"field": "email"}
  ],
  "filters": {
    "logic": "OR",
    "conditions": [
      {"field": "tier", "op": "=", "value": "VIP"},
      {
        "logic": "AND",
        "conditions": [
          {"field": "purchase_count", "op": ">", "value": 10},
          {"field": "status", "op": "=", "value": "active"}
        ]
      }
    ]
  }
}
```

**Generated SQL:**
```sql
SELECT id, name, email
FROM users
WHERE tier = 'VIP' OR (purchase_count > 10 AND status = 'active');
```

## Implementation Guidelines

### 1. LLM Layer

**Responsibilities:**
- Parse natural language query
- Identify tables, fields, conditions, and operations
- Generate valid IR JSON

**Best Practices:**
- Use structured output with schema validation (e.g., JSON mode)
- Provide examples of IR for few-shot prompting
- Include database schema in prompt context
- Handle ambiguous queries by requesting clarification

**Prompt Template Structure:**
```
You are a SQL query assistant. Convert natural language to IR.

Database Schema:
[schema description]

IR Format:
[IR specification]

Examples:
[few-shot examples]

User Query: {user_query}

Output only valid IR JSON.
```

### 2. IR Validator

**Responsibilities:**
- Validate IR structure (schema conformance)
- Validate semantics (table/field existence)
- Type checking (operators match field types)
- Security checks (no suspicious patterns)

**Validation Steps:**
1. **Schema Validation**: Ensure IR matches defined structure
2. **Table Validation**: Verify all tables exist in schema
3. **Field Validation**: Verify all fields exist in their tables
4. **Type Validation**: Ensure operators match field types
5. **Logic Validation**: Ensure LogicalExpr has at least 2 conditions
6. **Join Validation**: Verify join conditions reference correct tables

**Error Handling:**
- Return specific error messages for invalid IR
- Suggest corrections when possible
- Log validation failures for LLM prompt improvement

### 3. SQLBuilder

**Responsibilities:**
- Translate IR to SQL deterministically
- Handle database-specific SQL dialects
- Properly escape identifiers and values
- Generate optimized SQL

**Translation Rules:**

**SELECT clause:**
```python
# If fields contain "*"
"SELECT *"

# Otherwise, join qualified fields
"SELECT " + ", ".join([
  f"{f['table']}.{f['field']} AS {f['alias']}" if 'table' and 'alias'
  else f"{f['table']}.{f['field']}" if 'table'
  else f"{f['field']} AS {f['alias']}" if 'alias'
  else f"{f['field']}"
  for f in fields
])
```

**FROM clause:**
```python
f"FROM {source['table']}"
```

**JOIN clauses:**
```python
for join in joins:
  f"{join['type']} JOIN {join['table']} ON {build_condition(join['on'])}"
```

**WHERE clause:**
```python
"WHERE " + build_filter(filters)
```

**ORDER BY clause:**
```python
"ORDER BY " + ", ".join([
  f"{o['table']}.{o['field']} {o['direction']}" if 'table'
  else f"{o['field']} {o['direction']}"
  for o in order_by
])
```

**LIMIT clause:**
```python
f"LIMIT {limit}"
```

**Security Considerations:**
- Always use parameterized queries or proper escaping
- Whitelist table/field names against schema
- Validate numeric values
- Escape string values
- Never use string concatenation for values

### 4. Database Executor

**Responsibilities:**
- Execute SQL with proper connection pooling
- Handle errors gracefully
- Return structured results
- Log queries for debugging

**Best Practices:**
- Use parameterized queries
- Set query timeouts
- Limit result set sizes
- Handle database-specific errors
- Transaction management (for future INSERT/UPDATE/DELETE)

## Future Enhancements

### Phase 1 (Complete)
- [x] SELECT queries with WHERE, JOIN, ORDER BY, LIMIT
- [x] IR validation
- [x] SQLBuilder implementation
- [x] LLM integration (OpenAI-compatible API)
- [x] REST API (FastAPI)
- [x] Result summarization (LLM)
- [x] SQLite and PostgreSQL support

### Phase 2 (In Progress)
- [ ] Multi-turn conversation sessions (TTL-based, in-memory)
- [ ] Aggregate functions (COUNT, SUM, AVG, MIN, MAX)
- [ ] GROUP BY and HAVING clauses
- [ ] Subqueries
- [ ] UNION operations

### Phase 3
- [ ] INSERT operations
- [ ] UPDATE operations
- [ ] DELETE operations
- [ ] Transaction support

### Phase 4
- [ ] Additional database dialects (MySQL)
- [ ] Query optimization hints
- [ ] Query caching
- [ ] Persistent session storage
- [ ] Execution plan analysis

## Security Considerations

### SQL Injection Prevention
- LLM never generates SQL directly
- All values are parameterized or properly escaped
- Table/field names validated against schema whitelist
- IR structure enforces type safety

### Access Control
- Future: Role-based access control in IR validator
- Future: Row-level security policies
- Future: Column-level permissions

### Rate Limiting
- Future: Query complexity scoring
- Future: Per-user query limits
- Future: Cost-based throttling

## Testing Strategy

### Unit Tests
- IR validator: Test all validation rules
- SQLBuilder: Test IR→SQL translation for all combinations
- Each component in isolation

### Integration Tests
- End-to-end: Natural language → IR → SQL → Results
- Multiple database backends
- Complex nested queries

### Security Tests
- SQL injection attempts via malformed IR
- Schema validation bypasses
- Type confusion attacks

### Performance Tests
- Query generation latency
- SQL execution performance
- Large result set handling

## Development Workflow

1. **Define Schema**: Create database schema definition
2. **Implement IR Validator**: Build validation logic
3. **Implement SQLBuilder**: Build deterministic translator
4. **Create LLM Prompt**: Design prompt for IR generation
5. **Test**: Comprehensive testing at each layer
6. **Iterate**: Refine based on real-world queries

## References

- [JSON Schema](https://json-schema.org/) for IR validation
- [SQL Standard](https://www.iso.org/standard/63555.html) for SQL semantics
- [OWASP SQL Injection](https://owasp.org/www-community/attacks/SQL_Injection) for security considerations
