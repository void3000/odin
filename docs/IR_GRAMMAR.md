# IR Grammar Specification

## Overview

This document provides a formal grammar specification for the Odin Intermediate Representation (IR). The IR is a structured format that serves as an intermediary between natural language queries and SQL.

## Notation

- `::=` means "is defined as"
- `|` separates alternatives
- `[]` indicates optional elements
- `{}` indicates repetition (zero or more)
- `<>` indicates non-terminals
- `""` indicates literal strings
- Type annotations follow `:` (e.g., `field: string`)

## Grammar Rules

### Top-Level Query

```
<QueryIR> ::= {
    operation: <Operation>,
    source: <TableSource>,
    fields: <FieldList>,
    [joins: <JoinList>],
    [filters: <FilterExpr>],
    [order_by: <OrderList>],
    [limit: <Limit>]
}

<Operation> ::= "SELECT"

<Limit> ::= integer >= 1
```

**Constraints:**
- `fields` must contain at least one element
- `limit` must be a positive integer
- All referenced tables must exist in the database schema
- All referenced fields must exist in their respective tables

### Table Reference

```
<TableSource> ::= {
    table: <TableName>
}

<TableName> ::= string
```

**Constraints:**
- `table` must be a non-empty string
- `table` must exist in the database schema

### Field Selection

```
<FieldList> ::= [ <FieldExpr> {, <FieldExpr>} ]

<FieldExpr> ::= {
    field: <FieldName>,
    [table: <TableName>],
    [alias: <AliasName>]
}

<FieldName> ::= string | "*"
<AliasName> ::= string
```

**Constraints:**
- `field` must be non-empty
- `field` can be "*" (wildcard) or a valid column name
- `table` is required when multiple tables are in scope and field names overlap
- `alias` provides an alternative name for the field in results

**Examples:**

```json
// Simple field
{"field": "name"}

// Qualified field from specific table
{"field": "email", "table": "users"}

// Field with alias
{"field": "total_price", "alias": "price"}

// Wildcard selection
{"field": "*"}
```

### Join Operations

```
<JoinList> ::= [ <JoinExpr> {, <JoinExpr>} ]

<JoinExpr> ::= {
    type: <JoinType>,
    table: <TableName>,
    on: <ConditionExpr>
}

<JoinType> ::= "INNER" | "LEFT" | "RIGHT"
```

**Constraints:**
- `type` must be one of the supported join types
- `table` must exist in the database schema
- `on` must be a `ConditionExpr` (not a `LogicalExpr`)
- Join conditions typically reference fields from both the source table and the joined table

**Examples:**

```json
// INNER JOIN
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

// LEFT JOIN
{
  "type": "LEFT",
  "table": "profiles",
  "on": {
    "field": "user_id",
    "table": "profiles",
    "op": "=",
    "value": {"field": "id", "table": "users"}
  }
}
```

### Filter Expressions (WHERE Clause)

```
<FilterExpr> ::= <ConditionExpr> | <LogicalExpr>

<ConditionExpr> ::= {
    field: <FieldName>,
    [table: <TableName>],
    op: <Operator>,
    value: <Value>
}

<LogicalExpr> ::= {
    logic: <LogicalOp>,
    conditions: [ <FilterExpr>, <FilterExpr> {, <FilterExpr>} ]
}

<Operator> ::= "=" | "!=" | ">" | ">=" | "<" | "<=" | "LIKE" | "IN"

<LogicalOp> ::= "AND" | "OR"

<Value> ::= <ScalarValue> | <ListValue> | <FieldReference>

<ScalarValue> ::= string | integer | float | boolean

<ListValue> ::= [ <ScalarValue> {, <ScalarValue>} ]

<FieldReference> ::= {
    field: <FieldName>,
    [table: <TableName>]
}
```

**Constraints:**

**Operator Constraints:**
- `LIKE` requires:
  - Field must be of string type
  - Value must be a string
- `IN` requires:
  - Value must be a non-empty list
  - List elements must match field type
- Comparison operators (`>`, `>=`, `<`, `<=`) require:
  - Field must be of numeric type
  - Value must be numeric or a field reference
- Equality operators (`=`, `!=`) accept any type

**LogicalExpr Constraints:**
- `conditions` must contain at least 2 elements
- Each condition can be either a `ConditionExpr` or another `LogicalExpr` (recursive)

**Examples:**

```json
// Simple condition
{"field": "status", "op": "=", "value": "active"}

// Numeric comparison
{"field": "age", "op": ">=", "value": 18}

// Pattern matching
{"field": "email", "op": "LIKE", "value": "%@example.com"}

// Set membership
{"field": "category", "op": "IN", "value": ["electronics", "books"]}

// AND condition
{
  "logic": "AND",
  "conditions": [
    {"field": "status", "op": "=", "value": "active"},
    {"field": "age", "op": ">=", "value": 18}
  ]
}

// Nested logical expression: (A OR B) AND C
{
  "logic": "AND",
  "conditions": [
    {
      "logic": "OR",
      "conditions": [
        {"field": "tier", "op": "=", "value": "premium"},
        {"field": "tier", "op": "=", "value": "VIP"}
      ]
    },
    {"field": "status", "op": "=", "value": "active"}
  ]
}
```

### Sort Order

```
<OrderList> ::= [ <OrderExpr> {, <OrderExpr>} ]

<OrderExpr> ::= {
    field: <FieldName>,
    [table: <TableName>],
    direction: <Direction>
}

<Direction> ::= "ASC" | "DESC"
```

**Constraints:**
- `field` must exist in the database schema
- `table` is required when multiple tables are in scope
- `direction` must be either "ASC" (ascending) or "DESC" (descending)

**Examples:**

```json
// Single sort
[{"field": "created_at", "direction": "DESC"}]

// Multiple sort criteria
[
  {"field": "status", "direction": "ASC"},
  {"field": "created_at", "direction": "DESC"}
]

// Sort with table qualifier
[{"field": "total", "table": "orders", "direction": "DESC"}]
```

## Type System

### Field Types

The IR validator enforces type compatibility between operators and field types:

```
<FieldType> ::= "int" | "integer" | "float" | "double" | "decimal" | "numeric"
              | "str" | "string" | "text" | "varchar"
              | "bool" | "boolean"
              | "date" | "datetime" | "timestamp"
```

### Operator Type Compatibility

| Operator | Compatible Field Types | Compatible Value Types |
|----------|------------------------|------------------------|
| `=`, `!=` | Any | Matching field type or field reference |
| `>`, `>=`, `<`, `<=` | Numeric types | Numeric or field reference |
| `LIKE` | String types | String only |
| `IN` | Any | List of matching field type |

## Validation Rules

### Structural Validation (Pydantic)

1. All required fields must be present
2. Field types must match their declared types
3. Enums must use valid values
4. Lists must meet minimum length requirements
5. Integers must meet range constraints

### Semantic Validation (IRValidator)

1. **Table Existence:**
   - All referenced tables must exist in the schema
   - This includes `source.table` and `joins[].table`

2. **Field Existence:**
   - All referenced fields must exist in their tables
   - Wildcards (`*`) are always valid

3. **Table Scope:**
   - Fields in multi-table queries should be qualified when ambiguous
   - Joined tables are added to the available scope

4. **Type Compatibility:**
   - Operators must be compatible with field types
   - Values must match field types

5. **Logical Expressions:**
   - Must contain at least 2 conditions
   - Can be nested arbitrarily deep

## Complete Examples

### Example 1: Simple Query

```json
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

**Equivalent SQL:**
```sql
SELECT * FROM users WHERE status = 'active';
```

### Example 2: Join with Filters

```json
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
  ],
  "limit": 10
}
```

**Equivalent SQL:**
```sql
SELECT
  users.name,
  orders.total,
  orders.created_at AS order_date
FROM users
INNER JOIN orders ON users.id = orders.user_id
WHERE users.tier = 'premium' AND orders.total > 100
ORDER BY orders.created_at DESC
LIMIT 10;
```

### Example 3: Nested Logical Conditions

```json
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
          {"field": "age", "op": ">", "value": 10},
          {"field": "status", "op": "=", "value": "active"}
        ]
      }
    ]
  }
}
```

**Equivalent SQL:**
```sql
SELECT id, name, email
FROM users
WHERE tier = 'VIP' OR (age > 10 AND status = 'active');
```

## Grammar Extensions (Future)

The following extensions are planned for future versions:

### Aggregate Functions

```
<FieldExpr> ::= {
    field: <FieldName>,
    [table: <TableName>],
    [alias: <AliasName>],
    [function: <AggregateFunction>]
}

<AggregateFunction> ::= "COUNT" | "SUM" | "AVG" | "MIN" | "MAX"
```

### GROUP BY Clause

```
<QueryIR> ::= {
    ...,
    [group_by: <GroupByList>],
    [having: <FilterExpr>]
}

<GroupByList> ::= [ <FieldExpr> {, <FieldExpr>} ]
```

### Subqueries

```
<Value> ::= <ScalarValue> | <ListValue> | <FieldReference> | <SubQuery>

<SubQuery> ::= {
    subquery: <QueryIR>
}
```

### INSERT/UPDATE/DELETE

```
<Operation> ::= "SELECT" | "INSERT" | "UPDATE" | "DELETE"

<InsertData> ::= {
    values: [ {field: value, ...} ]
}

<UpdateData> ::= {
    set: {field: value, ...}
}
```

## Error Handling

### Structural Errors (Pydantic ValidationError)

**Missing required field:**
```
ValidationError: 1 validation error for QueryIR
fields
  field required (type=value_error.missing)
```

**Invalid enum value:**
```
ValidationError: 1 validation error for QueryIR
operation
  unexpected value; permitted: 'SELECT' (type=value_error.const)
```

**Type mismatch:**
```
ValidationError: 1 validation error for QueryIR
limit
  value is not a valid integer (type=type_error.integer)
```

### Semantic Errors (IRValidator)

**Table not found:**
```
TableNotFoundError: Table 'orders' not found in schema.
Available tables: users, products
```

**Field not found:**
```
FieldNotFoundError: Field 'email' not found in table 'orders'.
Available fields: id, user_id, total, status
```

**Type mismatch:**
```
TypeMismatchError: LIKE operator requires string field, got 'int'
```

**Operator value mismatch:**
```
TypeMismatchError: IN operator requires list value, got str
```

## Best Practices

### 1. Always Qualify Fields in Joins

**Good:**
```json
{
  "field": "id",
  "table": "users"
}
```

**Avoid:**
```json
{
  "field": "id"
}
```

### 2. Use Specific Types

Match your schema's type system exactly. If your database uses `varchar`, your schema should use `"str"` or `"string"`.

### 3. Minimize Nesting Depth

Keep logical expressions as flat as possible for readability and debugging.

**Good:**
```json
{
  "logic": "AND",
  "conditions": [A, B, C]
}
```

**Avoid (when possible):**
```json
{
  "logic": "AND",
  "conditions": [
    A,
    {
      "logic": "AND",
      "conditions": [B, C]
    }
  ]
}
```

### 4. Validate Early

Always validate IR immediately after generation, before attempting SQL translation.

```python
# Generate IR (from LLM or programmatically)
query_ir = generate_ir(natural_language_query)

# Validate immediately
validator = IRValidator(schema)
validator.validate(query_ir)  # Fails fast if invalid

# Only then translate to SQL
sql = sql_builder.build(query_ir)
```

## References

- [DESIGN.md](DESIGN.md) - Complete architecture and design decisions
- [models.py](../src/ir/models.py) - Pydantic model implementations
- [validator.py](../src/ir/validator.py) - Semantic validation implementation
- [examples/](../examples/) - Working IR examples
