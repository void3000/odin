# Result Summarizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an LLM-powered Stage 5 to the query pipeline that summarizes database results into natural language, replacing raw row data.

**Architecture:** A new `ResultSummarizer` class in `src/summarizer.py` takes the original question, SQL, and result rows, then calls the existing `LLMClient.generate()` to produce a natural language summary. The orchestrator calls it after Stage 4 (execute) and returns the summary string instead of raw rows.

**Tech Stack:** Python, OpenAI-compatible API via existing `LLMClient`, pytest for tests.

**Spec:** `docs/superpowers/specs/2026-03-30-result-summarizer-design.md`

---

### Task 1: Create `ResultSummarizer` with tests

**Files:**
- Create: `src/summarizer.py`
- Create: `tests/test_summarizer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_summarizer.py`:

```python
"""Tests for ResultSummarizer."""

import pytest
from unittest.mock import MagicMock
from src.summarizer import ResultSummarizer


class TestResultSummarizer:
    """Tests for ResultSummarizer."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_llm = MagicMock()
        self.summarizer = ResultSummarizer(self.mock_llm)

    def test_summarize_success(self):
        """Summarizer returns LLM-generated summary."""
        self.mock_llm.generate.return_value = (True, "There are 2 users: Alice and Bob.")

        success, summary = self.summarizer.summarize(
            question="Show me all users",
            results=[{"name": "Alice"}, {"name": "Bob"}],
            sql="SELECT name FROM users"
        )

        assert success is True
        assert summary == "There are 2 users: Alice and Bob."
        self.mock_llm.generate.assert_called_once()

    def test_summarize_empty_results(self):
        """Summarizer handles empty result sets via LLM."""
        self.mock_llm.generate.return_value = (True, "No users were found in the database.")

        success, summary = self.summarizer.summarize(
            question="Show me all users",
            results=[],
            sql="SELECT name FROM users"
        )

        assert success is True
        assert summary == "No users were found in the database."
        self.mock_llm.generate.assert_called_once()

    def test_summarize_llm_failure(self):
        """Summarizer propagates LLM errors."""
        self.mock_llm.generate.return_value = (False, "API rate limit exceeded")

        success, summary = self.summarizer.summarize(
            question="Show me all users",
            results=[{"name": "Alice"}],
            sql="SELECT name FROM users"
        )

        assert success is False
        assert summary == "API rate limit exceeded"

    def test_prompt_contains_question_and_results(self):
        """Summarizer prompt includes the original question and result data."""
        self.mock_llm.generate.return_value = (True, "Summary.")

        self.summarizer.summarize(
            question="How many orders?",
            results=[{"count": 42}],
            sql="SELECT COUNT(*) as count FROM orders"
        )

        call_args = self.mock_llm.generate.call_args
        system_prompt = call_args[0][0] if call_args[0] else call_args[1]["system_prompt"]
        user_message = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["user_message"]

        assert "How many orders?" in user_message
        assert "42" in user_message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_summarizer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.summarizer'`

- [ ] **Step 3: Implement `ResultSummarizer`**

Create `src/summarizer.py`:

```python
"""
Result Summarizer.

Uses an LLM to summarize database query results into natural language.
"""

import json
import logging
from typing import Any, List, Tuple

from src.logging_config import get_component_logger

logger = get_component_logger("summarizer")

SUMMARIZE_SYSTEM_PROMPT = """You are a data analyst assistant. The user asked a question about a database, \
and a SQL query was executed to answer it. Your job is to summarize the results \
in clear, natural language that directly answers the user's question.

Rules:
- Answer the question directly and concisely.
- If the results are empty, say so in a helpful way related to the question.
- Do not mention SQL, queries, databases, or technical details.
- Do not use markdown formatting.
- Refer to the data naturally, as if you looked it up for the user."""


class ResultSummarizer:
    """Summarizes database query results into natural language using an LLM."""

    def __init__(self, llm_client: Any):
        """
        Initialize summarizer.

        Args:
            llm_client: LLMClient instance for generating summaries.
        """
        self.llm_client = llm_client
        logger.info("ResultSummarizer initialized")

    def summarize(
        self,
        question: str,
        results: List[Any],
        sql: str
    ) -> Tuple[bool, str]:
        """
        Summarize query results into natural language.

        Args:
            question: The original natural language question.
            results: List of result rows (dicts or tuples).
            sql: The SQL query that was executed.

        Returns:
            Tuple of (success, summary_or_error).
        """
        user_message = (
            f"User's question: {question}\n\n"
            f"SQL executed: {sql}\n\n"
            f"Results ({len(results)} rows):\n{json.dumps(results, indent=2, default=str)}"
        )

        logger.debug(f"Summarizing {len(results)} rows for question: {question}")

        success, response = self.llm_client.generate(SUMMARIZE_SYSTEM_PROMPT, user_message)

        if success:
            logger.info("Results summarized successfully")
        else:
            logger.error(f"Summarization failed: {response}")

        return success, response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_summarizer.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/summarizer.py tests/test_summarizer.py
git commit -m "feat: add ResultSummarizer class for LLM-based result summarization"
```

---

### Task 2: Integrate summarizer into orchestrator

**Files:**
- Modify: `src/orchestrator.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_summarizer.py`:

```python
from src.orchestrator import QueryOrchestrator


class TestOrchestratorSummarization:
    """Tests for summarization integration in QueryOrchestrator."""

    def setup_method(self):
        """Set up orchestrator with mocked components."""
        self.mock_llm = MagicMock()
        self.schema = {
            "users": {
                "columns": {"id": {"type": "INTEGER"}, "name": {"type": "TEXT"}},
                "primary_key": "id",
            }
        }

    def test_process_query_returns_summary(self, tmp_path):
        """Successful query returns summary instead of raw data."""
        db_path = str(tmp_path / "test.db")
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice')")
        conn.commit()
        conn.close()

        # First call: IR parsing, Second call: summarization
        self.mock_llm.generate.side_effect = [
            (True, '{"operation": "SELECT", "source": {"table": "users"}, "fields": [{"field": "name"}]}'),
            (True, "There is 1 user: Alice."),
        ]

        orchestrator = QueryOrchestrator(
            db_path=db_path,
            llm_client=self.mock_llm,
            system_prompt="parse",
            schema=self.schema,
        )

        result = orchestrator.process_query("Show me all users")

        assert result["success"] is True
        assert result["summary"] == "There is 1 user: Alice."
        assert "data" not in result

    def test_process_query_summarize_failure(self, tmp_path):
        """Summarization failure returns error with stage."""
        db_path = str(tmp_path / "test.db")
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice')")
        conn.commit()
        conn.close()

        self.mock_llm.generate.side_effect = [
            (True, '{"operation": "SELECT", "source": {"table": "users"}, "fields": [{"field": "name"}]}'),
            (False, "API error"),
        ]

        orchestrator = QueryOrchestrator(
            db_path=db_path,
            llm_client=self.mock_llm,
            system_prompt="parse",
            schema=self.schema,
        )

        result = orchestrator.process_query("Show me all users")

        assert result["success"] is False
        assert result["error"] == "API error"
        assert result["metadata"]["stage"] == "summarize"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_summarizer.py::TestOrchestratorSummarization -v`
Expected: FAIL — `result["summary"]` key missing, `result["data"]` still present.

- [ ] **Step 3: Update `QueryOrchestrator` to use `ResultSummarizer`**

In `src/orchestrator.py`, add the import at the top with the other imports:

```python
from src.summarizer import ResultSummarizer
```

In `__init__`, add after `self.executor`:

```python
self.summarizer = ResultSummarizer(llm_client)
```

Replace the success block at the end of Stage 4 (lines 134-138) with the Stage 5 summarization:

```python
            result["metadata"]["row_count"] = len(exec_result)
            logger.info(f"Stage 4 complete: Query executed successfully, returned {len(exec_result)} rows")

            # Stage 5: Summarize results using LLM
            logger.info("Stage 5: Summarizing results...")
            summ_success, summary = self.summarizer.summarize(
                natural_language, exec_result, sql
            )

            if not summ_success:
                result["error"] = summary
                result["metadata"]["stage"] = "summarize"
                logger.error(f"Summarization failed: {summary}")
                return result

            result["success"] = True
            result["summary"] = summary
            result["metadata"]["stage"] = "complete"
            logger.info("Stage 5 complete: Results summarized successfully")
```

Also remove the old lines that set `result["data"]`:

```python
            # Remove these lines (old Stage 4 success):
            # result["success"] = True
            # result["data"] = exec_result
            # result["metadata"]["row_count"] = len(exec_result)
            # result["metadata"]["stage"] = "complete"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_summarizer.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`
Expected: All tests pass (existing tests should not break since they don't depend on `result["data"]` from the orchestrator).

- [ ] **Step 6: Commit**

```bash
git add src/orchestrator.py tests/test_summarizer.py
git commit -m "feat: integrate ResultSummarizer into query pipeline as Stage 5"
```

---

### Task 3: Update CLI output in `main.py`

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Update `main()` to print summary**

In `src/main.py`, replace the result printing block in `main()` (around line 241) from:

```python
        # Print result
        import json
        print(json.dumps(result, indent=2, default=str))
```

To:

```python
        # Print result
        if result["success"]:
            print(result["summary"])
        else:
            print(f"Error: {result['error']}", file=sys.stderr)
            sys.exit(1)
```

- [ ] **Step 2: Run full test suite**

Run: `pytest -v`
Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/main.py
git commit -m "feat: update CLI to print natural language summary"
```

---

### Task 4: Update orchestrator docstrings and pipeline comment

**Files:**
- Modify: `src/orchestrator.py`

- [ ] **Step 1: Update class docstring**

In `src/orchestrator.py`, update the class docstring pipeline stages to include Stage 5:

```python
    """
    Orchestrates the complete query processing pipeline.

    Pipeline stages:
        1. Parse: Natural language -> IR (using LLM)
        2. Validate: IR against database schema
        3. Build: IR -> SQL query
        4. Execute: SQL -> Results
        5. Summarize: Results -> Natural language summary (using LLM)
    """
```

Also update the module docstring at the top:

```python
"""
Query Orchestrator.

Coordinates the complete query processing pipeline:
1. Parse natural language to IR
2. Validate IR against schema
3. Build SQL from validated IR
4. Execute SQL and return results
5. Summarize results into natural language
"""
```

- [ ] **Step 2: Commit**

```bash
git add src/orchestrator.py
git commit -m "docs: update orchestrator docstrings to reflect Stage 5"
```
