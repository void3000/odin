"""ValidateWorkflow — validates QueryIR against database schema."""

from src.ir.validator import IRValidator
from src.workflows.base import Workflow, PipelineContext


class ValidateWorkflow(Workflow):
    name = "validate"

    def run(self, context: PipelineContext) -> PipelineContext:
        validator = IRValidator(context.schema)
        errors = validator.validate_query(context.query_ir)
        if errors:
            context.error = "Validation failed:\n" + "\n".join(f"- {e}" for e in errors)
            context.failed_stage = self.name
        return context
