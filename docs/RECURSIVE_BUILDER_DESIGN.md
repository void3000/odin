# Recursive Builder Design (Compiler-Style)

## Problem with Current Approach

Current approach is **imperative and flat**:

```python
def build(self, query_ir: QueryIR) -> PostgreSQLQueryResult:
    # Build each component separately
    select_clause = self._build_select(query_ir.fields)
    from_clause = self._build_from(query_ir.source)
    join_clause = self._build_joins(query_ir.joins)
    where_clause = self._build_where(query_ir.filters)
    order_clause = self._build_order_by(query_ir.order_by)
    limit_clause = self._build_limit(query_ir.limit)

    # Manually combine
    parts = [select_clause, from_clause]
    if join_clause:
        parts.append(join_clause)
    # ... etc
```

**Issues:**
- Doesn't naturally handle nested queries
- Each method returns strings, not structured data
- Hard to compose complex structures
- Not extensible for subqueries

## Compiler-Style Recursive Approach

Like a compiler's AST walker, each IR node knows how to build itself:

```python
def build(self, query_ir: QueryIR) -> PostgreSQLQueryResult:
    """Entry point - delegates to recursive visitor."""
    # Reset state
    self.params = []
    self.param_counter = 0

    # Visit the IR tree recursively
    sql = self.visit_query(query_ir)

    return PostgreSQLQueryResult(sql=sql, params=self.params)

def visit_query(self, node: QueryIR) -> str:
    """Visit a QueryIR node - recursive entry point."""
    parts = []

    # Each component visits its children recursively
    parts.append(self.visit_select(node.fields))
    parts.append(self.visit_from(node.source))

    if node.joins:
        parts.append(self.visit_joins(node.joins))

    if node.filters:
        parts.append(self.visit_where(node.filters))

    if node.order_by:
        parts.append(self.visit_order_by(node.order_by))

    if node.limit:
        parts.append(self.visit_limit(node.limit))

    return "\n".join(p for p in parts if p)
```

## Recursive Visitor Methods

### Visit SELECT

```python
def visit_select(self, fields: List[FieldExpr]) -> str:
    """Visit SELECT clause - each field visits itself."""
    field_parts = [self.visit_field(field) for field in fields]
    return "SELECT " + ", ".join(field_parts)

def visit_field(self, field: FieldExpr) -> str:
    """Visit a single field - handles recursion for subqueries."""
    # Subquery in SELECT (scalar subquery)
    if field.subquery:
        subquery_sql = self.visit_query(field.subquery)  # RECURSIVE!
        result = f"(\n{self._indent(subquery_sql)}\n)"
        if field.alias:
            result += f" AS {self._quote_identifier(field.alias)}"
        return result

    # Wildcard
    if field.field == "*":
        if field.table:
            return f"{self._quote_identifier(field.table)}.*"
        return "*"

    # Regular field
    if field.table:
        result = self._quote_qualified(field.table, field.field)
    else:
        result = self._quote_identifier(field.field)

    if field.alias:
        result += f" AS {self._quote_identifier(field.alias)}"

    return result
```

### Visit FROM

```python
def visit_from(self, source: TableSource) -> str:
    """Visit FROM clause - handles table or subquery."""
    table_ref = self.visit_table_source(source)
    return f"FROM {table_ref}"

def visit_table_source(self, source: TableSource) -> str:
    """Visit a table source - handles recursion for derived tables."""
    # Subquery (derived table)
    if source.subquery:
        subquery_sql = self.visit_query(source.subquery)  # RECURSIVE!
        alias = self._quote_identifier(source.alias)
        return f"(\n{self._indent(subquery_sql)}\n) AS {alias}"

    # Simple table
    table = self._quote_identifier(source.table)
    if source.alias:
        table += f" AS {self._quote_identifier(source.alias)}"
    return table
```

### Visit WHERE (Most Complex - Deeply Recursive)

```python
def visit_where(self, filters: FilterExpr) -> str:
    """Visit WHERE clause."""
    condition = self.visit_filter(filters)
    return f"WHERE {condition}"

def visit_filter(self, expr: FilterExpr) -> str:
    """Visit a filter expression - recursive for LogicalExpr."""
    if isinstance(expr, ConditionExpr):
        return self.visit_condition(expr)
    elif isinstance(expr, LogicalExpr):
        return self.visit_logical(expr)
    else:
        raise QueryBuildError(f"Unknown filter type: {type(expr)}")

def visit_condition(self, cond: ConditionExpr) -> str:
    """Visit a condition - handles subqueries in values."""
    # Build left side
    left = self.visit_field_reference(cond.field, cond.table)

    # Build right side - RECURSIVE for subqueries!
    right = self.visit_value(cond.value, cond.op)

    # Special case for EXISTS
    if cond.op == "EXISTS":
        return f"EXISTS {right}"

    return f"{left} {cond.op} {right}"

def visit_field_reference(self, field: str, table: str | None) -> str:
    """Visit a field reference."""
    if table:
        return self._quote_qualified(table, field)
    return self._quote_identifier(field)

def visit_value(self, value: Any, operator: str) -> str:
    """Visit a value - handles scalars, lists, field refs, and subqueries."""
    # Subquery value - RECURSIVE!
    if isinstance(value, QueryIR):
        subquery_sql = self.visit_query(value)
        return f"(\n{self._indent(subquery_sql)}\n)"

    # Field reference
    if isinstance(value, dict) and "field" in value:
        return self.visit_field_reference(
            value["field"],
            value.get("table")
        )

    # List (for IN operator)
    if operator == "IN" and isinstance(value, list):
        placeholders = [self._add_param(v) for v in value]
        return f"({', '.join(placeholders)})"

    # Scalar value
    return self._add_param(value)

def visit_logical(self, expr: LogicalExpr) -> str:
    """Visit logical expression (AND/OR) - recursive."""
    # Recursively visit each sub-condition
    sub_conditions = [self.visit_filter(cond) for cond in expr.conditions]

    # Join with operator
    joined = f" {expr.logic} ".join(f"({c})" for c in sub_conditions)

    return f"({joined})"
```

### Visit JOINs

```python
def visit_joins(self, joins: List[JoinExpr]) -> str:
    """Visit JOIN clauses."""
    join_parts = [self.visit_join(join) for join in joins]
    return "\n".join(join_parts)

def visit_join(self, join: JoinExpr) -> str:
    """Visit a single JOIN."""
    # Table to join (could be subquery!)
    table_ref = self.visit_table_source(
        TableSource(table=join.table) if isinstance(join.table, str)
        else join.table  # If table can be TableSource with subquery
    )

    # Join condition
    condition = self.visit_condition(join.on)

    return f"{join.type} JOIN {table_ref} ON {condition}"
```

### Visit ORDER BY

```python
def visit_order_by(self, order_by: List[OrderExpr]) -> str:
    """Visit ORDER BY clause."""
    order_parts = [self.visit_order_expr(expr) for expr in order_by]
    return "ORDER BY " + ", ".join(order_parts)

def visit_order_expr(self, expr: OrderExpr) -> str:
    """Visit a single ORDER BY expression."""
    field = self.visit_field_reference(expr.field, expr.table)
    return f"{field} {expr.direction}"
```

### Visit LIMIT

```python
def visit_limit(self, limit: int) -> str:
    """Visit LIMIT clause."""
    return f"LIMIT {limit}"
```

## Complete Recursive Builder

```python
class PostgreSQLBuilder(QueryBuilder):
    """PostgreSQL query builder using recursive visitor pattern."""

    def __init__(self):
        self.params: List[Any] = []
        self.param_counter: int = 0
        self.indent_level: int = 0

    def build(self, query_ir: QueryIR) -> PostgreSQLQueryResult:
        """Build query - entry point."""
        # Initialize state
        self.params = []
        self.param_counter = 0
        self.indent_level = 0

        # Visit IR tree recursively
        sql = self.visit_query(query_ir)

        return PostgreSQLQueryResult(sql=sql, params=self.params)

    # ========== Visitor Methods ==========

    def visit_query(self, node: QueryIR) -> str:
        """Visit QueryIR node."""
        parts = []
        parts.append(self.visit_select(node.fields))
        parts.append(self.visit_from(node.source))

        if node.joins:
            parts.append(self.visit_joins(node.joins))
        if node.filters:
            parts.append(self.visit_where(node.filters))
        if node.order_by:
            parts.append(self.visit_order_by(node.order_by))
        if node.limit:
            parts.append(self.visit_limit(node.limit))

        return "\n".join(p for p in parts if p)

    def visit_select(self, fields: List[FieldExpr]) -> str:
        """Visit SELECT clause."""
        field_parts = [self.visit_field(field) for field in fields]
        return "SELECT " + ", ".join(field_parts)

    def visit_field(self, field: FieldExpr) -> str:
        """Visit field expression."""
        if field.subquery:
            subquery_sql = self.visit_query(field.subquery)
            result = f"(\n{self._indent(subquery_sql)}\n)"
            if field.alias:
                result += f" AS {self._quote_identifier(field.alias)}"
            return result

        if field.field == "*":
            if field.table:
                return f"{self._quote_identifier(field.table)}.*"
            return "*"

        if field.table:
            result = self._quote_qualified(field.table, field.field)
        else:
            result = self._quote_identifier(field.field)

        if field.alias:
            result += f" AS {self._quote_identifier(field.alias)}"

        return result

    def visit_from(self, source: TableSource) -> str:
        """Visit FROM clause."""
        table_ref = self.visit_table_source(source)
        return f"FROM {table_ref}"

    def visit_table_source(self, source: TableSource) -> str:
        """Visit table source."""
        if source.subquery:
            subquery_sql = self.visit_query(source.subquery)
            alias = self._quote_identifier(source.alias)
            return f"(\n{self._indent(subquery_sql)}\n) AS {alias}"

        table = self._quote_identifier(source.table)
        if source.alias:
            table += f" AS {self._quote_identifier(source.alias)}"
        return table

    def visit_joins(self, joins: List[JoinExpr]) -> str:
        """Visit JOINs."""
        return "\n".join(self.visit_join(j) for j in joins)

    def visit_join(self, join: JoinExpr) -> str:
        """Visit JOIN."""
        table = self._quote_identifier(join.table)
        condition = self.visit_condition(join.on)
        return f"{join.type} JOIN {table} ON {condition}"

    def visit_where(self, filters: FilterExpr) -> str:
        """Visit WHERE clause."""
        condition = self.visit_filter(filters)
        return f"WHERE {condition}"

    def visit_filter(self, expr: FilterExpr) -> str:
        """Visit filter expression (recursive)."""
        if isinstance(expr, ConditionExpr):
            return self.visit_condition(expr)
        elif isinstance(expr, LogicalExpr):
            return self.visit_logical(expr)
        raise QueryBuildError(f"Unknown filter type: {type(expr)}")

    def visit_condition(self, cond: ConditionExpr) -> str:
        """Visit condition."""
        left = self.visit_field_reference(cond.field, cond.table)
        right = self.visit_value(cond.value, cond.op)

        if cond.op == "EXISTS":
            return f"EXISTS {right}"

        return f"{left} {cond.op} {right}"

    def visit_logical(self, expr: LogicalExpr) -> str:
        """Visit logical expression (recursive)."""
        sub_conditions = [self.visit_filter(c) for c in expr.conditions]
        joined = f" {expr.logic} ".join(f"({c})" for c in sub_conditions)
        return f"({joined})"

    def visit_field_reference(self, field: str, table: str | None) -> str:
        """Visit field reference."""
        if table:
            return self._quote_qualified(table, field)
        return self._quote_identifier(field)

    def visit_value(self, value: Any, operator: str) -> str:
        """Visit value (handles subqueries)."""
        # Subquery
        if isinstance(value, QueryIR):
            subquery_sql = self.visit_query(value)
            return f"(\n{self._indent(subquery_sql)}\n)"

        # Field reference
        if isinstance(value, dict) and "field" in value:
            return self.visit_field_reference(value["field"], value.get("table"))

        # List (IN operator)
        if operator == "IN" and isinstance(value, list):
            placeholders = [self._add_param(v) for v in value]
            return f"({', '.join(placeholders)})"

        # Scalar
        return self._add_param(value)

    def visit_order_by(self, order_by: List[OrderExpr]) -> str:
        """Visit ORDER BY clause."""
        order_parts = [self.visit_order_expr(e) for e in order_by]
        return "ORDER BY " + ", ".join(order_parts)

    def visit_order_expr(self, expr: OrderExpr) -> str:
        """Visit ORDER BY expression."""
        field = self.visit_field_reference(expr.field, expr.table)
        return f"{field} {expr.direction}"

    def visit_limit(self, limit: int) -> str:
        """Visit LIMIT clause."""
        return f"LIMIT {limit}"

    # ========== Helpers ==========

    def _indent(self, sql: str) -> str:
        """Indent SQL for nested queries."""
        lines = sql.split("\n")
        return "\n".join("  " + line for line in lines)

    def _quote_identifier(self, name: str) -> str:
        """Quote identifier."""
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def _quote_qualified(self, table: str, column: str) -> str:
        """Quote qualified identifier."""
        return f'{self._quote_identifier(table)}.{self._quote_identifier(column)}'

    def _add_param(self, value: Any) -> str:
        """Add parameter and return placeholder."""
        self.params.append(value)
        self.param_counter += 1
        return f"${self.param_counter}"
```

## Benefits of Recursive Approach

### 1. Natural Recursion

Each `visit_*` method can call `visit_query()` for subqueries:

```python
def visit_field(self, field: FieldExpr) -> str:
    if field.subquery:
        return self.visit_query(field.subquery)  # Natural recursion!
    # ... handle regular field
```

### 2. Composability

Methods compose naturally:

```python
def visit_select(self, fields: List[FieldExpr]) -> str:
    # Each field knows how to visit itself (including subqueries)
    field_parts = [self.visit_field(f) for f in fields]
    return "SELECT " + ", ".join(field_parts)
```

### 3. Extensibility

Adding new node types is easy - just add a new `visit_*` method:

```python
def visit_union(self, union: UnionExpr) -> str:
    left = self.visit_query(union.left)
    right = self.visit_query(union.right)
    return f"{left}\nUNION\n{right}"
```

### 4. Separation of Concerns

Each method handles ONE type of node:
- `visit_query()` → QueryIR
- `visit_field()` → FieldExpr
- `visit_condition()` → ConditionExpr
- `visit_logical()` → LogicalExpr

### 5. Testing

Each visitor can be tested independently:

```python
def test_visit_condition():
    builder = PostgreSQLBuilder()
    builder.params = []
    builder.param_counter = 0

    cond = ConditionExpr(field="name", op="=", value="Alice")
    result = builder.visit_condition(cond)

    assert result == '"name" = $1'
    assert builder.params == ["Alice"]
```

## Example: Nested Query

**IR:**
```python
QueryIR(
    operation="SELECT",
    source=TableSource(table="users"),
    fields=[FieldExpr(field="*")],
    filters=ConditionExpr(
        field="id",
        op="IN",
        value=QueryIR(  # Subquery!
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[FieldExpr(field="user_id")]
        )
    )
)
```

**Execution Flow:**
```
visit_query(main_query)
  ├─ visit_select([*])
  │   └─ visit_field(*) → "SELECT *"
  ├─ visit_from(users) → "FROM \"users\""
  └─ visit_where(filters)
      └─ visit_filter(condition)
          └─ visit_condition(id IN ...)
              ├─ visit_field_reference(id) → "\"id\""
              └─ visit_value(subquery, IN)
                  └─ visit_query(subquery)  ← RECURSIVE!
                      ├─ visit_select([user_id])
                      └─ visit_from(orders)
```

**Output:**
```sql
SELECT *
FROM "users"
WHERE "id" IN (
  SELECT "user_id"
  FROM "orders"
)
```

## Comparison

| Current Approach | Recursive Visitor |
|-----------------|-------------------|
| `_build_select()` | `visit_select()` |
| `_build_from()` | `visit_from()` |
| `_build_where()` | `visit_where()` |
| Returns strings | Returns strings |
| Manual composition | Automatic recursion |
| Hard to extend | Easy to extend |
| Flat structure | Tree walking |

## Migration Path

You can migrate incrementally:

1. Rename `_build_*` to `visit_*`
2. Change `build()` to call `visit_query()`
3. Update each `visit_*` method to call `visit_query()` for subqueries
4. Add tests for recursive cases

The external API (`build()`) stays the same!

## Summary

**Key Insight:** Each IR node type has a corresponding `visit_*` method that:
1. Knows how to build SQL for that node
2. Recursively visits child nodes (including subqueries)
3. Returns a string (SQL fragment)
4. Accumulates parameters in shared state

This is exactly how compilers work with ASTs!
