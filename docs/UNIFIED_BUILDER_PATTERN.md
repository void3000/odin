# Unified Query Builder Pattern

## Philosophy

**All databases use the same pattern for consistency.**

Even though PostgreSQL and MongoDB have very different query languages, we treat them the same architecturally. This provides:

- **Consistency**: Same interface, same testing strategy, same extension points
- **Predictability**: Adding a new database follows the same pattern
- **Simplicity**: One pattern to learn and maintain
- **Flexibility**: Each database can be completely different internally

## The Pattern: Strategy + Abstract Factory

Every database is a concrete strategy implementing the same interface.

```
┌─────────────────────────────────────┐
│      QueryBuilderFactory            │
│      (Abstract Factory)             │
└──────────────┬──────────────────────┘
               │
               │ creates
               ▼
┌─────────────────────────────────────┐
│      QueryBuilder (Abstract)        │
│  ┌───────────────────────────────┐  │
│  │  + build(ir) -> QueryResult   │  │
│  │  + get_capabilities()         │  │
│  │  + validate_ir(ir)            │  │
│  └───────────────────────────────┘  │
└──────────────┬──────────────────────┘
               │
               │ implemented by
               │
    ┏━━━━━━━━━━┻━━━━━━━━━━━━━━━━━━━━━━━━┓
    ┃                                    ┃
    ▼                                    ▼
┌──────────────┐                  ┌──────────────┐
│ PostgreSQL   │                  │   MongoDB    │
│   Builder    │                  │   Builder    │
└──────────────┘                  └──────────────┘
    ▼                                    ▼
┌──────────────┐                  ┌──────────────┐
│   MySQL      │                  │  DynamoDB    │
│   Builder    │                  │   Builder    │
└──────────────┘                  └──────────────┘
```

**All builders:**
1. Implement the same `QueryBuilder` interface
2. Return their own specific `QueryResult` type
3. Handle their own identifier escaping
4. Manage their own parameter formatting
5. Provide capability discovery

## Core Interfaces

### 1. QueryResult (Protocol)

All query results must be executable:

```python
from typing import Protocol, Any

class QueryResult(Protocol):
    """Protocol for query results from any database."""

    def execute(self, connection: Any) -> Any:
        """Execute the query against a database connection.

        Args:
            connection: Database-specific connection object

        Returns:
            Database-specific result
        """
        ...

    def to_dict(self) -> dict:
        """Get query as dictionary for inspection/logging."""
        ...

    def __str__(self) -> str:
        """Human-readable representation."""
        ...
```

### 2. QueryBuilder (Abstract Base)

All builders implement this interface:

```python
from abc import ABC, abstractmethod
from typing import Set
from dataclasses import dataclass

class QueryCapabilities:
    """Describes what features a database supports."""

    supports_joins: bool = True
    supports_complex_filters: bool = True
    supports_aggregates: bool = True
    supports_subqueries: bool = True
    max_join_depth: int | None = None
    supported_operators: Set[str] = None

    def __post_init__(self):
        if self.supported_operators is None:
            self.supported_operators = {"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE"}

class QueryBuilder(ABC):
    """Abstract base for all query builders."""

    @abstractmethod
    def build(self, query_ir: QueryIR) -> QueryResult:
        """Build a query from IR.

        Args:
            query_ir: Validated intermediate representation

        Returns:
            Database-specific query result

        Raises:
            UnsupportedFeatureError: If IR uses unsupported features
            QueryBuildError: If query cannot be built
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> QueryCapabilities:
        """Get capabilities of this database."""
        pass

    def validate_ir(self, query_ir: QueryIR) -> None:
        """Validate that IR is supported by this builder.

        Args:
            query_ir: IR to validate

        Raises:
            UnsupportedFeatureError: If IR uses unsupported features
        """
        capabilities = self.get_capabilities()

        # Check joins
        if query_ir.joins and not capabilities.supports_joins:
            raise UnsupportedFeatureError("This database does not support JOINs")

        # Check operators
        if query_ir.filters:
            self._validate_operators(query_ir.filters, capabilities.supported_operators)

    def _validate_operators(self, filters: FilterExpr, supported: Set[str]) -> None:
        """Recursively validate operators in filters."""
        if isinstance(filters, ConditionExpr):
            if filters.op not in supported:
                raise UnsupportedFeatureError(
                    f"Operator '{filters.op}' not supported by this database"
                )
        elif isinstance(filters, LogicalExpr):
            for condition in filters.conditions:
                self._validate_operators(condition, supported)
```

### 3. QueryBuilderFactory (Abstract Factory)

```python
class QueryBuilderFactory:
    """Factory for creating query builders."""

    _builders: dict[str, type[QueryBuilder]] = {}

    @classmethod
    def register(cls, database_type: str, builder_class: type[QueryBuilder]) -> None:
        """Register a builder for a database type."""
        cls._builders[database_type.lower()] = builder_class

    @classmethod
    def create(cls, database_type: str) -> QueryBuilder:
        """Create a builder for the specified database type.

        Args:
            database_type: Type of database (e.g., 'postgresql', 'mongodb')

        Returns:
            Appropriate query builder

        Raises:
            ValueError: If database type is not registered
        """
        builder_class = cls._builders.get(database_type.lower())
        if not builder_class:
            available = ", ".join(cls._builders.keys())
            raise ValueError(
                f"Unknown database type: {database_type}. "
                f"Available: {available}"
            )
        return builder_class()

    @classmethod
    def list_supported(cls) -> list[str]:
        """List all supported database types."""
        return list(cls._builders.keys())
```

## Concrete Implementations

### PostgreSQL Builder

```python
from dataclasses import dataclass
from typing import Any, List

@dataclass
class PostgreSQLQueryResult:
    """PostgreSQL query result."""

    sql: str
    params: List[Any]

    def execute(self, connection: Any):
        """Execute with psycopg2 or asyncpg connection."""
        cursor = connection.cursor()
        cursor.execute(self.sql, self.params)
        return cursor.fetchall()

    def to_dict(self) -> dict:
        return {
            "type": "postgresql",
            "sql": self.sql,
            "params": self.params
        }

    def __str__(self) -> str:
        return f"PostgreSQL Query:\n{self.sql}\nParams: {self.params}"


class PostgreSQLBuilder(QueryBuilder):
    """PostgreSQL query builder."""

    def __init__(self):
        self.params: List[Any] = []
        self.param_counter = 0

    def build(self, query_ir: QueryIR) -> PostgreSQLQueryResult:
        """Build PostgreSQL query from IR."""
        # Validate first
        self.validate_ir(query_ir)

        # Reset state
        self.params = []
        self.param_counter = 0

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

        return PostgreSQLQueryResult(sql=sql, params=self.params)

    def get_capabilities(self) -> QueryCapabilities:
        """PostgreSQL supports all features."""
        return QueryCapabilities(
            supports_joins=True,
            supports_complex_filters=True,
            supports_aggregates=True,
            supports_subqueries=True,
            supported_operators={"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE", "ILIKE"}
        )

    # Component builders
    def _quote_identifier(self, name: str) -> str:
        """Quote identifier with double quotes."""
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def _add_param(self, value: Any) -> str:
        """Add parameter and return placeholder ($1, $2, etc.)."""
        self.params.append(value)
        self.param_counter += 1
        return f"${self.param_counter}"

    def _build_select(self, fields: List[FieldExpr]) -> str:
        """Build SELECT clause."""
        field_parts = []
        for field_expr in fields:
            if field_expr.field == "*":
                if field_expr.table:
                    field_parts.append(f"{self._quote_identifier(field_expr.table)}.*")
                else:
                    field_parts.append("*")
                continue

            if field_expr.table:
                field_str = f"{self._quote_identifier(field_expr.table)}.{self._quote_identifier(field_expr.field)}"
            else:
                field_str = self._quote_identifier(field_expr.field)

            if field_expr.alias:
                field_str += f" AS {self._quote_identifier(field_expr.alias)}"

            field_parts.append(field_str)

        return "SELECT " + ", ".join(field_parts)

    def _build_from(self, source: TableSource) -> str:
        """Build FROM clause."""
        return f"FROM {self._quote_identifier(source.table)}"

    def _build_joins(self, joins: List[JoinExpr] | None) -> str:
        """Build JOIN clauses."""
        if not joins:
            return ""

        join_parts = []
        for join_expr in joins:
            table = self._quote_identifier(join_expr.table)
            condition = self._build_condition(join_expr.on)
            join_parts.append(f"{join_expr.type} JOIN {table} ON {condition}")

        return "\n".join(join_parts)

    def _build_where(self, filters: FilterExpr | None) -> str:
        """Build WHERE clause."""
        if not filters:
            return ""
        return f"WHERE {self._build_filter_expr(filters)}"

    def _build_filter_expr(self, expr: FilterExpr) -> str:
        """Build filter expression (recursive)."""
        if isinstance(expr, ConditionExpr):
            return self._build_condition(expr)
        elif isinstance(expr, LogicalExpr):
            sub_conditions = [self._build_filter_expr(c) for c in expr.conditions]
            joined = f" {expr.logic} ".join(f"({c})" for c in sub_conditions)
            return f"({joined})"

    def _build_condition(self, cond: ConditionExpr) -> str:
        """Build single condition."""
        # Left side
        if cond.table:
            left = f"{self._quote_identifier(cond.table)}.{self._quote_identifier(cond.field)}"
        else:
            left = self._quote_identifier(cond.field)

        # Right side
        if isinstance(cond.value, dict):
            # Field reference
            if "table" in cond.value:
                right = f"{self._quote_identifier(cond.value['table'])}.{self._quote_identifier(cond.value['field'])}"
            else:
                right = self._quote_identifier(cond.value["field"])
        elif cond.op == "IN":
            placeholders = [self._add_param(v) for v in cond.value]
            right = f"({', '.join(placeholders)})"
        else:
            right = self._add_param(cond.value)

        return f"{left} {cond.op} {right}"

    def _build_order_by(self, order_by: List[OrderExpr] | None) -> str:
        """Build ORDER BY clause."""
        if not order_by:
            return ""

        order_parts = []
        for order_expr in order_by:
            if order_expr.table:
                field = f"{self._quote_identifier(order_expr.table)}.{self._quote_identifier(order_expr.field)}"
            else:
                field = self._quote_identifier(order_expr.field)
            order_parts.append(f"{field} {order_expr.direction}")

        return "ORDER BY " + ", ".join(order_parts)

    def _build_limit(self, limit: int | None) -> str:
        """Build LIMIT clause."""
        if not limit:
            return ""
        return f"LIMIT {limit}"


# Register with factory
QueryBuilderFactory.register("postgresql", PostgreSQLBuilder)
```

### MySQL Builder

```python
@dataclass
class MySQLQueryResult:
    """MySQL query result."""

    sql: str
    params: List[Any]

    def execute(self, connection: Any):
        """Execute with mysql-connector or pymysql connection."""
        cursor = connection.cursor()
        cursor.execute(self.sql, self.params)
        return cursor.fetchall()

    def to_dict(self) -> dict:
        return {
            "type": "mysql",
            "sql": self.sql,
            "params": self.params
        }

    def __str__(self) -> str:
        return f"MySQL Query:\n{self.sql}\nParams: {self.params}"


class MySQLBuilder(QueryBuilder):
    """MySQL query builder."""

    def __init__(self):
        self.params: List[Any] = []

    def build(self, query_ir: QueryIR) -> MySQLQueryResult:
        """Build MySQL query from IR."""
        self.validate_ir(query_ir)
        self.params = []

        # Build components (same structure as PostgreSQL)
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

        sql = "\n".join(parts)

        return MySQLQueryResult(sql=sql, params=self.params)

    def get_capabilities(self) -> QueryCapabilities:
        """MySQL supports all standard features."""
        return QueryCapabilities(
            supports_joins=True,
            supports_complex_filters=True,
            supports_aggregates=True,
            supports_subqueries=True,
            supported_operators={"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE"}
        )

    def _quote_identifier(self, name: str) -> str:
        """Quote identifier with backticks."""
        escaped = name.replace("`", "``")
        return f"`{escaped}`"

    def _add_param(self, value: Any) -> str:
        """Add parameter and return placeholder (?)."""
        self.params.append(value)
        return "?"

    # Component builders are identical to PostgreSQL
    # (just different quoting and param style)
    def _build_select(self, fields: List[FieldExpr]) -> str:
        # ... same as PostgreSQL
        pass

    # ... other methods same as PostgreSQL


# Register with factory
QueryBuilderFactory.register("mysql", MySQLBuilder)
```

### MongoDB Builder

```python
@dataclass
class MongoDBQueryResult:
    """MongoDB query result."""

    collection: str
    filter: dict
    projection: dict | None
    sort: dict | None
    limit: int | None

    def execute(self, connection: Any):
        """Execute with pymongo connection."""
        db = connection
        cursor = db[self.collection].find(
            self.filter,
            projection=self.projection,
            sort=list(self.sort.items()) if self.sort else None,
            limit=self.limit or 0
        )
        return list(cursor)

    def to_dict(self) -> dict:
        return {
            "type": "mongodb",
            "collection": self.collection,
            "filter": self.filter,
            "projection": self.projection,
            "sort": self.sort,
            "limit": self.limit
        }

    def __str__(self) -> str:
        parts = [f"MongoDB Query on collection: {self.collection}"]
        if self.filter:
            parts.append(f"Filter: {self.filter}")
        if self.projection:
            parts.append(f"Projection: {self.projection}")
        if self.sort:
            parts.append(f"Sort: {self.sort}")
        if self.limit:
            parts.append(f"Limit: {self.limit}")
        return "\n".join(parts)


class MongoDBBuilder(QueryBuilder):
    """MongoDB query builder."""

    def build(self, query_ir: QueryIR) -> MongoDBQueryResult:
        """Build MongoDB query from IR."""
        self.validate_ir(query_ir)

        return MongoDBQueryResult(
            collection=query_ir.source.table,
            filter=self._build_filter(query_ir.filters),
            projection=self._build_projection(query_ir.fields),
            sort=self._build_sort(query_ir.order_by),
            limit=query_ir.limit
        )

    def get_capabilities(self) -> QueryCapabilities:
        """MongoDB has limited JOIN support."""
        return QueryCapabilities(
            supports_joins=False,  # Would need $lookup aggregation pipeline
            supports_complex_filters=True,
            supports_aggregates=True,
            supports_subqueries=False,
            supported_operators={"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE"}
        )

    def _build_filter(self, filters: FilterExpr | None) -> dict:
        """Build MongoDB filter document."""
        if not filters:
            return {}

        if isinstance(filters, ConditionExpr):
            return self._build_condition(filters)
        elif isinstance(filters, LogicalExpr):
            return self._build_logical(filters)

    def _build_condition(self, cond: ConditionExpr) -> dict:
        """Build single MongoDB condition."""
        field = cond.field
        op = cond.op
        value = cond.value

        # Operator mapping
        if op == "=":
            return {field: value}
        elif op == "!=":
            return {field: {"$ne": value}}
        elif op == ">":
            return {field: {"$gt": value}}
        elif op == ">=":
            return {field: {"$gte": value}}
        elif op == "<":
            return {field: {"$lt": value}}
        elif op == "<=":
            return {field: {"$lte": value}}
        elif op == "IN":
            return {field: {"$in": value}}
        elif op == "LIKE":
            # Convert SQL LIKE to regex
            pattern = value.replace("%", ".*").replace("_", ".")
            return {field: {"$regex": f"^{pattern}$", "$options": "i"}}
        else:
            raise ValueError(f"Unsupported operator: {op}")

    def _build_logical(self, logical: LogicalExpr) -> dict:
        """Build MongoDB logical expression."""
        mongo_op = "$and" if logical.logic == "AND" else "$or"
        conditions = [self._build_filter(c) for c in logical.conditions]
        return {mongo_op: conditions}

    def _build_projection(self, fields: List[FieldExpr]) -> dict | None:
        """Build MongoDB projection."""
        if any(f.field == "*" for f in fields):
            return None

        projection = {}
        for field in fields:
            # MongoDB uses field name or alias
            key = field.alias if field.alias else field.field
            projection[field.field] = 1

        return projection

    def _build_sort(self, order_by: List[OrderExpr] | None) -> dict | None:
        """Build MongoDB sort."""
        if not order_by:
            return None

        sort = {}
        for order_expr in order_by:
            direction = 1 if order_expr.direction == "ASC" else -1
            sort[order_expr.field] = direction

        return sort


# Register with factory
QueryBuilderFactory.register("mongodb", MongoDBBuilder)
```

### DynamoDB Builder

```python
@dataclass
class DynamoDBQueryResult:
    """DynamoDB query result."""

    table_name: str
    key_condition_expression: str | None
    filter_expression: str | None
    expression_attribute_names: dict
    expression_attribute_values: dict
    projection_expression: str | None
    limit: int | None

    def execute(self, connection: Any):
        """Execute with boto3 DynamoDB resource."""
        table = connection.Table(self.table_name)

        kwargs = {}
        if self.key_condition_expression:
            kwargs["KeyConditionExpression"] = self.key_condition_expression
        if self.filter_expression:
            kwargs["FilterExpression"] = self.filter_expression
        if self.expression_attribute_names:
            kwargs["ExpressionAttributeNames"] = self.expression_attribute_names
        if self.expression_attribute_values:
            kwargs["ExpressionAttributeValues"] = self.expression_attribute_values
        if self.projection_expression:
            kwargs["ProjectionExpression"] = self.projection_expression
        if self.limit:
            kwargs["Limit"] = self.limit

        response = table.query(**kwargs)
        return response["Items"]

    def to_dict(self) -> dict:
        return {
            "type": "dynamodb",
            "table_name": self.table_name,
            "key_condition_expression": self.key_condition_expression,
            "filter_expression": self.filter_expression,
            "expression_attribute_names": self.expression_attribute_names,
            "expression_attribute_values": self.expression_attribute_values,
            "projection_expression": self.projection_expression,
            "limit": self.limit
        }

    def __str__(self) -> str:
        return f"DynamoDB Query:\nTable: {self.table_name}\n" + \
               f"KeyCondition: {self.key_condition_expression}\n" + \
               f"Filter: {self.filter_expression}"


class DynamoDBBuilder(QueryBuilder):
    """DynamoDB query builder."""

    def __init__(self, partition_key: str = "id"):
        """Initialize with partition key name."""
        self.partition_key = partition_key
        self.attr_name_counter = 0
        self.attr_value_counter = 0
        self.attr_names: dict = {}
        self.attr_values: dict = {}

    def build(self, query_ir: QueryIR) -> DynamoDBQueryResult:
        """Build DynamoDB query from IR."""
        self.validate_ir(query_ir)

        # Reset state
        self.attr_name_counter = 0
        self.attr_value_counter = 0
        self.attr_names = {}
        self.attr_values = {}

        # Build filter expressions
        key_cond, filter_cond = self._split_conditions(query_ir.filters)

        return DynamoDBQueryResult(
            table_name=query_ir.source.table,
            key_condition_expression=key_cond,
            filter_expression=filter_cond,
            expression_attribute_names=self.attr_names,
            expression_attribute_values=self.attr_values,
            projection_expression=self._build_projection(query_ir.fields),
            limit=query_ir.limit
        )

    def get_capabilities(self) -> QueryCapabilities:
        """DynamoDB has very limited query capabilities."""
        return QueryCapabilities(
            supports_joins=False,
            supports_complex_filters=False,  # Limited to key and filter expressions
            supports_aggregates=False,
            supports_subqueries=False,
            supported_operators={"=", "!=", ">", ">=", "<", "<=", "IN"}  # No LIKE
        )

    def _split_conditions(self, filters: FilterExpr | None) -> tuple[str | None, str | None]:
        """Split conditions into key condition and filter expression.

        DynamoDB requires partition key in KeyConditionExpression.
        Other filters go in FilterExpression.
        """
        if not filters:
            return None, None

        # For now, simple implementation
        # More complex: extract partition key condition
        key_condition = None
        filter_expression = self._build_filter_expr(filters)

        return key_condition, filter_expression

    def _add_attr_name(self, name: str) -> str:
        """Add attribute name placeholder."""
        placeholder = f"#n{self.attr_name_counter}"
        self.attr_names[placeholder] = name
        self.attr_name_counter += 1
        return placeholder

    def _add_attr_value(self, value: Any) -> str:
        """Add attribute value placeholder."""
        placeholder = f":v{self.attr_value_counter}"
        self.attr_values[placeholder] = value
        self.attr_value_counter += 1
        return placeholder

    def _build_filter_expr(self, filters: FilterExpr) -> str:
        """Build filter expression."""
        if isinstance(filters, ConditionExpr):
            return self._build_condition(filters)
        elif isinstance(filters, LogicalExpr):
            sub_conditions = [self._build_filter_expr(c) for c in filters.conditions]
            op = " AND " if filters.logic == "AND" else " OR "
            return f"({op.join(sub_conditions)})"

    def _build_condition(self, cond: ConditionExpr) -> str:
        """Build single condition."""
        field_placeholder = self._add_attr_name(cond.field)
        value_placeholder = self._add_attr_value(cond.value)

        if cond.op == "=":
            return f"{field_placeholder} = {value_placeholder}"
        elif cond.op == "!=":
            return f"{field_placeholder} <> {value_placeholder}"
        elif cond.op in (">", ">=", "<", "<="):
            return f"{field_placeholder} {cond.op} {value_placeholder}"
        elif cond.op == "IN":
            # IN requires multiple value placeholders
            placeholders = [self._add_attr_value(v) for v in cond.value]
            return f"{field_placeholder} IN ({', '.join(placeholders)})"
        else:
            raise ValueError(f"Unsupported operator: {cond.op}")

    def _build_projection(self, fields: List[FieldExpr]) -> str | None:
        """Build projection expression."""
        if any(f.field == "*" for f in fields):
            return None

        field_placeholders = [self._add_attr_name(f.field) for f in fields]
        return ", ".join(field_placeholders)


# Register with factory
QueryBuilderFactory.register("dynamodb", DynamoDBBuilder)
```

## Usage - Consistent Across All Databases

```python
from src.query.factory import QueryBuilderFactory
from src.ir.models import QueryIR

# Load IR (same for all databases)
query_ir = QueryIR(**json.load(open('query.json')))

# PostgreSQL
builder = QueryBuilderFactory.create("postgresql")
result = builder.build(query_ir)
print(result)  # Shows SQL + params
rows = result.execute(pg_connection)

# MySQL
builder = QueryBuilderFactory.create("mysql")
result = builder.build(query_ir)
print(result)  # Shows SQL + params
rows = result.execute(mysql_connection)

# MongoDB
builder = QueryBuilderFactory.create("mongodb")
result = builder.build(query_ir)
print(result)  # Shows collection + filter + sort
docs = result.execute(mongo_db)

# DynamoDB
builder = QueryBuilderFactory.create("dynamodb")
result = builder.build(query_ir)
print(result)  # Shows expressions + attribute values
items = result.execute(dynamodb_resource)
```

## Key Advantages of This Unified Approach

### 1. Consistency

All databases use:
- Same `build()` interface
- Same `get_capabilities()` for feature discovery
- Same `validate_ir()` for pre-build validation
- Same factory pattern for creation

### 2. Testing

Same test pattern for all databases:

```python
def test_builder(builder_class, expected_result_type):
    """Generic test for any builder."""
    builder = builder_class()
    query_ir = QueryIR(...)

    # Validate capabilities
    capabilities = builder.get_capabilities()
    assert isinstance(capabilities, QueryCapabilities)

    # Build query
    result = builder.build(query_ir)
    assert isinstance(result, expected_result_type)

    # Check result
    result_dict = result.to_dict()
    assert "type" in result_dict

# Use for all builders
test_builder(PostgreSQLBuilder, PostgreSQLQueryResult)
test_builder(MySQLBuilder, MySQLQueryResult)
test_builder(MongoDBBuilder, MongoDBQueryResult)
test_builder(DynamoDBBuilder, DynamoDBQueryResult)
```

### 3. Extensibility

Adding a new database follows the exact same pattern:

```python
class NewDatabaseBuilder(QueryBuilder):
    def build(self, query_ir: QueryIR) -> NewDatabaseQueryResult:
        # Build query
        pass

    def get_capabilities(self) -> QueryCapabilities:
        # Return capabilities
        pass

# Register
QueryBuilderFactory.register("newdb", NewDatabaseBuilder)
```

### 4. Feature Discovery

All builders expose capabilities:

```python
builder = QueryBuilderFactory.create(db_type)
capabilities = builder.get_capabilities()

if not capabilities.supports_joins and query_ir.joins:
    raise UnsupportedFeatureError("JOINs not supported")
```

## Summary

**One Pattern, All Databases:**

1. **All builders** implement `QueryBuilder` abstract base
2. **All builders** return a `QueryResult` (protocol)
3. **All builders** provide `get_capabilities()`
4. **All builders** validate IR before building
5. **All builders** registered with `QueryBuilderFactory`

**Benefits:**
- Consistent interface across all databases
- Easy to test (same pattern)
- Easy to extend (add new database)
- Easy to maintain (one pattern to understand)
- Feature discovery built-in

**Differences handled internally:**
- PostgreSQL uses `"` quotes and `$1` params
- MySQL uses `` ` `` quotes and `?` params
- MongoDB uses dict filters and projections
- DynamoDB uses expression attribute names/values

The user doesn't care about these differences - they just call `build()` and `execute()`.
