# IR Examples

This directory contains example IR (Intermediate Representation) JSON files that demonstrate the query format.

## Files

### simple_query.json
A basic SELECT query with a simple filter condition.

**Natural Language:** "Get all active users"

**Generated SQL:**
```sql
SELECT * FROM users WHERE status = 'active';
```

### join_with_filters.json
A query with an INNER JOIN and multiple filter conditions.

**Natural Language:** "Show me all orders from premium users with order total over $100"

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

### nested_conditions.json
A query with nested logical conditions (OR containing AND).

**Natural Language:** "Find users who are either VIP members or have age over 10 and are active"

**Generated SQL:**
```sql
SELECT id, name, email
FROM users
WHERE tier = 'VIP' OR (age > 10 AND status = 'active');
```

### with_limit.json
A query demonstrating IN operator, ORDER BY, and LIMIT.

**Natural Language:** "Get top 10 most expensive products in electronics, books, or clothing categories"

**Generated SQL:**
```sql
SELECT *
FROM products
WHERE category IN ('electronics', 'books', 'clothing')
ORDER BY price DESC
LIMIT 10;
```

## Using These Examples

### Loading and Validating

```python
import json
from src.ir.models import QueryIR
from src.ir.validator import IRValidator

# Load the IR from JSON
with open('examples/simple_query.json') as f:
    ir_data = json.load(f)

# Parse into Pydantic model
query_ir = QueryIR(**ir_data)

# Validate against schema
schema = {
    "users": {"id": "int", "name": "str", "email": "str", "status": "str", "tier": "str", "age": "int"},
    "orders": {"id": "int", "user_id": "int", "total": "float", "created_at": "datetime"},
    "products": {"id": "int", "name": "str", "price": "float", "category": "str"}
}

validator = IRValidator(schema)
validator.validate(query_ir)

print("✓ IR is valid!")
```

### Converting to SQL

```python
# Once SQLBuilder is implemented:
from src.sql.builder import SQLBuilder

builder = SQLBuilder()
sql_query = builder.build(query_ir)
print(sql_query)
```

## Creating Your Own IR

You can create IR structures either:

1. **From JSON** (as shown above)
2. **Programmatically using Pydantic models:**

```python
from src.ir.models import QueryIR, TableSource, FieldExpr, ConditionExpr

query = QueryIR(
    operation="SELECT",
    source=TableSource(table="users"),
    fields=[FieldExpr(field="*")],
    filters=ConditionExpr(field="status", op="=", value="active")
)

# Export to JSON
print(query.model_dump_json(indent=2))
```

## Schema Requirements

For these examples to validate successfully, ensure your database schema includes:

- **users** table: id (int), name (str), email (str), status (str), tier (str), age (int)
- **orders** table: id (int), user_id (int), total (float), created_at (datetime)
- **products** table: id (int), name (str), price (float), category (str)
