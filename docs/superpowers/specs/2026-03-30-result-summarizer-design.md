# Result Summarizer Design

## Summary

Add a Stage 5 to the query pipeline where the LLM summarizes database results into a natural language response. Raw rows are replaced by a human-readable summary string.

## Decisions

- **Summary replaces raw data:** The result dict returns `summary` (string) instead of `data` (list of rows). Callers get a natural language answer, not raw rows.
- **Reuse existing LLM client:** The summarizer uses the same `LLMClient` instance already configured on the orchestrator.
- **Zero rows go through the LLM:** Even empty result sets are sent to the summarizer so the LLM can provide a contextual "no results" message.

## New File: `src/summarizer.py`

### Class: `ResultSummarizer`

```python
class ResultSummarizer:
    def __init__(self, llm_client):
        """Takes the existing LLMClient instance."""

    def summarize(self, question: str, results: list, sql: str) -> tuple[bool, str]:
        """
        Summarize query results into natural language.

        Args:
            question: The original natural language question from the user.
            results: List of result rows (dicts or tuples) from the database.
            sql: The generated SQL query, included for LLM context.

        Returns:
            Tuple of (success: bool, summary_or_error: str).
        """
```

**Prompt strategy:** The system prompt instructs the LLM to act as a data analyst answering the user's question based on the provided query results. The user message contains the original question, the SQL executed, and the result rows serialized as JSON.

## Changes to `src/orchestrator.py`

### `__init__`
- Import and instantiate `ResultSummarizer(self.llm_client)`.

### `process_query`
- After Stage 4 (execute), add Stage 5 (summarize):
  - Call `self.summarizer.summarize(natural_language, exec_result, sql)`.
  - On success: set `result["summary"]` to the summary string. Do not set `result["data"]`.
  - On failure: set `result["error"]` with `stage: "summarize"` and `result["success"] = False`.
- Remove `result["data"]` and `result["metadata"]["row_count"]` assignments from Stage 4. The row count moves to metadata set during Stage 5 for reference.

### Result dict shape

```python
# Before
{"success": True, "data": [..rows], "error": None, "metadata": {...}}

# After
{"success": True, "summary": "There are 5 rock albums...", "error": None, "metadata": {...}}
```

`metadata` continues to include `ir`, `sql`, `params`, and `stage`. A new `row_count` key is added in metadata during Stage 5 for observability.

## Changes to `src/main.py`

- Update `Text2SQL.query()` to pass through the new result shape (no code change needed since it returns the orchestrator result directly).
- Update `main()` CLI output to print `result["summary"]` instead of the full JSON dump when successful.

## Error Handling

- If the summarization LLM call fails, `result["success"]` is `False`, `result["error"]` contains the error message, and `result["metadata"]["stage"]` is `"summarize"`.
- The raw results are not surfaced to the caller on failure — the error message is returned instead.

## Testing

- Unit test `ResultSummarizer` with a mock LLM client.
- Test the full pipeline through `QueryOrchestrator.process_query()` to verify the summary appears in the result.
- Test zero-row case to verify the LLM is still called.
- Test summarization failure to verify error propagation.
