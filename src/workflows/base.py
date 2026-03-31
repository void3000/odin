"""Workflow base class and PipelineContext for the query pipeline."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.ir.models import QueryIR
from src.logging_config import get_component_logger

logger = get_component_logger("workflow")


@dataclass
class PipelineContext:
    """Shared state that flows through the pipeline."""

    # Input (set before pipeline starts)
    natural_language: str
    db_path: str
    schema: Dict[str, Any]

    # Stage outputs
    query_ir: Optional[QueryIR] = None
    sql: Optional[str] = None
    params: Optional[List] = None
    rows: Optional[List[Dict[str, Any]]] = None
    summary: Optional[str] = None

    # Metadata
    timings: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None
    failed_stage: Optional[str] = None


class Workflow(ABC):
    """Abstract base class for pipeline workflow steps."""

    name: str

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if ABC not in cls.__bases__ and not hasattr(cls, "name"):
            raise TypeError(f"{cls.__name__} must define a class attribute 'name'")

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
        """Subclasses implement this. Set context fields and return context."""
        ...
