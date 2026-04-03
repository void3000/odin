# Aggregate Functions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add COUNT, SUM, AVG, MIN, MAX aggregate function support to FieldExpr, the validator, the PostgreSQL SQL builder, and the LLM system prompt.

**Architecture:** Add an optional `function` field to the existing `FieldExpr` model. The validator allows `*` only with COUNT and still validates column existence for named columns. The SQL builder wraps the column reference in the function call. The LLM system prompt documents the new field and adds an example.

**Tech Stack:** Pydantic models, pytest, existing PostgreSQLBuilder visitor pattern

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/ir/models.py` | Modify | Add optional `function` field to `FieldExpr` |
| `tests/test_ir_models.py` | Modify | Test FieldExpr with function field |
| `src/ir/validator.py` | Modify | Handle aggregates in `_validate_fields` |
| `src/query/postgresql.py` | Modify | Emit `FUNCTION(column)` in `visit_field` |
| `tests/test_postgresql_builder.py` | Modify | Test aggregate SQL generation |
| `src/llm/nl_to_ir.py` | Modify | Update system prompt with aggregate docs + example |

---

### Task 1: Add `function` Field to FieldExpr

**Files:**
- Modify: `src/ir/models.py:49-77`
- Modify: `tests/test_ir_models.py`

- [ ] **Step 1: Write failing tests for FieldExpr with function**

```python
# Add to tests/test_ir_models.py
from src.ir.models import FieldExpr


class TestFieldExprAggregates:
    def test_field_with_count_star(self):
        field = FieldExpr(field="*", function="COUNT", alias="total")
        assert field.function == "COUNT"
        assert field.field == "*"
        assert field.alias == "total"

    def test_field_with_sum(self):
        field = FieldExpr(field="total", function="SUM", table="orders", alias="total_sum")
        assert field.function == "SUM"
        assert field.field == "total"

    def test_field_with_avg(self):
        field = FieldExpr(field="age", function="AVG")
        assert field.function == "AVG"

    def test_field_with_min(self):
        field = FieldExpr(field="price", function="MIN")
        assert field.function == "MIN"

    def test_field_with_max(self):
        field = FieldExpr(field="price", function="MAX")
        assert field.function == "MAX"

    def test_field_without_function_defaults_none(self):
        field = FieldExpr(field="name")
        assert field.function is None

    def test_invalid_function_rejected(self):
        import pytest
        with pytest.raises(Exception):
            FieldExpr(field="name", function="INVALID")

    def test_count_star_in_query_ir(self):
        """Test that a QueryIR with COUNT(*) parses correctly from JSON."""
        from src.ir.models import QueryIR
        import json
        ir_json = json.dumps({
            "operation": "SELECT",
            "source": {"table": "users"},
            "fields": [{"field": "*", "function": "COUNT", "alias": "total"}]
        })
        query_ir = QueryIR.model_validate_json(ir_json)
        assert query_ir.fields[0].function == "COUNT"
        assert query_ir.fields[0].field == "*"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ir_models.py::TestFieldExprAggregates -v`
Expected: FAIL — `function` is not a valid field for FieldExpr

- [ ] **Step 3: Add function field to FieldExpr**

In `src/ir/models.py`, add to the `FieldExpr` class after the `alias` field:

```python
    function: Literal["COUNT", "SUM", "AVG", "MIN", "MAX"] | None = Field(
        None, description="Aggregate function to apply (COUNT, SUM, AVG, MIN, MAX)"
    )
```

The `Literal` import already exists at line 11.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ir_models.py::TestFieldExprAggregates -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Run existing FieldExpr tests for regressions**

Run: `.venv/bin/pytest tests/test_ir_models.py -v`
Expected: Existing tests still pass (function defaults to None)

- [ ] **Step 6: Commit**

```bash
git add src/ir/models.py tests/test_ir_models.py
git commit -m "feat: add optional function field to FieldExpr for aggregates"
```

---

### Task 2: Validator Aggregate Handling

**Files:**
- Modify: `src/ir/validator.py:99-127`

- [ ] **Step 1: Write failing tests**

The existing `tests/test_ir_validator.py` has an import error (tries to import `TableNotFoundError` which doesn't exist). Create a focused test file for aggregate validation instead.

```python
# tests/test_aggregate_validation.py
from src.ir.models import QueryIR, TableSource, FieldExpr
from src.ir.validator import IRValidator


class TestAggregateValidation:
    def setup_method(self):
        self.schema = {
            "users": {
                "columns": {
                    "id": {"type": "int"},
                    "name": {"type": "str"},
                    "age": {"type": "int"},
                }
            },
            "orders": {
                "columns": {
                    "id": {"type": "int"},
                    "total": {"type": "float"},
                    "user_id": {"type": "int"},
                }
            },
        }
        self.validator = IRValidator(self.schema)

    def test_count_star_passes_validation(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*", function="COUNT", alias="total")],
        )
        errors = self.validator.validate_query(query_ir)
        assert errors == []

    def test_sum_valid_column_passes(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[FieldExpr(field="total", function="SUM", alias="revenue")],
        )
        errors = self.validator.validate_query(query_ir)
        assert errors == []

    def test_avg_valid_column_passes(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="age", function="AVG")],
        )
        errors = self.validator.validate_query(query_ir)
        assert errors == []

    def test_min_max_valid_column_passes(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[
                FieldExpr(field="total", function="MIN"),
                FieldExpr(field="total", function="MAX"),
            ],
        )
        errors = self.validator.validate_query(query_ir)
        assert errors == []

    def test_aggregate_invalid_column_fails(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="nonexistent", function="SUM")],
        )
        errors = self.validator.validate_query(query_ir)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_sum_star_fails(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*", function="SUM")],
        )
        errors = self.validator.validate_query(query_ir)
        assert len(errors) == 1
        assert "COUNT" in errors[0]

    def test_avg_star_fails(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*", function="AVG")],
        )
        errors = self.validator.validate_query(query_ir)
        assert len(errors) == 1

    def test_plain_field_still_validated(self):
        """Existing behavior: plain fields without function are validated."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="nonexistent")],
        )
        errors = self.validator.validate_query(query_ir)
        assert len(errors) == 1
        assert "nonexistent" in errors[0]

    def test_mixed_aggregate_and_plain_fields(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="*", function="COUNT", alias="total"),
                FieldExpr(field="name"),
            ],
        )
        errors = self.validator.validate_query(query_ir)
        assert errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_aggregate_validation.py -v`
Expected: `test_count_star_passes_validation` FAILS (validator rejects `*` with function, or rejects `COUNT(*)` as column name)

- [ ] **Step 3: Update _validate_fields in validator**

In `src/ir/validator.py`, replace the `_validate_fields` method (lines 99-127) with:

```python
    def _validate_fields(self, fields: List[Any], source_table: str) -> List[str]:
        """Validate SELECT field references."""
        errors = []
        table_schema = self.schema.get(source_table, {})
        available_columns = set(table_schema.get("columns", {}).keys())
        
        for field in fields:
            # Handle aggregate functions
            if getattr(field, "function", None) is not None:
                if field.field == "*":
                    # Only COUNT supports *
                    if field.function != "COUNT":
                        error_msg = f"Only COUNT supports *, not {field.function}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                    continue  # COUNT(*) is always valid, skip column check

            if field.field == "*":
                continue  # Wildcard is always valid
            
            # Determine which table to check against
            target_table = field.table or source_table
            
            if target_table not in self.tables:
                error_msg = f"Field '{field.field}' references unknown table '{target_table}'"
                errors.append(error_msg)
                logger.error(error_msg)
                continue
            
            # Check if column exists in the specified table
            target_schema = self.schema.get(target_table, {})
            target_columns = set(target_schema.get("columns", {}).keys())
            
            if field.field not in target_columns:
                error_msg = f"Column '{field.field}' does not exist in table '{target_table}'. Available: {', '.join(sorted(target_columns))}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_aggregate_validation.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ir/validator.py tests/test_aggregate_validation.py
git commit -m "feat: validator handles aggregate functions in field validation"
```

---

### Task 3: SQL Builder Aggregate Output

**Files:**
- Modify: `src/query/postgresql.py:140-167`
- Modify: `tests/test_postgresql_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/test_postgresql_builder.py

class TestPostgreSQLAggregates:
    def test_count_star(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*", function="COUNT", alias="total")],
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert 'SELECT COUNT(*) AS "total"' in result.query["sql"]

    def test_count_star_no_alias(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*", function="COUNT")],
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert "SELECT COUNT(*)" in result.query["sql"]
        assert "AS" not in result.query["sql"]

    def test_sum_column(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[FieldExpr(field="total", function="SUM", alias="revenue")],
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert 'SELECT SUM("total") AS "revenue"' in result.query["sql"]

    def test_sum_qualified_column(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[FieldExpr(field="total", function="SUM", table="orders")],
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert 'SELECT SUM("orders"."total")' in result.query["sql"]

    def test_avg_column(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="age", function="AVG", alias="avg_age")],
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert 'SELECT AVG("age") AS "avg_age"' in result.query["sql"]

    def test_min_column(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[FieldExpr(field="total", function="MIN")],
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert 'SELECT MIN("total")' in result.query["sql"]

    def test_max_column(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[FieldExpr(field="total", function="MAX")],
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert 'SELECT MAX("total")' in result.query["sql"]

    def test_mixed_aggregate_and_plain(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="*", function="COUNT", alias="total"),
                FieldExpr(field="name"),
            ],
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert 'SELECT COUNT(*) AS "total", "name"' in result.query["sql"]

    def test_aggregate_with_filter(self):
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*", function="COUNT", alias="active_count")],
            filters=ConditionExpr(field="status", op="=", value="active"),
        )
        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)
        assert 'COUNT(*) AS "active_count"' in result.query["sql"]
        assert 'WHERE "status" = $1' in result.query["sql"]
        assert result.query["params"] == ["active"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_postgresql_builder.py::TestPostgreSQLAggregates -v`
Expected: FAIL — visit_field doesn't handle function field

- [ ] **Step 3: Update visit_field in PostgreSQLBuilder**

In `src/query/postgresql.py`, replace the `visit_field` method (lines 140-167) with:

```python
    def visit_field(self, field: FieldExpr) -> str:
        """Visit a field expression.

        Handles regular fields, wildcards, and aggregate functions.

        Args:
            field: Field expression to visit

        Returns:
            Field SQL fragment
        """
        # Aggregate function
        if getattr(field, "function", None) is not None:
            if field.field == "*":
                inner = "*"
            elif field.table:
                inner = self._quote_qualified(field.table, field.field)
            else:
                inner = self._quote_identifier(field.field)

            result = f"{field.function}({inner})"

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

        # Add alias if present
        if field.alias:
            result += f" AS {self._quote_identifier(field.alias)}"

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_postgresql_builder.py -v`
Expected: All tests PASS (new + existing)

- [ ] **Step 5: Commit**

```bash
git add src/query/postgresql.py tests/test_postgresql_builder.py
git commit -m "feat: SQL builder emits aggregate function calls"
```

---

### Task 4: LLM System Prompt Update

**Files:**
- Modify: `src/llm/nl_to_ir.py:81-182`

- [ ] **Step 1: Update the system prompt**

In `src/llm/nl_to_ir.py`, in the `_build_system_prompt` method, update the `fields` documentation section (around line 99) to include the function field:

Replace:
```python
3. "fields": List of columns to retrieve
   [{{"field": "column_name", "table": "table_name", "alias": "optional_alias"}}]
   - Use "table" when joining multiple tables
   - Use "alias" to rename output columns
```

With:
```python
3. "fields": List of columns to retrieve
   [{{"field": "column_name", "table": "table_name", "alias": "optional_alias", "function": "optional_aggregate"}}]
   - Use "table" when joining multiple tables
   - Use "alias" to rename output columns
   - Use "function" for aggregates: "COUNT", "SUM", "AVG", "MIN", "MAX"
   - COUNT can use "*" as the field (e.g., {{"field": "*", "function": "COUNT"}})
   - SUM, AVG, MIN, MAX require a specific column name
```

Add a new example after the existing examples (before the IMPORTANT RULES section, around line 171):

```python
Query: "How many artists are there?"
{{
  "operation": "SELECT",
  "source": {{"table": "Artist"}},
  "fields": [
    {{"field": "*", "function": "COUNT", "alias": "artist_count"}}
  ]
}}
```

- [ ] **Step 2: Verify the prompt renders correctly**

Run: `.venv/bin/python3 -c "from src.llm.nl_to_ir import NaturalLanguageToIR; from src.schema.schema import DatabaseSchema, TableDef, ColumnDef; schema = DatabaseSchema(tables=[TableDef(name='test', columns=[ColumnDef(name='id', type='int')])]); nlr = NaturalLanguageToIR(api_key='test'); print(nlr._build_system_prompt(schema)[:500])"`

Expected: Prompt renders without errors, shows the aggregate documentation.

- [ ] **Step 3: Commit**

```bash
git add src/llm/nl_to_ir.py
git commit -m "feat: update LLM system prompt with aggregate function documentation"
```

---

### Task 5: End-to-End Verification

**Files:**
- No new files

- [ ] **Step 1: Run all aggregate-related tests**

Run: `.venv/bin/pytest tests/test_ir_models.py::TestFieldExprAggregates tests/test_aggregate_validation.py tests/test_postgresql_builder.py::TestPostgreSQLAggregates -v`
Expected: All tests PASS

- [ ] **Step 2: Run full test suite for regressions**

Run: `.venv/bin/pytest tests/ --ignore=tests/test_ir_validator.py -v --tb=short`
Expected: Same pre-existing failures only. No new failures.

- [ ] **Step 3: Commit plan**

```bash
git add docs/superpowers/plans/2026-04-03-aggregate-functions.md
git commit -m "docs: add aggregate functions implementation plan"
```
