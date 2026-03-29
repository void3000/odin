# IR Quick Reference

A condensed reference for the Odin Intermediate Representation format.

## Basic Structure

```json
{
  "operation": "SELECT",
  "source": {"table": "table_name"},
  "fields": [...],
  "joins": [...],           // optional
  "filters": {...},         // optional
  "order_by": [...],        // optional
  "limit": 10               // optional
}
```

## Components

### Fields

```json
// Simple field
{"field": "name"}

// With table qualifier
{"field": "email", "table": "users"}

// With alias
{"field": "total_price", "alias": "price"}

// Wildcard
{"field": "*"}
```

### Joins

```json
{
  "type": "INNER",  // or "LEFT", "RIGHT"
  "table": "orders",
  "on": {
    "field": "id",
    "table": "users",
    "op": "=",
    "value": {"field": "user_id", "table": "orders"}
  }
}
```

### Filters - Simple Condition

```json
// Equality
{"field": "status", "op": "=", "value": "active"}

// Comparison
{"field": "age", "op": ">=", "value": 18}

// Pattern matching
{"field": "email", "op": "LIKE", "value": "%@example.com"}

// Set membership
{"field": "category", "op": "IN", "value": ["a", "b", "c"]}
```

### Filters - Logical (AND/OR)

```json
// AND condition
{
  "logic": "AND",
  "conditions": [
    {"field": "status", "op": "=", "value": "active"},
    {"field": "age", "op": ">=", "value": 18}
  ]
}

// Nested: (A OR B) AND C
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

### Order By

```json
// Single sort
[{"field": "created_at", "direction": "DESC"}]

// Multiple sorts
[
  {"field": "status", "direction": "ASC"},
  {"field": "created_at", "direction": "DESC"}
]

// With table qualifier
[{"field": "total", "table": "orders", "direction": "DESC"}]
```

## Operators

| Operator | Description | Field Types | Value Type |
|----------|-------------|-------------|------------|
| `=` | Equality | Any | Scalar or field ref |
| `!=` | Inequality | Any | Scalar or field ref |
| `>` | Greater than | Numeric | Number or field ref |
| `>=` | Greater or equal | Numeric | Number or field ref |
| `<` | Less than | Numeric | Number or field ref |
| `<=` | Less or equal | Numeric | Number or field ref |
| `LIKE` | Pattern match | String | String only |
| `IN` | Set membership | Any | List of scalars |

## Field Types

- **Numeric:** `int`, `integer`, `float`, `double`, `decimal`, `numeric`
- **String:** `str`, `string`, `text`, `varchar`
- **Boolean:** `bool`, `boolean`
- **Temporal:** `date`, `datetime`, `timestamp`

## Common Patterns

### Select all active users

```json
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [{"field": "*"}],
  "filters": {"field": "status", "op": "=", "value": "active"}
}
```

### Join with filter

```json
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [
    {"field": "name", "table": "users"},
    {"field": "total", "table": "orders"}
  ],
  "joins": [{
    "type": "INNER",
    "table": "orders",
    "on": {
      "field": "id", "table": "users",
      "op": "=",
      "value": {"field": "user_id", "table": "orders"}
    }
  }],
  "filters": {"field": "total", "table": "orders", "op": ">", "value": 100}
}
```

### Top N with sorting

```json
{
  "operation": "SELECT",
  "source": {"table": "products"},
  "fields": [{"field": "*"}],
  "order_by": [{"field": "price", "direction": "DESC"}],
  "limit": 10
}
```

### Complex filter (OR with AND)

```json
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [{"field": "*"}],
  "filters": {
    "logic": "OR",
    "conditions": [
      {"field": "tier", "op": "=", "value": "VIP"},
      {
        "logic": "AND",
        "conditions": [
          {"field": "status", "op": "=", "value": "active"},
          {"field": "age", "op": ">=", "value": 18}
        ]
      }
    ]
  }
}
```

## Validation Rules

**Required:**
- `operation` must be "SELECT"
- `source` must specify valid table
- `fields` must have at least one element

**Constraints:**
- Table names must exist in schema
- Field names must exist in their tables
- Operators must match field types
- `IN` values must be non-empty lists
- `LogicalExpr` must have 2+ conditions
- `limit` must be positive integer

## Python Usage

### Create IR programmatically

```python
from src.ir.models import QueryIR, TableSource, FieldExpr, ConditionExpr

query = QueryIR(
    operation="SELECT",
    source=TableSource(table="users"),
    fields=[FieldExpr(field="*")],
    filters=ConditionExpr(field="status", op="=", value="active")
)
```

### Load from JSON

```python
import json
from src.ir.models import QueryIR

with open('query.json') as f:
    data = json.load(f)

query = QueryIR(**data)
```

### Validate

```python
from src.ir.validator import IRValidator

schema = {
    "users": {"id": "int", "name": "str", "status": "str", "age": "int"}
}

validator = IRValidator(schema)
validator.validate(query)  # Raises if invalid
```

### Export to JSON

```python
# Get as dict
query_dict = query.model_dump()

# Get as JSON string
query_json = query.model_dump_json(indent=2)
```

## Error Messages

### Pydantic Validation Errors

```
ValidationError: field required
ValidationError: unexpected value; permitted: 'SELECT'
ValidationError: ensure this value is greater than or equal to 1
```

### Semantic Validation Errors

```
TableNotFoundError: Table 'orders' not found in schema
FieldNotFoundError: Field 'email' not found in table 'orders'
TypeMismatchError: LIKE operator requires string field, got 'int'
TypeMismatchError: IN operator requires list value, got str
```

## See Also

- [IR Grammar Specification](IR_GRAMMAR.md) - Complete formal grammar
- [Design Document](DESIGN.md) - Architecture and rationale
- [Examples](../examples/) - Working IR files with validation
