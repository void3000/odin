# Odin Documentation

Complete documentation for the Odin LLM-to-SQL pipeline.

## Documentation Index

### Getting Started

1. **[Project README](../README.md)** - Start here
   - Installation instructions
   - Quick start guide
   - Basic usage examples
   - Project overview

### IR (Intermediate Representation)

2. **[IR Quick Reference](IR_QUICK_REFERENCE.md)** - Reference guide
   - Common patterns and examples
   - Operator reference table
   - Python usage snippets
   - Quick lookup for syntax

3. **[IR Grammar Specification](IR_GRAMMAR.md)** - Formal specification
   - Complete formal grammar
   - Type system details
   - Validation rules
   - Error handling
   - Future extensions

### Architecture & Design

4. **[Design Document](DESIGN.md)** - Complete architecture
   - System architecture
   - Component descriptions
   - Implementation guidelines
   - Security considerations
   - Development roadmap

## Documentation Structure

```
docs/
├── README.md                  # This file - documentation index
├── IR_QUICK_REFERENCE.md      # Quick syntax reference
├── IR_GRAMMAR.md              # Formal grammar specification
└── DESIGN.md                  # Architecture and design

examples/
├── README.md                  # Examples documentation
├── simple_query.json          # Basic query example
├── join_with_filters.json     # JOIN example
├── nested_conditions.json     # Complex filters
├── with_limit.json            # Sorting and pagination
└── validate_examples.py       # Validation demo script

tests/
├── test_ir_models.py          # IR model tests (32 tests)
├── test_ir_validator.py       # Validator tests (25 tests)
├── test_schema.py             # Schema tests (17 tests)
└── conftest.py                # Shared test fixtures
```

## Reading Guide

### For New Users

1. Start with [Project README](../README.md) for installation and quick start
2. Review [IR Quick Reference](IR_QUICK_REFERENCE.md) for common patterns
3. Explore [examples/](../examples/) directory for working code
4. Run `pytest tests/ -v` to see comprehensive usage

### For Developers

1. Read [Design Document](DESIGN.md) for architecture understanding
2. Study [IR Grammar Specification](IR_GRAMMAR.md) for formal rules
3. Review [test files](../tests/) for implementation examples
4. Check the roadmap in [DESIGN.md](DESIGN.md) for future work

### For LLM Integration

1. Study [IR Grammar Specification](IR_GRAMMAR.md) for output format
2. Review [examples/](../examples/) for training data patterns
3. Use [IR Quick Reference](IR_QUICK_REFERENCE.md) for prompt engineering
4. Implement validation early using `IRValidator`

### For Contributing

1. Read [Design Document](DESIGN.md) for project philosophy
2. Review existing [test coverage](../tests/)
3. Check implementation guidelines in [DESIGN.md](DESIGN.md)
4. See contribution areas in [README.md](../README.md)

## Key Concepts

### Intermediate Representation (IR)

The IR is a structured JSON format that sits between natural language and SQL:

- **Predictable:** Strictly defined schema
- **Validatable:** Two-layer validation (structure + semantics)
- **Type-safe:** Pydantic models enforce correctness
- **Debuggable:** Human-readable, inspectable format

### Validation Layers

1. **Pydantic (Structure):** Ensures JSON conforms to IR schema
2. **IRValidator (Semantics):** Checks table/field existence and types
3. **SQLBuilder (Safety):** Generates parameterized SQL safely

### Security Model

- LLM outputs IR, never SQL
- IR validated before SQL generation
- Table/field names whitelisted against schema
- Values parameterized in final SQL
- No dynamic SQL construction from untrusted input

## Examples Summary

| Example | Description | Features Demonstrated |
|---------|-------------|----------------------|
| [simple_query.json](../examples/simple_query.json) | Basic SELECT | Field selection, simple filter |
| [join_with_filters.json](../examples/join_with_filters.json) | Multi-table query | INNER JOIN, AND conditions, ORDER BY |
| [nested_conditions.json](../examples/nested_conditions.json) | Complex logic | OR with nested AND, field aliases |
| [with_limit.json](../examples/with_limit.json) | Pagination | IN operator, sorting, LIMIT |

Run validation: `python examples/validate_examples.py`

## API Reference

### Core Classes

```python
# IR Models
from src.ir.models import (
    QueryIR,           # Root query structure
    TableSource,       # Table reference
    FieldExpr,         # Field selection
    JoinExpr,          # JOIN operation
    ConditionExpr,     # Leaf filter condition
    LogicalExpr,       # AND/OR combination
    OrderExpr,         # Sort specification
)

# Validation
from src.ir.validator import IRValidator

# Schema
from src.schema import (
    DatabaseSchema,    # Complete database schema
    TableDef,          # Table definition
    ColumnDef,         # Column definition
)
```

### Common Operations

```python
# Create IR from JSON
import json
from src.ir.models import QueryIR

with open('query.json') as f:
    query = QueryIR(**json.load(f))

# Validate IR
from src.ir.validator import IRValidator

schema = {"users": {"id": "int", "name": "str"}}
validator = IRValidator(schema)
validator.validate(query)

# Export IR to JSON
json_str = query.model_dump_json(indent=2)
```

## Testing

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test Suite

```bash
pytest tests/test_ir_models.py -v
pytest tests/test_ir_validator.py -v
pytest tests/test_schema.py -v
```

### Test Coverage

```bash
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

### Current Status

- 74 tests total
- 100% passing
- Coverage: IR models, validator, schema

## Additional Resources

### Related Technologies

- [Pydantic](https://docs.pydantic.dev/) - Data validation library
- [pytest](https://docs.pytest.org/) - Testing framework
- [SQL Standards](https://www.iso.org/standard/63555.html) - SQL specification

### Security Resources

- [OWASP SQL Injection](https://owasp.org/www-community/attacks/SQL_Injection)
- [Parameterized Queries](https://cheatsheetseries.owasp.org/cheatsheets/Query_Parameterization_Cheat_Sheet.html)

## Feedback & Support

- File issues on GitHub
- Review test files for usage patterns
- Check examples directory for working code
- Read design document for architectural decisions

## Version History

### v0.1.0 (Current)

- IR models with Pydantic
- Semantic validator
- Schema definition system
- Comprehensive test suite (74 tests)
- Example IR files
- Complete documentation
