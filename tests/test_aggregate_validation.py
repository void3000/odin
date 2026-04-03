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
