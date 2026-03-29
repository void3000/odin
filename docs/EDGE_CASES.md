# PostgreSQL Visitor Pattern - Edge Cases Analysis

## Currently Tested Edge Cases

### Field Handling
- ✓ Wildcard with table qualifier (`users.*`)
- ✓ Mixed qualified and unqualified fields
- ✓ Fields with aliases

### State Management
- ✓ Parameter counter resets between builds
- ✓ Empty joins list
- ✓ No filters
- ✓ No ORDER BY
- ✓ No LIMIT

### SQL Injection Prevention
- ✓ Identifier escaping (double quotes in names)
- ✓ Parameterized values

## Potential Untested Edge Cases

### 1. **Empty or Malformed Filter Expressions**

**Issue**: `visit_logical()` assumes `expr.conditions` is non-empty
```python
def visit_logical(self, expr: LogicalExpr) -> str:
    sub_conditions = [self.visit_filter(cond) for cond in expr.conditions]
    joined = f" {logic_op} ".join(f"({c})" for c in sub_conditions)
    return f"({joined})"
```

**Risk**: Empty `conditions` list would produce `()` which is invalid SQL
- `LogicalExpr(logic="AND", conditions=[])` → `WHERE ()`

**Mitigation**: IR models validate `min_length=2`, but runtime check missing in visitor

---

### 2. **Deep Nesting of Logical Expressions**

**Issue**: Recursive `visit_logical()` → `visit_filter()` → `visit_logical()` could cause stack overflow

**Risk**: Queries like:
```json
{
  "logic": "AND",
  "conditions": [
    {"logic": "OR", "conditions": [
      {"logic": "AND", "conditions": [
        // ... 1000+ levels deep
      ]}
    ]}
  ]
}
```

**Current State**: No depth limit in visitor
**Python limit**: ~1000 recursion depth (configurable with `sys.setrecursionlimit()`)

---

### 3. **Null/None Values in Conditions**

**Issue**: `visit_value()` handles field references and scalars, but not NULL explicitly

**Risk**:
```python
ConditionExpr(field="deleted_at", op="=", value=None)
```
Would produce: `WHERE "deleted_at" = $1` with `params=[None]`

**PostgreSQL behavior**: This works but is not idiomatic (should use `IS NULL`)

---

### 4. **Empty String Values**

**Issue**: No special handling for empty strings

**Cases**:
- `ConditionExpr(field="name", op="=", value="")`
- `ConditionExpr(field="status", op="IN", value=[])`

**Current behavior**: Empty string is parameterized correctly
**Empty list**: Would cause `QueryBuildError` in `_add_param()` → IndexError

---

### 5. **Special Characters in Identifiers**

**Issue**: PostgreSQL allows Unicode, spaces, and special chars in quoted identifiers

**Test cases**:
- Unicode: `table="用户表"`, `field="名前"`
- Spaces: `table="my table"`, `field="first name"`
- Reserved words: `table="user"`, `field="select"`
- SQL injection attempt: `field='id"; DROP TABLE users--'`

**Current handling**: `_quote_identifier()` escapes double quotes but not tested

---

### 6. **Maximum SQL Length**

**Issue**: No limit on generated SQL length

**Risk**: Very large queries could:
- Exceed PostgreSQL's max query length
- Cause memory issues
- Hit network packet limits

**Example**:
- 10,000 fields in SELECT
- 1,000 values in IN clause
- 100 JOINs

---

### 7. **Field References in Filters with Missing Table Context**

**Issue**: `visit_value()` handles field references but doesn't validate they're in scope

**Risk**:
```python
JoinExpr(
    type="INNER",
    table="orders",
    on=ConditionExpr(
        field="user_id",
        op="=",
        value={"table": "nonexistent", "field": "id"}  # Wrong table
    )
)
```

**Current behavior**: Generates valid SQL syntax but semantically wrong

---

### 8. **Operator Case Sensitivity**

**Issue**: Operators stored as strings in IR

**Risk**:
- `op="in"` vs `op="IN"`
- `op="Like"` vs `op="LIKE"`

**Current behavior**: Operators passed through as-is, PostgreSQL is case-insensitive but style inconsistent

---

### 9. **Multiple Wildcards in SELECT**

**Issue**: Combining `*` with other fields or multiple table wildcards

**Cases**:
```python
fields=[
    FieldExpr(field="*"),
    FieldExpr(field="created_at")  # Is this valid?
]

fields=[
    FieldExpr(field="*", table="users"),
    FieldExpr(field="*", table="orders")  # Valid but unusual
]
```

**PostgreSQL**: Allows this, but it's unusual

---

### 10. **Join Without Alias on Same Table (Self-Join)**

**Issue**: Self-joins require aliases to disambiguate

**Risk**:
```python
QueryIR(
    source=TableSource(table="users"),
    joins=[
        JoinExpr(
            type="INNER",
            table="users",  # Same table, no alias!
            on=ConditionExpr(field="manager_id", op="=", value={"field": "id"})
        )
    ]
)
```

**Produces**: `FROM "users" INNER JOIN "users" ON ...` (ambiguous)
**Should be**: `FROM "users" u1 INNER JOIN "users" u2 ON ...`

---

### 11. **Very Long Identifier Names**

**Issue**: PostgreSQL has 63-byte limit for identifiers

**Risk**:
```python
table="this_is_a_very_long_table_name_that_exceeds_postgresql_identifier_limit_maximum"
```

**PostgreSQL behavior**: Silently truncates to 63 bytes
**Visitor behavior**: Passes through as-is

---

### 12. **LIMIT with 0 or Negative Values**

**Issue**: `visit_limit()` doesn't validate the value

**Risk**:
- `limit=0` → `LIMIT 0` (valid, returns no rows)
- `limit=-1` → `LIMIT -1` (PostgreSQL error)

**Current**: IR models validate `gt=0`, but visitor trusts input

---

### 13. **Order of Operations in Complex Logical Expressions**

**Issue**: Parenthesization strategy might not match intent

**Example**:
```python
# (A OR B) AND C vs A OR (B AND C)
LogicalExpr(
    logic="AND",
    conditions=[
        LogicalExpr(logic="OR", conditions=[A, B]),
        C
    ]
)
```

**Current behavior**: All nested conditions wrapped in `()`
**Result**: `((A) OR (B)) AND (C)` - excessive but correct

---

### 14. **Type Mismatches Between Operator and Value**

**Issue**: Visitor doesn't validate type compatibility

**Risk**:
```python
ConditionExpr(field="age", op=">", value="not a number")
ConditionExpr(field="name", op="LIKE", value=123)
```

**Current**: Generates SQL, error at execution time
**Should**: IRValidator handles this, but visitor doesn't double-check

---

### 15. **Concurrent Build Calls on Same Builder Instance**

**Issue**: `self.params` and `self.param_counter` are instance state

**Risk**: In multi-threaded environment:
```python
builder = PostgreSQLBuilder()
thread1: builder.build(query1)  # Sets params=[...]
thread2: builder.build(query2)  # Resets params, corrupts thread1
```

**Current**: Each `build()` resets state, but not thread-safe

---

## Recommendations

### Critical (Should Fix)
1. **Add depth limit to recursive visiting** (prevent stack overflow)
2. **Handle NULL values idiomatically** (`IS NULL` instead of `= NULL`)
3. **Validate empty IN lists** (prevent IndexError)
4. **Thread safety**: Document builder is not thread-safe OR make it thread-safe

### Important (Should Test)
5. Test special characters in identifiers
6. Test self-joins without aliases
7. Test very large queries (stress test)

### Nice to Have (Document)
8. Document identifier length limits
9. Document operator case expectations
10. Document wildcard behavior with other fields

---

## Test Coverage Gaps

Create additional tests for:

```python
# 1. Empty logical expression (should fail at IR validation)
# 2. Deep nesting (100+ levels)
# 3. NULL values
# 4. Empty IN list
# 5. Special characters: table="my\"table", field="user's name"
# 6. Unicode identifiers
# 7. Self-join without alias
# 8. LIMIT 0
# 9. Concurrent builds (thread safety test)
# 10. Very large SELECT (1000+ fields)
# 11. Very large IN (1000+ values)
```
