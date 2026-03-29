"""Tests for IR validator."""

import pytest

from src.ir.models import (
    QueryIR,
    TableSource,
    FieldExpr,
    JoinExpr,
    ConditionExpr,
    LogicalExpr,
    OrderExpr,
)
from src.ir.validator import (
    IRValidator,
    ValidationError,
    TableNotFoundError,
    FieldNotFoundError,
    TypeMismatchError,
)


class TestIRValidator:
    """Tests for IRValidator."""

    def test_validate_simple_query(self, sample_schema_dict):
        """Test validating a simple query."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")]
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_invalid_table(self, sample_schema_dict):
        """Test validation fails for non-existent table."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="nonexistent"),
            fields=[FieldExpr(field="*")]
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(TableNotFoundError, match="nonexistent"):
            validator.validate(query)

    def test_invalid_field(self, sample_schema_dict):
        """Test validation fails for non-existent field."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="nonexistent_field")]
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(FieldNotFoundError, match="nonexistent_field"):
            validator.validate(query)

    def test_valid_field_with_table_qualifier(self, sample_schema_dict):
        """Test validation passes for qualified field."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="email", table="users")]
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_field_in_wrong_table(self, sample_schema_dict):
        """Test validation fails when field doesn't exist in specified table."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="total", table="users")]  # total is in orders, not users
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(FieldNotFoundError, match="total.*users"):
            validator.validate(query)

    def test_validate_join(self, sample_schema_dict):
        """Test validating a query with join."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="name", table="users"),
                FieldExpr(field="total", table="orders"),
            ],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="orders",
                    on=ConditionExpr(
                        field="id",
                        table="users",
                        op="=",
                        value={"field": "user_id", "table": "orders"}
                    )
                )
            ]
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_join_with_invalid_table(self, sample_schema_dict):
        """Test validation fails for join with non-existent table."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="nonexistent",
                    on=ConditionExpr(field="id", op="=", value=1)
                )
            ]
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(TableNotFoundError, match="nonexistent"):
            validator.validate(query)

    def test_validate_filter_condition(self, sample_schema_dict):
        """Test validating filter conditions."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="active")
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_filter_with_invalid_field(self, sample_schema_dict):
        """Test validation fails for filter on non-existent field."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="nonexistent", op="=", value="foo")
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(FieldNotFoundError, match="nonexistent"):
            validator.validate(query)

    def test_validate_logical_filter(self, sample_schema_dict):
        """Test validating logical filter expressions."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=LogicalExpr(
                logic="AND",
                conditions=[
                    ConditionExpr(field="status", op="=", value="active"),
                    ConditionExpr(field="age", op=">=", value=18)
                ]
            )
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_validate_nested_logical_filter(self, sample_schema_dict):
        """Test validating nested logical expressions."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=LogicalExpr(
                logic="OR",
                conditions=[
                    ConditionExpr(field="tier", op="=", value="VIP"),
                    LogicalExpr(
                        logic="AND",
                        conditions=[
                            ConditionExpr(field="status", op="=", value="active"),
                            ConditionExpr(field="age", op=">=", value=18)
                        ]
                    )
                ]
            )
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_validate_order_by(self, sample_schema_dict):
        """Test validating ORDER BY clause."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=[OrderExpr(field="name", direction="ASC")]
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_order_by_invalid_field(self, sample_schema_dict):
        """Test validation fails for ORDER BY on non-existent field."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=[OrderExpr(field="nonexistent", direction="ASC")]
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(FieldNotFoundError, match="nonexistent"):
            validator.validate(query)


class TestOperatorTypeValidation:
    """Tests for operator type validation."""

    def test_like_operator_requires_string_field(self, sample_schema_dict):
        """Test LIKE operator requires string field."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="age", op="LIKE", value="%18%")  # age is int
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(TypeMismatchError, match="LIKE.*string"):
            validator.validate(query)

    def test_like_operator_with_string_field(self, sample_schema_dict):
        """Test LIKE operator works with string field."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="email", op="LIKE", value="%@example.com")
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_like_operator_requires_string_value(self, sample_schema_dict):
        """Test LIKE operator requires string value."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="name", op="LIKE", value=123)  # numeric value
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(TypeMismatchError, match="string value"):
            validator.validate(query)

    def test_comparison_operator_requires_numeric_field(self, sample_schema_dict):
        """Test comparison operators require numeric fields."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="name", op=">", value=100)  # name is string
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(TypeMismatchError, match="numeric field"):
            validator.validate(query)

    def test_comparison_operator_with_numeric_field(self, sample_schema_dict):
        """Test comparison operators work with numeric fields."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="age", op=">=", value=18)
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_in_operator_with_integer_field(self, sample_schema_dict):
        """Test IN operator with integer field and values."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="age", op="IN", value=[18, 21, 25])
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_in_operator_type_mismatch(self, sample_schema_dict):
        """Test IN operator rejects type mismatched values."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="age", op="IN", value=["18", "21"])  # strings for int field
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(TypeMismatchError, match="integer values"):
            validator.validate(query)


class TestComplexQueries:
    """Tests for complex query validation."""

    def test_complex_query_from_design_doc(self, sample_schema_dict):
        """Test validating the complex query from DESIGN.md."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="name", table="users"),
                FieldExpr(field="total", table="orders"),
                FieldExpr(field="created_at", table="orders", alias="order_date")
            ],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="orders",
                    on=ConditionExpr(
                        field="id",
                        table="users",
                        op="=",
                        value={"field": "user_id", "table": "orders"}
                    )
                )
            ],
            filters=LogicalExpr(
                logic="AND",
                conditions=[
                    ConditionExpr(field="tier", table="users", op="=", value="premium"),
                    ConditionExpr(field="total", table="orders", op=">", value=100)
                ]
            ),
            order_by=[
                OrderExpr(field="created_at", table="orders", direction="DESC")
            ]
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_multi_table_query_with_unqualified_fields(self, sample_schema_dict):
        """Test query with joins can use unqualified fields if unambiguous."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="id", table="users"),
                FieldExpr(field="name"),  # Only exists in users
            ],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="orders",
                    on=ConditionExpr(
                        field="id",
                        table="users",
                        op="=",
                        value={"field": "user_id", "table": "orders"}
                    )
                )
            ]
        )
        validator = IRValidator(sample_schema_dict)
        validator.validate(query)  # Should not raise

    def test_field_reference_from_unavailable_table(self, sample_schema_dict):
        """Test validation fails when referencing field from table not in query."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="name", table="users"),
                FieldExpr(field="price", table="products")  # products not joined
            ]
        )
        validator = IRValidator(sample_schema_dict)
        with pytest.raises(ValidationError, match="products.*not available"):
            validator.validate(query)
