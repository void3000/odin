from unittest.mock import MagicMock
from src.workflows.base import PipelineContext
from src.workflows.build import BuildWorkflow
from src.ir.models import QueryIR, TableSource, FieldExpr


class TestBuildWorkflow:
    def test_uses_source_build_query(self):
        mock_source = MagicMock()
        mock_native = MagicMock()
        mock_native.sql = "SELECT * FROM users LIMIT 10;"
        mock_native.params = []
        mock_source.build_query.return_value = mock_native

        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10,
        )

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.query_ir = ir

        workflow = BuildWorkflow(default_limit=100)
        result = workflow.run(context)

        mock_source.build_query.assert_called_once_with(ir)
        assert result.native_query is not None
        assert result.sql == "SELECT * FROM users LIMIT 10;"
        assert result.error is None

    def test_applies_default_limit(self):
        mock_source = MagicMock()
        mock_native = MagicMock()
        mock_native.sql = "SELECT *"
        mock_native.params = []
        mock_source.build_query.return_value = mock_native

        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
        )

        context = PipelineContext(
            natural_language="show users",
            source=mock_source,
            schema={},
        )
        context.query_ir = ir

        workflow = BuildWorkflow(default_limit=50)
        workflow.run(context)

        assert ir.limit == 50
