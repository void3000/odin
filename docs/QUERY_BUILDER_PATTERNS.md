# Query Builder Design Patterns

## Problem Statement

The IR must translate to multiple fundamentally different query languages:

| Database | Query Language | Paradigm | Example |
|----------|---------------|----------|---------|
| PostgreSQL | SQL | Relational | `SELECT * FROM users WHERE status = 'active'` |
| MySQL | SQL | Relational | Same as PostgreSQL (minor syntax differences) |
| MongoDB | MQL | Document | `db.users.find({status: "active"})` |
| DynamoDB | PartiQL/API | Key-Value | `{"KeyConditionExpression": "pk = :pk"}` |

**Key Insight:** These aren't dialect variations - they're different query languages requiring different translation strategies.

## Recommended Design Patterns

### Pattern 1: Strategy Pattern (for similar languages)

Use for **PostgreSQL, MySQL, SQLite** - they share SQL grammar with minor differences.

```python
class QueryBuilder(ABC):
    """Abstract base for all query builders."""

    @abstractmethod
    def build(self, query_ir: QueryIR) -> QueryResult:
        """Build query from IR."""
        pass

class SQLBuilder(QueryBuilder):
    """Base SQL builder for relational databases."""

    def __init__(self, dialect: SQLDialect):
        self.dialect = dialect
        # Common SQL building logic

class PostgreSQLBuilder(SQLBuilder):
    """PostgreSQL-specific builder."""

    def __init__(self):
        super().__init__(SQLDialect.POSTGRESQL)

    def _build_limit(self, limit: int) -> str:
        return f"LIMIT {limit}"

    def _quote_identifier(self, name: str) -> str:
        return f'"{name}"'

class MySQLBuilder(SQLBuilder):
    """MySQL-specific builder."""

    def __init__(self):
        super().__init__(SQLDialect.MYSQL)

    def _quote_identifier(self, name: str) -> str:
        return f'`{name}`'
```

**When to use:** Languages with ~80%+ shared grammar.

### Pattern 2: Adapter Pattern (for different paradigms)

Use for **MongoDB, DynamoDB** - completely different query models.

```python
class MongoDBAdapter(QueryBuilder):
    """Adapter for MongoDB queries."""

    def build(self, query_ir: QueryIR) -> MongoQuery:
        """Translate IR to MongoDB query."""
        return MongoQuery(
            collection=query_ir.source.table,
            filter=self._build_mongo_filter(query_ir.filters),
            projection=self._build_mongo_projection(query_ir.fields),
            sort=self._build_mongo_sort(query_ir.order_by),
            limit=query_ir.limit
        )

    def _build_mongo_filter(self, filters: FilterExpr) -> dict:
        """Translate IR filters to MongoDB query operators."""
        if isinstance(filters, ConditionExpr):
            return self._build_mongo_condition(filters)
        elif isinstance(filters, LogicalExpr):
            if filters.logic == "AND":
                return {"$and": [self._build_mongo_filter(c) for c in filters.conditions]}
            else:  # OR
                return {"$or": [self._build_mongo_filter(c) for c in filters.conditions]}

    def _build_mongo_condition(self, cond: ConditionExpr) -> dict:
        """Map SQL operators to MongoDB operators."""
        operator_map = {
            "=": None,           # {field: value}
            "!=": "$ne",
            ">": "$gt",
            ">=": "$gte",
            "<": "$lt",
            "<=": "$lte",
            "IN": "$in",
            "LIKE": "$regex"
        }

        field = cond.field
        op = cond.op
        value = cond.value

        if op == "=":
            return {field: value}
        elif op == "LIKE":
            # Convert SQL LIKE to regex
            pattern = value.replace("%", ".*").replace("_", ".")
            return {field: {"$regex": pattern}}
        else:
            mongo_op = operator_map[op]
            return {field: {mongo_op: value}}

class DynamoDBAdapter(QueryBuilder):
    """Adapter for DynamoDB queries."""

    def build(self, query_ir: QueryIR) -> DynamoQuery:
        """Translate IR to DynamoDB query."""
        # DynamoDB requires knowing partition key
        # May need to extract from filters or schema
        return DynamoQuery(
            table_name=query_ir.source.table,
            key_condition_expression=self._build_key_condition(query_ir.filters),
            filter_expression=self._build_filter_expression(query_ir.filters),
            projection_expression=self._build_projection(query_ir.fields),
            limit=query_ir.limit
        )
```

**When to use:** Fundamentally different query models.

### Pattern 3: Template Method Pattern (for shared structure)

Use for common IR → Query translation steps.

```python
class QueryBuilder(ABC):
    """Template method pattern for query building."""

    def build(self, query_ir: QueryIR) -> QueryResult:
        """Template method - defines the algorithm structure."""
        # Validate IR (common across all builders)
        self._validate_ir(query_ir)

        # Build query (delegated to subclasses)
        query = self._build_query(query_ir)

        # Post-process (common across all builders)
        return self._post_process(query)

    @abstractmethod
    def _build_query(self, query_ir: QueryIR) -> Any:
        """Subclass-specific query building."""
        pass

    def _validate_ir(self, query_ir: QueryIR):
        """Common validation logic."""
        # Check for unsupported features
        pass

    def _post_process(self, query: Any) -> QueryResult:
        """Common post-processing."""
        pass
```

### Pattern 4: Factory Pattern (for builder selection)

Use to select the right builder based on database type.

```python
class QueryBuilderFactory:
    """Factory for creating appropriate query builders."""

    _builders: Dict[str, Type[QueryBuilder]] = {
        "postgresql": PostgreSQLBuilder,
        "mysql": MySQLBuilder,
        "sqlite": SQLiteBuilder,
        "mongodb": MongoDBAdapter,
        "dynamodb": DynamoDBAdapter,
    }

    @classmethod
    def create(cls, database_type: str) -> QueryBuilder:
        """Create appropriate builder for database type."""
        builder_class = cls._builders.get(database_type.lower())
        if not builder_class:
            raise ValueError(f"Unsupported database: {database_type}")
        return builder_class()

# Usage
builder = QueryBuilderFactory.create("postgresql")
result = builder.build(query_ir)
```

### Pattern 5: Visitor Pattern (for complex IR traversal)

Use when different databases need different IR traversal strategies.

```python
class IRVisitor(ABC):
    """Visitor for traversing IR structures."""

    @abstractmethod
    def visit_query(self, query: QueryIR) -> Any:
        pass

    @abstractmethod
    def visit_condition(self, condition: ConditionExpr) -> Any:
        pass

    @abstractmethod
    def visit_logical(self, logical: LogicalExpr) -> Any:
        pass

class SQLVisitor(IRVisitor):
    """Visitor for SQL generation."""

    def visit_condition(self, condition: ConditionExpr) -> str:
        return f"{condition.field} {condition.op} ?"

class MongoVisitor(IRVisitor):
    """Visitor for MongoDB generation."""

    def visit_condition(self, condition: ConditionExpr) -> dict:
        return {condition.field: {"$eq": condition.value}}
```

## Recommended Architecture

For your use case, I recommend a **hybrid approach**:

```
┌─────────────────────────────────────────┐
│         QueryBuilderFactory             │
│  (Factory Pattern)                      │
└────────────┬────────────────────────────┘
             │
             ├─────────────┬──────────────┬──────────────┐
             │             │              │              │
             ▼             ▼              ▼              ▼
┌─────────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│   SQLBuilder    │  │  MySQL   │  │ MongoDB  │  │ DynamoDB │
│   (Base)        │  │ Builder  │  │ Adapter  │  │ Adapter  │
│                 │  │          │  │          │  │          │
│ Template Method │  │ Strategy │  │ Adapter  │  │ Adapter  │
└─────────────────┘  └──────────┘  └──────────┘  └──────────┘
         │
         ├──── PostgreSQLBuilder (Strategy)
         └──── SQLiteBuilder (Strategy)
```

### Implementation Structure

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List

# Result types
@dataclass
class SQLQueryResult:
    """Result for SQL-based databases."""
    sql: str
    params: List[Any]
    param_style: str

@dataclass
class MongoQueryResult:
    """Result for MongoDB."""
    collection: str
    filter: dict
    projection: dict | None
    sort: dict | None
    limit: int | None

@dataclass
class DynamoQueryResult:
    """Result for DynamoDB."""
    table_name: str
    key_condition_expression: str | None
    filter_expression: str | None
    expression_attribute_values: dict
    projection_expression: str | None
    limit: int | None

# Base builder interface
class QueryBuilder(ABC):
    """Abstract base for all query builders."""

    @abstractmethod
    def build(self, query_ir: QueryIR) -> Any:
        """Build query from IR."""
        pass

    @abstractmethod
    def supports_feature(self, feature: str) -> bool:
        """Check if builder supports a feature."""
        pass

# SQL Builder (Template Method + Strategy)
class SQLBuilder(QueryBuilder):
    """Base class for SQL-based databases."""

    def __init__(self, dialect: SQLDialect):
        self.dialect = dialect

    def build(self, query_ir: QueryIR) -> SQLQueryResult:
        """Template method for SQL building."""
        self._validate_ir(query_ir)

        # Build components
        select = self._build_select(query_ir.fields)
        from_clause = self._build_from(query_ir.source)
        joins = self._build_joins(query_ir.joins)
        where = self._build_where(query_ir.filters)
        order = self._build_order_by(query_ir.order_by)
        limit = self._build_limit(query_ir.limit)

        # Combine
        parts = [select, from_clause, joins, where, order, limit]
        sql = "\n".join(p for p in parts if p)

        return SQLQueryResult(
            sql=sql,
            params=self._get_params(),
            param_style=self._get_param_style()
        )

    # Abstract methods for dialect-specific behavior
    @abstractmethod
    def _quote_identifier(self, name: str) -> str:
        """Quote an identifier (database-specific)."""
        pass

    @abstractmethod
    def _get_param_style(self) -> str:
        """Get parameter placeholder style."""
        pass

    # Concrete methods with default SQL behavior
    def _build_select(self, fields: List[FieldExpr]) -> str:
        """Build SELECT clause (common across SQL dialects)."""
        # ... implementation
        pass

# Concrete SQL builders
class PostgreSQLBuilder(SQLBuilder):
    """PostgreSQL-specific builder."""

    def __init__(self):
        super().__init__(SQLDialect.POSTGRESQL)

    def _quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def _get_param_style(self) -> str:
        return "numeric"  # $1, $2, etc.

class MySQLBuilder(SQLBuilder):
    """MySQL-specific builder."""

    def __init__(self):
        super().__init__(SQLDialect.MYSQL)

    def _quote_identifier(self, name: str) -> str:
        return f'`{name}`'

    def _get_param_style(self) -> str:
        return "qmark"  # ?

    def _build_limit(self, limit: int | None) -> str:
        """MySQL-specific LIMIT syntax."""
        if not limit:
            return ""
        return f"LIMIT {limit}"

# MongoDB Adapter
class MongoDBAdapter(QueryBuilder):
    """Adapter for MongoDB queries."""

    def build(self, query_ir: QueryIR) -> MongoQueryResult:
        """Translate IR to MongoDB query."""
        return MongoQueryResult(
            collection=query_ir.source.table,
            filter=self._build_filter(query_ir.filters),
            projection=self._build_projection(query_ir.fields),
            sort=self._build_sort(query_ir.order_by),
            limit=query_ir.limit
        )

    def supports_feature(self, feature: str) -> bool:
        """MongoDB doesn't support traditional JOINs."""
        if feature == "joins":
            return False  # Would need $lookup
        return True

    def _build_filter(self, filters: FilterExpr | None) -> dict:
        """Translate IR filters to MongoDB query."""
        if not filters:
            return {}

        if isinstance(filters, ConditionExpr):
            return self._translate_condition(filters)
        elif isinstance(filters, LogicalExpr):
            return self._translate_logical(filters)

    def _translate_condition(self, cond: ConditionExpr) -> dict:
        """Map SQL operators to MongoDB operators."""
        operator_map = {
            "=": lambda f, v: {f: v},
            "!=": lambda f, v: {f: {"$ne": v}},
            ">": lambda f, v: {f: {"$gt": v}},
            ">=": lambda f, v: {f: {"$gte": v}},
            "<": lambda f, v: {f: {"$lt": v}},
            "<=": lambda f, v: {f: {"$lte": v}},
            "IN": lambda f, v: {f: {"$in": v}},
            "LIKE": lambda f, v: {f: {"$regex": self._like_to_regex(v)}}
        }

        translator = operator_map.get(cond.op)
        if not translator:
            raise ValueError(f"Unsupported operator for MongoDB: {cond.op}")

        return translator(cond.field, cond.value)

    def _translate_logical(self, logical: LogicalExpr) -> dict:
        """Translate AND/OR to MongoDB $and/$or."""
        mongo_op = "$and" if logical.logic == "AND" else "$or"
        conditions = [self._build_filter(c) for c in logical.conditions]
        return {mongo_op: conditions}

    def _like_to_regex(self, pattern: str) -> str:
        """Convert SQL LIKE pattern to regex."""
        # % -> .*, _ -> .
        regex = pattern.replace("%", ".*").replace("_", ".")
        return f"^{regex}$"

    def _build_projection(self, fields: List[FieldExpr]) -> dict | None:
        """Build MongoDB projection."""
        if any(f.field == "*" for f in fields):
            return None  # Return all fields

        return {f.field: 1 for f in fields}

    def _build_sort(self, order_by: List[OrderExpr] | None) -> dict | None:
        """Build MongoDB sort."""
        if not order_by:
            return None

        return {
            o.field: 1 if o.direction == "ASC" else -1
            for o in order_by
        }

# DynamoDB Adapter
class DynamoDBAdapter(QueryBuilder):
    """Adapter for DynamoDB queries."""

    def __init__(self, partition_key: str):
        """DynamoDB requires knowing the partition key."""
        self.partition_key = partition_key

    def build(self, query_ir: QueryIR) -> DynamoQueryResult:
        """Translate IR to DynamoDB query."""
        # DynamoDB is complex - requires partition key in WHERE clause
        # This is a simplified example

        key_condition, filter_condition, attr_values = self._split_conditions(
            query_ir.filters
        )

        return DynamoQueryResult(
            table_name=query_ir.source.table,
            key_condition_expression=key_condition,
            filter_expression=filter_condition,
            expression_attribute_values=attr_values,
            projection_expression=self._build_projection(query_ir.fields),
            limit=query_ir.limit
        )

    def supports_feature(self, feature: str) -> bool:
        """DynamoDB has limited query capabilities."""
        unsupported = ["joins", "complex_filters"]
        return feature not in unsupported

    def _split_conditions(self, filters: FilterExpr | None) -> tuple:
        """Split conditions into key conditions and filter conditions.

        DynamoDB requires partition key in KeyConditionExpression,
        other filters go in FilterExpression.
        """
        # Complex logic to separate key vs filter conditions
        # ...
        pass

# Factory
class QueryBuilderFactory:
    """Factory for creating query builders."""

    @staticmethod
    def create(database_type: str, **kwargs) -> QueryBuilder:
        """Create appropriate builder."""
        builders = {
            "postgresql": PostgreSQLBuilder,
            "mysql": MySQLBuilder,
            "sqlite": SQLiteBuilder,
            "mongodb": MongoDBAdapter,
            "dynamodb": DynamoDBAdapter,
        }

        builder_class = builders.get(database_type.lower())
        if not builder_class:
            raise ValueError(f"Unsupported database: {database_type}")

        return builder_class(**kwargs)
```

## Usage Example

```python
# PostgreSQL
builder = QueryBuilderFactory.create("postgresql")
result = builder.build(query_ir)
cursor.execute(result.sql, result.params)

# MongoDB
builder = QueryBuilderFactory.create("mongodb")
result = builder.build(query_ir)
db[result.collection].find(
    result.filter,
    projection=result.projection,
    sort=result.sort,
    limit=result.limit
)

# DynamoDB
builder = QueryBuilderFactory.create("dynamodb", partition_key="user_id")
result = builder.build(query_ir)
table.query(
    KeyConditionExpression=result.key_condition_expression,
    FilterExpression=result.filter_expression,
    ExpressionAttributeValues=result.expression_attribute_values,
    Limit=result.limit
)
```

## Pattern Summary

| Pattern | Use Case | Example |
|---------|----------|---------|
| **Strategy** | SQL dialects with shared grammar | PostgreSQL vs MySQL |
| **Adapter** | Different query paradigms | MongoDB, DynamoDB |
| **Template Method** | Shared building algorithm | Common IR → Query flow |
| **Factory** | Builder selection | Create right builder for DB type |
| **Visitor** | Complex IR traversal | Optional: for very complex IR |

## Key Design Principles

1. **Separation of Concerns**: Each builder handles one database type
2. **Open/Closed Principle**: Easy to add new database adapters
3. **Liskov Substitution**: All builders implement same interface
4. **Single Responsibility**: Each builder only translates to its target format
5. **Dependency Inversion**: Depend on QueryBuilder abstraction, not concrete builders

## Feature Matrix

Different databases support different features:

| Feature | PostgreSQL | MySQL | MongoDB | DynamoDB |
|---------|-----------|-------|---------|----------|
| SELECT | ✓ | ✓ | ✓ (find) | ✓ (query) |
| JOIN | ✓ | ✓ | Partial ($lookup) | ✗ |
| Complex Filters | ✓ | ✓ | ✓ | Limited |
| ORDER BY | ✓ | ✓ | ✓ (sort) | ✓ |
| LIMIT | ✓ | ✓ | ✓ | ✓ |
| Aggregates | ✓ | ✓ | ✓ (pipeline) | Limited |

**Recommendation:** Use `supports_feature()` method to check capabilities before building.

## Testing Strategy

```python
# Test SQL builders with same IR
def test_sql_builders():
    query_ir = QueryIR(...)

    pg_builder = PostgreSQLBuilder()
    mysql_builder = MySQLBuilder()

    pg_result = pg_builder.build(query_ir)
    mysql_result = mysql_builder.build(query_ir)

    # Both should produce semantically equivalent SQL
    assert pg_result.sql  # has double quotes
    assert mysql_result.sql  # has backticks

# Test MongoDB adapter
def test_mongodb_adapter():
    query_ir = QueryIR(...)

    mongo_builder = MongoDBAdapter()
    result = mongo_builder.build(query_ir)

    assert isinstance(result, MongoQueryResult)
    assert result.filter == {"status": "active"}
```

## Conclusion

**For your use case:**

1. **SQL databases (PostgreSQL, MySQL)**: Use **Strategy Pattern** with shared `SQLBuilder` base
2. **MongoDB**: Use **Adapter Pattern** to translate IR → MQL
3. **DynamoDB**: Use **Adapter Pattern** to translate IR → DynamoDB API
4. **Factory Pattern**: To select the right builder
5. **Template Method**: For shared IR validation and post-processing

This gives you flexibility, testability, and maintainability while handling fundamentally different query languages.
