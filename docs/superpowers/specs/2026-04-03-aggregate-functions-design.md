# Aggregate Functions Support

## Problem

The IR grammar only supports simple column references in `FieldExpr`. When the LLM generates IR with aggregate functions like `COUNT(*)` or `SUM(total)`, the validator rejects them because it checks the `field` value against actual column names. Users cannot ask analytical questions like "how many users are there?" or "what is the total revenue?".

## Goal

Add support for aggregate functions (COUNT, SUM, AVG, MIN, MAX) to the IR, validator, and SQL builder. No GROUP BY or HAVING — those are a separate future phase. Existing queries without aggregates must continue working unchanged.

## Scope

- **In scope:** COUNT, SUM, AVG, MIN, MAX as optional decorators on `FieldExpr`
- **Out of scope:** GROUP BY, HAVING, DISTINCT, nested aggregates, expressions like `COUNT(DISTINCT field)`

## IR Model Change

Add an optional `function` field to `FieldExpr` in `src/ir/models.py`:

```python
class FieldExpr(BaseModel):
    field: str
    table: str | None = None
    alias: str | None = None
    function: Literal["COUNT", "SUM", "AVG", "MIN", "MAX"] | None = None
```

### IR Examples

**Count all rows:**
```json
{"field": "*", "function": "COUNT", "alias": "total_count"}
```

**Sum a column:**
```json
{"field": "total", "function": "SUM", "table": "orders", "alias": "total_sum"}
```

**Average with no alias:**
```json
{"field": "age", "function": "AVG"}
```

**Plain column (unchanged):**
```json
{"field": "name"}
```

### Validation Rules

- `function` is optional. When absent, `FieldExpr` behaves exactly as today.
- Only `COUNT` may use `*` as the field value. `SUM(*)`, `AVG(*)`, etc. are invalid.
- When `function` is set and `field` is `*`, skip column existence validation.
- When `function` is set and `field` is not `*`, validate that the column exists in the schema as normal.

## Validator Changes

In `IRValidator._validate_fields` (`src/ir/validator.py`):

- If `field.function` is not None and `field.field == "*"`:
  - If `field.function != "COUNT"`: error — only COUNT supports `*`.
  - Otherwise: skip column validation (COUNT(*) is always valid).
- If `field.function` is not None and `field.field != "*"`:
  - Validate the column exists as normal.
- If `field.function` is None:
  - Existing behavior unchanged.

## SQL Builder Changes

In the PostgreSQL builder's `visit_field` method (`src/query/postgresql.py`):

- If `field.function` is set:
  - If `field.field == "*"`: emit `COUNT(*)`
  - If `field.table` is set: emit `FUNCTION("table"."column")`
  - Else: emit `FUNCTION("column")`
  - If `field.alias` is set: append ` AS "alias"`
- If `field.function` is not set:
  - Existing behavior unchanged.

### Generated SQL Examples

| IR | SQL |
|----|-----|
| `{"field": "*", "function": "COUNT", "alias": "total"}` | `COUNT(*) AS "total"` |
| `{"field": "total", "function": "SUM", "table": "orders"}` | `SUM("orders"."total")` |
| `{"field": "age", "function": "AVG", "alias": "avg_age"}` | `AVG("age") AS "avg_age"` |
| `{"field": "price", "function": "MIN"}` | `MIN("price")` |
| `{"field": "price", "function": "MAX"}` | `MAX("price")` |

## LLM System Prompt Changes

Update the IR format specification in `src/llm/nl_to_ir.py` (`_build_system_prompt`):

- Document the optional `function` field on `FieldExpr` with the five supported values.
- Add an example: "How many artists are there?" producing `{"field": "*", "function": "COUNT", "alias": "artist_count"}`.
- Note that only COUNT supports `*` as the field.

## File Changes

| File | Action | Responsibility |
|------|--------|---------------|
| `src/ir/models.py` | Modify | Add optional `function` field to `FieldExpr` |
| `src/ir/validator.py` | Modify | Handle aggregates in `_validate_fields` |
| `src/query/postgresql.py` | Modify | Emit `FUNCTION(column)` in `visit_field` |
| `src/llm/nl_to_ir.py` | Modify | Update system prompt with aggregate documentation |
| `tests/test_ir_models.py` | Modify | Test `FieldExpr` with function field |
| `tests/test_ir_validator.py` | Modify | Test aggregate validation rules |
| `tests/test_postgresql_builder.py` | Modify | Test aggregate SQL generation |

## What Doesn't Change

- `QueryIR` structure — no new top-level fields
- Existing queries without `function` work identically
- JOIN, filter, ORDER BY logic unchanged
- Session management, LangGraph routing, orchestrator pipeline
- No GROUP BY or HAVING support (future phase)
