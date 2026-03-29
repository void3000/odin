# MongoDB Connector Analysis

## Question: Would MongoDB Work with Current Design?

**Short Answer**: Yes, but with important caveats and design adjustments needed.

---

## Current Architecture Review

### What We Have

```
QueryIR → QueryBuilder → QueryResult(sql, params) → QueryExecutor → DatabaseConnector
```

**Key Assumption**: The `QueryBuilder` produces **SQL** queries.

```python
class PostgreSQLBuilder(QueryBuilder):
    def build(self, query_ir: QueryIR) -> PostgreSQLQueryResult:
        return PostgreSQLQueryResult(
            sql="SELECT * FROM users WHERE status = $1",  # ← SQL string
            params=["active"]
        )
```

---

## The MongoDB Problem

### MongoDB Doesn't Use SQL

MongoDB uses a **different query language**:

```javascript
// MongoDB query (not SQL)
db.users.find(
    { status: "active" },
    { name: 1, email: 1 }
)
```

Or with Python driver (pymongo):

```python
collection.find(
    {"status": "active"},  # Filter (dict)
    {"name": 1, "email": 1}  # Projection (dict)
)
```

### Current Mismatch

```python
class MongoDBConnector:
    def execute_query(self, sql: str, params: List[Any]) -> RawResult:
        # ❌ Problem: MongoDB doesn't execute SQL strings!
        # ❌ We receive "SELECT * FROM users WHERE status = $1"
        # ❌ MongoDB needs {"status": "active"} instead
```

---

## Solution Approaches

### Approach 1: Separate Builder for MongoDB ✓ RECOMMENDED

Create `MongoDBBuilder` that translates IR to MongoDB queries:

```python
@dataclass
class MongoDBQueryResult:
    """MongoDB query result (not SQL)."""
    collection: str
    filter: dict
    projection: dict
    sort: List[Tuple[str, int]]  # [(field, direction)]
    limit: Optional[int]

class MongoDBBuilder(QueryBuilder):
    """Translates IR to MongoDB query structure."""

    def build(self, query_ir: QueryIR) -> MongoDBQueryResult:
        return MongoDBQueryResult(
            collection="users",
            filter={"status": "active"},
            projection={"name": 1, "email": 1, "_id": 0},
            sort=[("created_at", -1)],
            limit=10
        )
```

Then MongoDB connector uses this structure:

```python
class MongoDBConnector:
    def execute_query(self, query: MongoDBQueryResult) -> RawResult:
        collection = self.db[query.collection]
        cursor = collection.find(
            query.filter,
            query.projection
        )
        if query.sort:
            cursor = cursor.sort(query.sort)
        if query.limit:
            cursor = cursor.limit(query.limit)

        # Convert to RawResult format
        rows = list(cursor)
        return self._to_raw_result(rows)
```

**Pros**:
- Clean separation
- MongoDB-native queries (better performance)
- Type-safe query structure
- No SQL parsing needed

**Cons**:
- Need separate builder for each NoSQL database
- Can't share SQL builders with MongoDB

---

### Approach 2: Generic Query Interface ✓ BETTER LONG-TERM

Modify the bridge to use a **generic query representation**:

```python
@dataclass
class QueryResult:
    """Generic query result (database-agnostic)."""
    database_type: str  # "postgresql", "mongodb", etc.
    query: Any  # SQL string, MongoDB dict, DynamoDB params, etc.
    params: Any  # SQL params, MongoDB options, etc.

class QueryBuilder(ABC):
    @abstractmethod
    def build(self, query_ir: QueryIR) -> QueryResult:
        """Build database-specific query from IR."""
        pass

    @abstractmethod
    def get_database_type(self) -> str:
        """Return database type this builder targets."""
        pass
```

Then builders produce appropriate formats:

```python
class PostgreSQLBuilder(QueryBuilder):
    def build(self, query_ir: QueryIR) -> QueryResult:
        sql = self._generate_sql(query_ir)
        return QueryResult(
            database_type="postgresql",
            query=sql,  # SQL string
            params=self.params  # List of values
        )

class MongoDBBuilder(QueryBuilder):
    def build(self, query_ir: QueryIR) -> QueryResult:
        mongo_query = self._generate_mongo_query(query_ir)
        return QueryResult(
            database_type="mongodb",
            query=mongo_query,  # Dict with filter, projection, etc.
            params={}  # MongoDB options
        )
```

Connectors handle their own query types:

```python
class MongoDBConnector:
    def execute_query(self, query_result: QueryResult) -> RawResult:
        assert query_result.database_type == "mongodb"

        # Extract MongoDB-specific query structure
        mongo_query = query_result.query  # Dict
        collection = self.db[mongo_query["collection"]]

        cursor = collection.find(
            mongo_query.get("filter", {}),
            mongo_query.get("projection", None)
        )
        # ... apply sort, limit, etc.
```

**Pros**:
- Single QueryExecutor works for all databases
- Each builder produces optimal format
- Type-safe with proper structure
- Extensible to any database type

**Cons**:
- More complex QueryResult structure
- Need type checking in connectors
- Less type safety (using `Any`)

---

### Approach 3: Hybrid - SQL-to-MongoDB Translation ❌ NOT RECOMMENDED

Try to parse SQL and translate to MongoDB:

```python
class MongoDBConnector:
    def execute_query(self, sql: str, params: List[Any]) -> RawResult:
        # Parse SQL: "SELECT name, email FROM users WHERE status = $1"
        # Translate to MongoDB: {"status": params[0]}
        parsed = self._parse_sql(sql)
        mongo_query = self._sql_to_mongo(parsed)
        ...
```

**Pros**:
- Reuse existing SQL builders
- No changes to QueryBuilder interface

**Cons**:
- ❌ SQL parsing is complex and error-prone
- ❌ SQL features don't map 1:1 to MongoDB (JOINs, subqueries)
- ❌ Performance overhead
- ❌ Fragile (breaks on complex SQL)
- ❌ Loses MongoDB-specific optimizations

---

## Recommended Design: Approach 2 (Generic Query Interface)

### Updated Architecture

```python
# 1. Generic QueryResult
@dataclass
class QueryResult:
    database_type: str
    query: Any
    metadata: dict = field(default_factory=dict)

# 2. Builders produce appropriate formats
class PostgreSQLBuilder:
    def build(self, query_ir: QueryIR) -> QueryResult:
        return QueryResult(
            database_type="postgresql",
            query={
                "sql": 'SELECT * FROM "users" WHERE "status" = $1',
                "params": ["active"]
            }
        )

class MongoDBBuilder:
    def build(self, query_ir: QueryIR) -> QueryResult:
        return QueryResult(
            database_type="mongodb",
            query={
                "collection": "users",
                "filter": {"status": "active"},
                "projection": None,
                "sort": None,
                "limit": None
            }
        )

# 3. Connectors handle their own formats
class PostgreSQLConnector:
    def execute_query(self, query_result: QueryResult) -> RawResult:
        sql = query_result.query["sql"]
        params = query_result.query["params"]
        self.cursor.execute(sql, params)
        ...

class MongoDBConnector:
    def execute_query(self, query_result: QueryResult) -> RawResult:
        q = query_result.query
        collection = self.db[q["collection"]]
        cursor = collection.find(q["filter"], q["projection"])
        if q["sort"]:
            cursor = cursor.sort(q["sort"])
        if q["limit"]:
            cursor = cursor.limit(q["limit"])
        ...
```

---

## MongoDB Query Translation Examples

### Example 1: Simple SELECT

**IR**:
```python
QueryIR(
    operation="SELECT",
    source=TableSource(table="users"),
    fields=[FieldExpr(field="name"), FieldExpr(field="email")],
    filters=ConditionExpr(field="status", op="=", value="active")
)
```

**PostgreSQL**:
```sql
SELECT "name", "email"
FROM "users"
WHERE "status" = $1
-- params: ["active"]
```

**MongoDB**:
```python
{
    "collection": "users",
    "filter": {"status": "active"},
    "projection": {"name": 1, "email": 1, "_id": 0}
}

# Python execution:
db.users.find(
    {"status": "active"},
    {"name": 1, "email": 1, "_id": 0}
)
```

---

### Example 2: Logical Operators

**IR**:
```python
LogicalExpr(
    logic="AND",
    conditions=[
        ConditionExpr(field="age", op=">", value=18),
        ConditionExpr(field="status", op="=", value="active")
    ]
)
```

**PostgreSQL**:
```sql
WHERE ("age" > $1) AND ("status" = $2)
-- params: [18, "active"]
```

**MongoDB**:
```python
{
    "filter": {
        "$and": [
            {"age": {"$gt": 18}},
            {"status": "active"}
        ]
    }
}

# Simplified (MongoDB optimizes AND):
{
    "filter": {
        "age": {"$gt": 18},
        "status": "active"
    }
}
```

---

### Example 3: IN Operator

**IR**:
```python
ConditionExpr(field="status", op="IN", value=["active", "pending"])
```

**PostgreSQL**:
```sql
WHERE "status" IN ($1, $2)
-- params: ["active", "pending"]
```

**MongoDB**:
```python
{
    "filter": {
        "status": {"$in": ["active", "pending"]}
    }
}
```

---

### Example 4: ORDER BY + LIMIT

**IR**:
```python
QueryIR(
    ...
    order_by=[OrderExpr(field="created_at", direction="DESC")],
    limit=10
)
```

**PostgreSQL**:
```sql
ORDER BY "created_at" DESC
LIMIT 10
```

**MongoDB**:
```python
{
    "sort": [("created_at", -1)],  # -1 = descending
    "limit": 10
}

# Python execution:
db.users.find(...).sort("created_at", -1).limit(10)
```

---

## MongoDB Challenges

### 1. JOINs ❌ MAJOR ISSUE

**SQL JOINs**:
```sql
SELECT u.name, o.total
FROM users u
INNER JOIN orders o ON u.id = o.user_id
```

**MongoDB**:
MongoDB doesn't have traditional JOINs. Options:

**Option A: $lookup (aggregation pipeline)**
```python
db.users.aggregate([
    {
        "$lookup": {
            "from": "orders",
            "localField": "_id",
            "foreignField": "user_id",
            "as": "orders"
        }
    }
])
```

**Option B: Multiple queries (application-level join)**
```python
# Query 1: Get users
users = db.users.find(...)

# Query 2: Get orders for those users
user_ids = [u["_id"] for u in users]
orders = db.orders.find({"user_id": {"$in": user_ids}})

# Join in application code
```

**Implication**: MongoDBBuilder needs to:
- Detect JOINs in IR
- Generate `$lookup` aggregation pipeline OR
- Return multiple queries for application-level join

---

### 2. Aggregations

**SQL**:
```sql
SELECT status, COUNT(*) as count
FROM users
GROUP BY status
```

**MongoDB**:
```python
db.users.aggregate([
    {
        "$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }
    }
])
```

**Implication**: IR needs aggregation support (not yet implemented)

---

### 3. Subqueries ❌ COMPLEX

**SQL**:
```sql
SELECT * FROM users
WHERE id IN (SELECT user_id FROM orders WHERE total > 100)
```

**MongoDB**:
```python
# Option 1: $lookup with pipeline
db.users.aggregate([
    {
        "$lookup": {
            "from": "orders",
            "let": {"userId": "$_id"},
            "pipeline": [
                {"$match": {
                    "$expr": {"$and": [
                        {"$eq": ["$user_id", "$$userId"]},
                        {"$gt": ["$total", 100]}
                    ]}
                }}
            ],
            "as": "matching_orders"
        }
    },
    {"$match": {"matching_orders": {"$ne": []}}}
])

# Option 2: Two separate queries
order_users = db.orders.find({"total": {"$gt": 100}}).distinct("user_id")
users = db.users.find({"_id": {"$in": order_users}})
```

---

## IR Limitations for MongoDB

### Current IR Works For:
✓ Simple SELECT with filters
✓ WHERE conditions (=, !=, >, <, >=, <=, IN, LIKE)
✓ Logical operators (AND, OR)
✓ ORDER BY
✓ LIMIT
✓ Field selection (projection)

### Current IR Doesn't Support:
❌ JOINs (MongoDB needs $lookup or separate queries)
❌ Aggregations (GROUP BY, COUNT, SUM, AVG)
❌ Subqueries (complex in MongoDB)
❌ UPDATE operations
❌ DELETE operations
❌ INSERT operations

---

## Implementation Plan for MongoDB Support

### Phase 1: Basic MongoDBBuilder
Implement simple queries only:

```python
class MongoDBBuilder(QueryBuilder):
    """MongoDB query builder - basic queries only."""

    def build(self, query_ir: QueryIR) -> QueryResult:
        # Validate no JOINs
        if query_ir.joins:
            raise UnsupportedFeatureError("MongoDB builder doesn't support JOINs yet")

        return QueryResult(
            database_type="mongodb",
            query={
                "collection": query_ir.source.table,
                "filter": self._build_filter(query_ir.filters),
                "projection": self._build_projection(query_ir.fields),
                "sort": self._build_sort(query_ir.order_by),
                "limit": query_ir.limit
            }
        )

    def _build_filter(self, filters):
        """Convert IR filters to MongoDB filter dict."""
        if isinstance(filters, ConditionExpr):
            return self._build_condition(filters)
        elif isinstance(filters, LogicalExpr):
            return self._build_logical(filters)

    def _build_condition(self, cond: ConditionExpr):
        """Convert condition to MongoDB operator."""
        op_map = {
            "=": None,  # Direct equality
            "!=": "$ne",
            ">": "$gt",
            ">=": "$gte",
            "<": "$lt",
            "<=": "$lte",
            "IN": "$in",
            "LIKE": "$regex"  # Convert LIKE to regex
        }

        mongo_op = op_map[cond.op]
        if mongo_op is None:
            # Direct equality
            return {cond.field: cond.value}
        else:
            return {cond.field: {mongo_op: cond.value}}
```

### Phase 2: MongoDBConnector

```python
class MongoDBConnector:
    """MongoDB connector using pymongo."""

    def __init__(self, connection_string: str, database: str):
        import pymongo
        self.client = pymongo.MongoClient(connection_string)
        self.db = self.client[database]

    def execute_query(self, query_result: QueryResult) -> RawResult:
        q = query_result.query
        collection = self.db[q["collection"]]

        # Build cursor
        cursor = collection.find(q["filter"], q["projection"])

        # Apply sort
        if q["sort"]:
            cursor = cursor.sort(q["sort"])

        # Apply limit
        if q["limit"]:
            cursor = cursor.limit(q["limit"])

        # Fetch results
        docs = list(cursor)

        # Convert to RawResult
        return self._to_raw_result(docs, q["projection"])

    def _to_raw_result(self, docs, projection):
        """Convert MongoDB docs to RawResult format."""
        if not docs:
            return RawResult(rows=[], columns=[], rowcount=0)

        # Extract columns from projection or first doc
        if projection:
            columns = [k for k in projection.keys() if k != "_id"]
        else:
            columns = list(docs[0].keys())

        # Convert docs to tuples
        rows = [
            tuple(doc.get(col) for col in columns)
            for doc in docs
        ]

        return RawResult(
            rows=rows,
            columns=columns,
            rowcount=len(rows)
        )
```

### Phase 3: Advanced Features (JOINs via $lookup)

Add support for JOINs using aggregation pipeline:

```python
def _build_join_pipeline(self, query_ir: QueryIR):
    """Build aggregation pipeline for JOINs."""
    pipeline = []

    # Add $lookup stages for each join
    for join in query_ir.joins:
        pipeline.append({
            "$lookup": {
                "from": join.table,
                "localField": join.on.field,
                "foreignField": join.on.value["field"],
                "as": f"joined_{join.table}"
            }
        })

    # Add $match stage for filters
    if query_ir.filters:
        pipeline.append({
            "$match": self._build_filter(query_ir.filters)
        })

    return pipeline
```

---

## Summary: Would MongoDB Work?

### Short Answer: YES, with modifications

### What Works Out of the Box:
✓ Basic SELECT queries
✓ WHERE conditions (=, !=, >, <, IN, etc.)
✓ Logical operators (AND, OR)
✓ ORDER BY
✓ LIMIT
✓ Field projection

### What Needs Implementation:
1. **MongoDBBuilder** - Translate IR to MongoDB query structure
2. **MongoDBConnector** - Execute MongoDB queries via pymongo
3. **Generic QueryResult** - Support both SQL and NoSQL formats

### What's Challenging:
❌ JOINs (need $lookup or app-level joins)
❌ Aggregations (need IR extensions)
❌ Subqueries (complex translation)

### Recommended Approach:
1. **Modify QueryResult** to be database-agnostic (use `query: Any`)
2. **Implement MongoDBBuilder** for basic queries
3. **Implement MongoDBConnector** with pymongo
4. **Add JOIN support** later via $lookup aggregation pipeline

---

## Conclusion

**Yes, MongoDB would work**, but requires:

1. ✅ Generic query interface (Approach 2)
2. ✅ MongoDB-specific builder
3. ✅ MongoDB connector
4. ⚠️ Limited feature set initially (no JOINs)
5. ⚠️ IR extensions for advanced MongoDB features

The **Bridge Pattern holds up perfectly** - we just need to make QueryResult more flexible to accommodate different query formats (SQL strings vs MongoDB dicts).
