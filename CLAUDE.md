# Odin - LLM-to-SQL Pipeline

## Project Overview

Natural language to SQL conversion pipeline using local LLMs (LM Studio) with multi-database support (PostgreSQL, MongoDB, SQLite). Uses a Pydantic-based Intermediate Representation (IR) as the bridge between natural language and database queries.

## Quick Reference

- **Language**: Python 3.13
- **Framework**: FastAPI + LangGraph
- **Package manager**: pip with setuptools (`pyproject.toml`)
- **Virtual env**: `.venv` (always use `.venv`, never `venv`)

## Common Commands

```bash
# Install
pip install -e .
pip install -e ".[dev]"           # dev dependencies (pytest)
pip install -e ".[postgresql]"    # PostgreSQL support

# Run tests
pytest                            # all tests (~261 collected)
pytest tests/test_server.py       # single file
pytest --cov=src                  # with coverage

# Run server
ODIN_LOG_LEVEL=INFO python -m src.server \
  --db postgresql://user:pass@localhost:5432/dbname \
  --llm-model <model-name> \
  --temperature 0.1
```

## Architecture

```
Natural Language → LangGraph Router → (query|chat)
                                         ↓
                          LLM (NL→IR) → Pydantic IR → Query Builder → Executor → DB
```

**Key layers** (each is independent):
- `src/ir/` — IR models (`QueryIR`, `FieldExpr`, `ConditionExpr`, etc.) and validation
- `src/query/` — Query builders: IR → SQL/MongoDB (PostgreSQL, MongoDB, SQLite)
- `src/executor/` — Bridge pattern: `QueryExecutor` + `DatabaseConnector` protocol + connectors
- `src/schema/` — Schema models and extraction from live databases
- `src/llm/` — LLM integration (`nl_to_ir.py`)
- `src/graph.py` — LangGraph intent routing (router → query/chat nodes)
- `src/server.py` — FastAPI server with session middleware
- `src/workflows/` — Workflow steps (parse, validate, build, execute, summarize)

## Code Conventions

- **Type safety**: Pydantic models for all data structures and validation
- **Error handling**: Typed exception hierarchy (`DatabaseError` → `ConnectionError`, `QueryError`, `TransactionError`)
- **Parameterized queries**: Always use parameterized queries, never string interpolation for SQL
- **Bridge pattern**: Executor ↔ Connector separation for database abstraction
- **Logging**: Use `get_component_logger("name")` from `src/logging_config.py`
- **Testing**: Tests live in `tests/`, fixtures in `tests/conftest.py`

## Commit Style

Conventional commits: `type: description` (lowercase, no period)
- Types used: `feat`, `fix`, `refactor`, `docs`
