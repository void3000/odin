# Subquery Design

## Overview

Nested queries (subqueries) can appear in multiple places in SQL:
1. **FROM clause** - Derived tables
2. **WHERE clause** - Scalar/list subqueries
3. **SELECT clause** - Scalar subqueries
4. **JOIN ON clause** - Subquery joins

## IR Extensions

### 1. TableSource with Subquery Support

Currently:
```python
TableSource = {
    "table": "users"
}
```

Extended:
```python
TableSource = {
    "table": "users"  # Table name
}
# OR
TableSource = {
    "subquery": QueryIR,  # Nested query
    "alias": "subq"       # Required for subqueries
}
```

### 2. ConditionExpr Value as Subquery

Currently:
```python
ConditionExpr = {
    "field": "id",
    "op": "IN",
    "value": [1, 2, 3]  # List of values
}
```

Extended:
```python
ConditionExpr = {
    "field": "id",
    "op": "IN",
    "value": {
        "subquery": QueryIR  # Nested query returning list
    }
}
```

### 3. FieldExpr with Scalar Subquery

Currently:
```python
FieldExpr = {
    "field": "name"
}
```

Extended:
```python
FieldExpr = {
    "field": "name"
}
# OR
FieldExpr = {
    "subquery": QueryIR,  # Nested query returning scalar
    "alias": "count"      # Required
}
```

## Updated IR Models

```python
from typing import Union

class SubqueryRef(BaseModel):
    """Reference to a nested query."""
    subquery: 'QueryIR'  # Forward reference for recursion

class TableSource(BaseModel):
    """Table source - either a table name or subquery."""
    table: str | None = None
    subquery: 'QueryIR' | None = None
    alias: str | None = None  # Required when using subquery

    @model_validator(mode='after')
    def validate_source(self):
        # Must have exactly one of table or subquery
        if (self.table is None) == (self.subquery is None):
            raise ValueError("Must specify exactly one of 'table' or 'subquery'")

        # Subquery requires alias
        if self.subquery and not self.alias:
            raise ValueError("Subquery in FROM requires an alias")

        return self

class FieldExpr(BaseModel):
    """Field expression - column or scalar subquery."""
    field: str | None = None
    table: str | None = None
    alias: str | None = None
    subquery: 'QueryIR' | None = None

    @model_validator(mode='after')
    def validate_field(self):
        # Must have exactly one of field or subquery
        if (self.field is None) == (self.subquery is None):
            raise ValueError("Must specify exactly one of 'field' or 'subquery'")

        # Subquery requires alias
        if self.subquery and not self.alias:
            raise ValueError("Subquery in SELECT requires an alias")

        return self

class ConditionExpr(BaseModel):
    """Condition - supports subqueries in value."""
    field: str
    table: str | None = None
    op: Literal["=", "!=", ">", ">=", "<", "<=", "IN", "LIKE", "EXISTS"]
    value: Union[str, int, float, List[Any], dict, 'QueryIR']

    # value can be:
    # - scalar: "active", 18, 3.14
    # - list: [1, 2, 3] (for IN)
    # - dict: {"field": "id", "table": "users"} (field reference)
    # - QueryIR: nested query
```

## PostgreSQL Builder Updates

### Recursive Build Method

```python
def build(self, query_ir: QueryIR) -> PostgreSQLQueryResult:
    """Build PostgreSQL query from IR (supports recursion)."""
    self.validate_ir(query_ir)

    # Note: Don't reset params here if called recursively
    # Only reset at top level
    if not hasattr(self, '_building_subquery'):
        self.params = []
        self.param_counter = 0
        self._building_subquery = False

    # Build components
    select_clause = self._build_select(query_ir.fields)
    from_clause = self._build_from(query_ir.source)
    join_clause = self._build_joins(query_ir.joins)
    where_clause = self._build_where(query_ir.filters)
    order_clause = self._build_order_by(query_ir.order_by)
    limit_clause = self._build_limit(query_ir.limit)

    # Combine
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

    # Only create result at top level
    if not self._building_subquery:
        return PostgreSQLQueryResult(sql=sql, params=self.params)
    else:
        # Return just SQL for recursive calls
        return sql
```

### Better Approach: Separate Method for Subqueries

```python
def build(self, query_ir: QueryIR) -> PostgreSQLQueryResult:
    """Build PostgreSQL query from IR (top-level only)."""
    self.validate_ir(query_ir)

    # Reset state
    self.params = []
    self.param_counter = 0

    # Build SQL
    sql = self._build_query(query_ir)

    return PostgreSQLQueryResult(sql=sql, params=self.params)

def _build_query(self, query_ir: QueryIR) -> str:
    """Build query recursively (used for subqueries)."""
    select_clause = self._build_select(query_ir.fields)
    from_clause = self._build_from(query_ir.source)
    join_clause = self._build_joins(query_ir.joins)
    where_clause = self._build_where(query_ir.filters)
    order_clause = self._build_order_by(query_ir.order_by)
    limit_clause = self._build_limit(query_ir.limit)

    parts = [select_clause, from_clause]
    if join_clause:
        parts.append(join_clause)
    if where_clause:
        parts.append(where_clause)
    if order_clause:
        parts.append(order_clause)
    if limit_clause:
        parts.append(limit_clause)

    return "\n".join(parts)
```

### Updated Component Builders

#### FROM Clause with Subquery Support

```python
def _build_from(self, source: TableSource) -> str:
    """Build FROM clause (supports subqueries)."""
    if source.table:
        # Simple table
        table_ref = self._quote_identifier(source.table)
        if source.alias:
            table_ref += f" AS {self._quote_identifier(source.alias)}"
        return f"FROM {table_ref}"

    elif source.subquery:
        # Subquery (recursive call)
        subquery_sql = self._build_query(source.subquery)
        alias = self._quote_identifier(source.alias)
        return f"FROM (\n{subquery_sql}\n) AS {alias}"

    else:
        raise QueryBuildError("TableSource must have table or subquery")
```

#### SELECT Clause with Scalar Subqueries

```python
def _build_select(self, fields: List[FieldExpr]) -> str:
    """Build SELECT clause (supports scalar subqueries)."""
    field_parts = []

    for field_expr in fields:
        # Scalar subquery
        if field_expr.subquery:
            subquery_sql = self._build_query(field_expr.subquery)
            field_str = f"(\n{subquery_sql}\n)"
            if field_expr.alias:
                field_str += f" AS {self._quote_identifier(field_expr.alias)}"
            field_parts.append(field_str)
            continue

        # Regular field handling
        if field_expr.field == "*":
            if field_expr.table:
                field_parts.append(f"{self._quote_identifier(field_expr.table)}.*")
            else:
                field_parts.append("*")
            continue

        if field_expr.table:
            field_str = self._quote_qualified(field_expr.table, field_expr.field)
        else:
            field_str = self._quote_identifier(field_expr.field)

        if field_expr.alias:
            field_str += f" AS {self._quote_identifier(field_expr.alias)}"

        field_parts.append(field_str)

    return "SELECT " + ", ".join(field_parts)
```

#### WHERE Clause with Subqueries

```python
def _build_condition(self, cond: ConditionExpr) -> str:
    """Build single condition (supports subqueries in value)."""
    # Build left side
    if cond.table:
        left = self._quote_qualified(cond.table, cond.field)
    else:
        left = self._quote_identifier(cond.field)

    op = cond.op

    # Build right side
    if isinstance(cond.value, QueryIR):
        # Subquery (recursive)
        subquery_sql = self._build_query(cond.value)

        if op == "EXISTS":
            # EXISTS doesn't need left side
            return f"EXISTS (\n{subquery_sql}\n)"
        elif op == "IN":
            return f"{left} IN (\n{subquery_sql}\n)"
        else:
            # Scalar subquery
            return f"{left} {op} (\n{subquery_sql}\n)"

    elif isinstance(cond.value, dict) and "field" in cond.value:
        # Field reference
        if "table" in cond.value:
            right = self._quote_qualified(cond.value["table"], cond.value["field"])
        else:
            right = self._quote_identifier(cond.value["field"])

    elif op == "IN":
        # IN with list
        placeholders = [self._add_param(v) for v in cond.value]
        right = f"({', '.join(placeholders)})"

    else:
        # Regular value
        right = self._add_param(cond.value)

    return f"{left} {op} {right}"
```

## Examples

### Example 1: Subquery in WHERE (IN clause)

**Natural Language:** "Get users who have placed orders"

**IR:**
```json
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [{"field": "*"}],
  "filters": {
    "field": "id",
    "op": "IN",
    "value": {
      "operation": "SELECT",
      "source": {"table": "orders"},
      "fields": [{"field": "user_id"}]
    }
  }
}
```

**Generated SQL:**
```sql
SELECT *
FROM "users"
WHERE "id" IN (
  SELECT "user_id"
  FROM "orders"
)
```

### Example 2: Subquery in FROM (Derived Table)

**Natural Language:** "Get average order total by user"

**IR:**
```json
{
  "operation": "SELECT",
  "source": {
    "subquery": {
      "operation": "SELECT",
      "source": {"table": "orders"},
      "fields": [
        {"field": "user_id"},
        {"field": "total", "alias": "order_total"}
      ]
    },
    "alias": "user_orders"
  },
  "fields": [
    {"field": "user_id", "table": "user_orders"},
    {"field": "order_total", "table": "user_orders"}
  ]
}
```

**Generated SQL:**
```sql
SELECT "user_orders"."user_id", "user_orders"."order_total"
FROM (
  SELECT "user_id", "total" AS "order_total"
  FROM "orders"
) AS "user_orders"
```

### Example 3: Scalar Subquery in SELECT

**Natural Language:** "Get users with their order count"

**IR:**
```json
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [
    {"field": "name"},
    {
      "subquery": {
        "operation": "SELECT",
        "source": {"table": "orders"},
        "fields": [{"field": "COUNT(*)", "alias": "cnt"}],
        "filters": {
          "field": "user_id",
          "table": "orders",
          "op": "=",
          "value": {"field": "id", "table": "users"}
        }
      },
      "alias": "order_count"
    }
  ]
}
```

**Generated SQL:**
```sql
SELECT "name", (
  SELECT COUNT(*) AS "cnt"
  FROM "orders"
  WHERE "orders"."user_id" = "users"."id"
) AS "order_count"
FROM "users"
```

### Example 4: EXISTS Subquery

**Natural Language:** "Get users who have at least one order"

**IR:**
```json
{
  "operation": "SELECT",
  "source": {"table": "users"},
  "fields": [{"field": "*"}],
  "filters": {
    "field": "",
    "op": "EXISTS",
    "value": {
      "operation": "SELECT",
      "source": {"table": "orders"},
      "fields": [{"field": "1"}],
      "filters": {
        "field": "user_id",
        "table": "orders",
        "op": "=",
        "value": {"field": "id", "table": "users"}
      }
    }
  }
}
```

**Generated SQL:**
```sql
SELECT *
FROM "users"
WHERE EXISTS (
  SELECT 1
  FROM "orders"
  WHERE "orders"."user_id" = "users"."id"
)
```

## Parameter Handling in Subqueries

**Important:** Parameters must be shared across all levels of nesting.

```python
def build(self, query_ir: QueryIR) -> PostgreSQLQueryResult:
    """Build query (top-level only)."""
    # Initialize shared state
    self.params = []
    self.param_counter = 0

    # Build recursively - params accumulate across all levels
    sql = self._build_query(query_ir)

    return PostgreSQLQueryResult(sql=sql, params=self.params)
```

When a subquery calls `_add_param()`, it adds to the same `self.params` list and increments the same `self.param_counter`. This ensures:

1. All parameters across all nesting levels are collected
2. Parameter numbering ($1, $2, $3...) is sequential across entire query
3. The final `params` list matches the order of placeholders in SQL

## Testing Strategy

```python
def test_subquery_in_where():
    """Test subquery in WHERE IN clause."""
    subquery = QueryIR(
        operation="SELECT",
        source=TableSource(table="orders"),
        fields=[FieldExpr(field="user_id")]
    )

    query_ir = QueryIR(
        operation="SELECT",
        source=TableSource(table="users"),
        fields=[FieldExpr(field="*")],
        filters=ConditionExpr(field="id", op="IN", value=subquery)
    )

    builder = PostgreSQLBuilder()
    result = builder.build(query_ir)

    assert 'WHERE "id" IN (' in result.sql
    assert 'SELECT "user_id"' in result.sql
    assert 'FROM "orders"' in result.sql

def test_subquery_in_from():
    """Test subquery in FROM clause."""
    subquery = QueryIR(
        operation="SELECT",
        source=TableSource(table="orders"),
        fields=[FieldExpr(field="user_id")]
    )

    query_ir = QueryIR(
        operation="SELECT",
        source=TableSource(subquery=subquery, alias="subq"),
        fields=[FieldExpr(field="user_id", table="subq")]
    )

    builder = PostgreSQLBuilder()
    result = builder.build(query_ir)

    assert 'FROM (' in result.sql
    assert ') AS "subq"' in result.sql

def test_nested_subqueries():
    """Test multiple levels of nesting."""
    # Subquery level 2
    inner_subquery = QueryIR(
        operation="SELECT",
        source=TableSource(table="order_items"),
        fields=[FieldExpr(field="order_id")]
    )

    # Subquery level 1
    outer_subquery = QueryIR(
        operation="SELECT",
        source=TableSource(table="orders"),
        fields=[FieldExpr(field="user_id")],
        filters=ConditionExpr(field="id", op="IN", value=inner_subquery)
    )

    # Main query
    query_ir = QueryIR(
        operation="SELECT",
        source=TableSource(table="users"),
        fields=[FieldExpr(field="*")],
        filters=ConditionExpr(field="id", op="IN", value=outer_subquery)
    )

    builder = PostgreSQLBuilder()
    result = builder.build(query_ir)

    # Should have 3 SELECT statements
    assert result.sql.count("SELECT") == 3
```

## Implementation Checklist

- [ ] Update IR models to support subqueries
- [ ] Add `_build_query()` method for recursive building
- [ ] Update `_build_from()` to handle subqueries
- [ ] Update `_build_select()` for scalar subqueries
- [ ] Update `_build_condition()` for subqueries in WHERE
- [ ] Add EXISTS operator support
- [ ] Test parameter handling across nesting levels
- [ ] Add comprehensive subquery tests
- [ ] Update documentation

## Security Considerations

Subqueries don't add new security risks if:
1. All values are still parameterized
2. Table/field names are still quoted
3. Subquery IR is validated same as main query

The recursive nature means the same security measures apply at all levels.
