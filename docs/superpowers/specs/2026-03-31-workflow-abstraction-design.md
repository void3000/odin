# Workflow Abstraction Design

Convert each orchestrator pipeline stage into a self-contained, independently runnable `Workflow` class with a shared `PipelineContext`.

## Goals

- Each pipeline stage is a standalone unit that can be instantiated and run independently
- Uniform timing, logging, and error handling across all stages
- The orchestrator becomes a thin runner that chains workflows
- Easy to insert, remove, or reorder steps

## File Layout

```
src/workflows/
    __init__.py        # Public exports
    base.py            # Workflow ABC + PipelineContext
    parse.py           # ParseWorkflow
    validate.py        # ValidateWorkflow
    build.py           # BuildWorkflow
    execute.py         # ExecuteWorkflow
    summarize.py       # SummarizeWorkflow
```

## PipelineContext

A dataclass that accumulates state as it flows through steps. Each workflow reads what it needs and writes its output.

```python
@dataclass
class PipelineContext:
    # Input (set before pipeline starts)
    natural_language: str
    db_path: str
    schema: Dict[str, Any]

    # Stage outputs (set by individual workflows)
    query_ir: Optional[QueryIR] = None
    sql: Optional[str] = None
    params: Optional[List] = None
    rows: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None

    # Metadata
    timings: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    failed_stage: Optional[str] = None
```

## Workflow Base Class

```python
class Workflow(ABC):
    name: str

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Run the workflow with timing and error handling."""
        logger.info(f"Stage: {self.name}...")
        t0 = time.perf_counter()
        try:
            context = self.run(context)
        except Exception as e:
            context.error = str(e)
            context.failed_stage = self.name
        context.timings[f"{self.name}_ms"] = (time.perf_counter() - t0) * 1000
        return context

    @abstractmethod
    def run(self, context: PipelineContext) -> PipelineContext:
        """Subclasses implement this. Mutate context and return it."""
        ...
```

- `execute()` wraps `run()` with timing, logging, and exception-to-error conversion
- On failure, workflows set `context.error` and `context.failed_stage`
- Workflows can set error explicitly in `run()` (preferred) or raise an exception (caught by `execute()`)
- Contract: if `run()` sets `context.error`, it should return immediately without raising

## Individual Workflows

### ParseWorkflow (`parse.py`)

- **Dependencies:** `IRParser` (injected via constructor)
- **Reads:** `context.natural_language`
- **Writes:** `context.query_ir`
- **Error:** Sets `context.error` if LLM fails or JSON is invalid

```python
class ParseWorkflow(Workflow):
    name = "parse"

    def __init__(self, parser: IRParser):
        self.parser = parser

    def run(self, context: PipelineContext) -> PipelineContext:
        result = self.parser.parse(context.natural_language)
        if not result["success"]:
            context.error = result["error"]
            context.failed_stage = self.name
            return context
        context.query_ir = result["data"]
        return context
```

### ValidateWorkflow (`validate.py`)

- **Dependencies:** None (creates `IRValidator` from `context.schema`)
- **Reads:** `context.query_ir`, `context.schema`
- **Writes:** Nothing on success; `context.error` on failure

```python
class ValidateWorkflow(Workflow):
    name = "validate"

    def run(self, context: PipelineContext) -> PipelineContext:
        validator = IRValidator(context.schema)
        errors = validator.validate_query(context.query_ir)
        if errors:
            context.error = "Validation failed:\n" + "\n".join(f"- {e}" for e in errors)
            context.failed_stage = self.name
        return context
```

### BuildWorkflow (`build.py`)

- **Dependencies:** None (creates `SQLBuilder` internally)
- **Reads:** `context.query_ir`
- **Writes:** `context.sql`, `context.params`

```python
class BuildWorkflow(Workflow):
    name = "build"

    def run(self, context: PipelineContext) -> PipelineContext:
        builder = SQLBuilder()
        context.sql, context.params = builder.build(context.query_ir)
        return context
```

### ExecuteWorkflow (`execute.py`)

- **Dependencies:** `db_path` (injected via constructor)
- **Reads:** `context.sql`, `context.params`
- **Writes:** `context.rows`

```python
class ExecuteWorkflow(Workflow):
    name = "execute"

    def __init__(self, db_path: str):
        self.db_path = db_path

    def run(self, context: PipelineContext) -> PipelineContext:
        connector = SQLiteConnector(database=self.db_path)
        try:
            connector.connect()
            raw = connector.execute_query({"sql": context.sql, "params": context.params or []})
            context.rows = [dict(zip(raw.columns, row)) for row in raw.rows]
        except DatabaseError as e:
            context.error = str(e)
            context.failed_stage = self.name
        finally:
            connector.disconnect()
        return context
```

### SummarizeWorkflow (`summarize.py`)

- **Dependencies:** `ResultSummarizer` (injected via constructor)
- **Reads:** `context.natural_language`, `context.rows`, `context.sql`
- **Writes:** `context.summary`

```python
class SummarizeWorkflow(Workflow):
    name = "summarize"

    def __init__(self, summarizer: ResultSummarizer):
        self.summarizer = summarizer

    def run(self, context: PipelineContext) -> PipelineContext:
        success, summary = self.summarizer.summarize(
            context.natural_language, context.rows, context.sql
        )
        if not success:
            context.error = summary
            context.failed_stage = self.name
            return context
        context.summary = summary
        return context
```

## Orchestrator Changes

The orchestrator becomes a thin runner:

```python
class QueryOrchestrator:
    def __init__(self, db_path, llm_client, system_prompt, schema):
        parser = IRParser(llm_client, system_prompt)
        summarizer = ResultSummarizer(llm_client)

        self.steps: List[Workflow] = [
            ParseWorkflow(parser),
            ValidateWorkflow(),
            BuildWorkflow(),
            ExecuteWorkflow(db_path),
            SummarizeWorkflow(summarizer),
        ]
        self.schema = schema
        self.db_path = db_path

    def process_query(self, natural_language: str) -> Dict[str, Any]:
        context = PipelineContext(
            natural_language=natural_language,
            db_path=self.db_path,
            schema=self.schema,
        )
        for step in self.steps:
            context = step.execute(context)
            if context.error:
                break
        context.timings["total_ms"] = sum(context.timings.values())
        return self._to_result_dict(context)

    def _to_result_dict(self, context: PipelineContext) -> Dict[str, Any]:
        """Convert PipelineContext to the existing result dict format for backwards compatibility."""
        result = {
            "success": context.error is None,
            "error": context.error,
            "metadata": {
                "timings": context.timings,
                "stage": context.failed_stage or "complete",
            }
        }
        if context.query_ir:
            result["metadata"]["ir"] = context.query_ir.model_dump()
        if context.sql:
            result["metadata"]["sql"] = context.sql
            result["metadata"]["params"] = context.params
        if context.rows is not None:
            result["metadata"]["row_count"] = len(context.rows)
        if context.summary:
            result["summary"] = context.summary
        return result
```

## Testing Strategy

- Each workflow gets its own unit test file that tests `run()` directly with a crafted `PipelineContext`
- Existing orchestrator tests continue to work since `_to_result_dict` preserves the output format
- Integration test: run full pipeline through orchestrator to verify chaining works

## Migration

- Existing components (`IRParser`, `IRValidator`, `SQLBuilder`, `SQLiteConnector`, `ResultSummarizer`) are unchanged — workflows wrap them
- The orchestrator's public API (`process_query` return format) is preserved via `_to_result_dict`
- `main.py` and `Text2SQL` require no changes
