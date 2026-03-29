"""Tests for IR Pydantic models."""

import pytest
from pydantic import ValidationError

from src.ir.models import (
    QueryIR,
    TableSource,
    FieldExpr,
    JoinExpr,
    ConditionExpr,
    LogicalExpr,
    OrderExpr,
)


class TestTableSource:
    """Tests for TableSource model."""

    def test_valid_table_source(self):
        """Test creating a valid TableSource."""
        ts = TableSource(table="users")
        assert ts.table == "users"

    def test_empty_table_name(self):
        """Test that empty table name is rejected."""
        with pytest.raises(ValidationError):
            TableSource(table="")


class TestFieldExpr:
    """Tests for FieldExpr model."""

    def test_simple_field(self):
        """Test simple field without table or alias."""
        field = FieldExpr(field="name")
        assert field.field == "name"
        assert field.table is None
        assert field.alias is None

    def test_field_with_table(self):
        """Test field with table qualifier."""
        field = FieldExpr(field="email", table="users")
        assert field.field == "email"
        assert field.table == "users"

    def test_field_with_alias(self):
        """Test field with alias."""
        field = FieldExpr(field="total_price", alias="price")
        assert field.field == "total_price"
        assert field.alias == "price"

    def test_wildcard_field(self):
        """Test wildcard field."""
        field = FieldExpr(field="*")
        assert field.field == "*"


class TestConditionExpr:
    """Tests for ConditionExpr model."""

    def test_equality_condition(self):
        """Test equality condition."""
        cond = ConditionExpr(field="status", op="=", value="active")
        assert cond.field == "status"
        assert cond.op == "="
        assert cond.value == "active"

    def test_numeric_comparison(self):
        """Test numeric comparison."""
        cond = ConditionExpr(field="age", op=">=", value=18)
        assert cond.op == ">="
        assert cond.value == 18

    def test_like_operator(self):
        """Test LIKE operator."""
        cond = ConditionExpr(field="email", op="LIKE", value="%@example.com")
        assert cond.op == "LIKE"
        assert cond.value == "%@example.com"

    def test_in_operator_with_list(self):
        """Test IN operator with list value."""
        cond = ConditionExpr(field="category", op="IN", value=["electronics", "books"])
        assert cond.op == "IN"
        assert cond.value == ["electronics", "books"]

    def test_in_operator_requires_list(self):
        """Test that IN operator requires a list."""
        with pytest.raises(ValidationError, match="IN operator requires a list"):
            ConditionExpr(field="category", op="IN", value="electronics")

    def test_in_operator_requires_nonempty_list(self):
        """Test that IN operator requires non-empty list."""
        with pytest.raises(ValidationError, match="non-empty"):
            ConditionExpr(field="category", op="IN", value=[])

    def test_non_in_operator_rejects_list(self):
        """Test that non-IN operators reject list values."""
        with pytest.raises(ValidationError, match="does not support list"):
            ConditionExpr(field="age", op=">", value=[18, 25])

    def test_field_reference_in_value(self):
        """Test using a field reference as value."""
        cond = ConditionExpr(
            field="id",
            table="users",
            op="=",
            value={"field": "user_id", "table": "orders"}
        )
        assert isinstance(cond.value, dict)
        assert cond.value["field"] == "user_id"


class TestLogicalExpr:
    """Tests for LogicalExpr model."""

    def test_and_condition(self):
        """Test AND logical expression."""
        logical = LogicalExpr(
            logic="AND",
            conditions=[
                ConditionExpr(field="status", op="=", value="active"),
                ConditionExpr(field="age", op=">=", value=18),
            ]
        )
        assert logical.logic == "AND"
        assert len(logical.conditions) == 2

    def test_or_condition(self):
        """Test OR logical expression."""
        logical = LogicalExpr(
            logic="OR",
            conditions=[
                ConditionExpr(field="role", op="=", value="admin"),
                ConditionExpr(field="tier", op="=", value="premium"),
            ]
        )
        assert logical.logic == "OR"

    def test_nested_logical_expr(self):
        """Test nested logical expressions."""
        logical = LogicalExpr(
            logic="OR",
            conditions=[
                ConditionExpr(field="tier", op="=", value="VIP"),
                LogicalExpr(
                    logic="AND",
                    conditions=[
                        ConditionExpr(field="status", op="=", value="active"),
                        ConditionExpr(field="age", op=">=", value=18),
                    ]
                ),
            ]
        )
        assert logical.logic == "OR"
        assert isinstance(logical.conditions[1], LogicalExpr)

    def test_requires_minimum_two_conditions(self):
        """Test that LogicalExpr requires at least 2 conditions."""
        with pytest.raises(ValidationError):
            LogicalExpr(
                logic="AND",
                conditions=[ConditionExpr(field="status", op="=", value="active")]
            )


class TestJoinExpr:
    """Tests for JoinExpr model."""

    def test_inner_join(self):
        """Test INNER JOIN."""
        join = JoinExpr(
            type="INNER",
            table="orders",
            on=ConditionExpr(
                field="id",
                table="users",
                op="=",
                value={"field": "user_id", "table": "orders"}
            )
        )
        assert join.type == "INNER"
        assert join.table == "orders"

    def test_left_join(self):
        """Test LEFT JOIN."""
        join = JoinExpr(
            type="LEFT",
            table="profiles",
            on=ConditionExpr(
                field="user_id",
                table="profiles",
                op="=",
                value={"field": "id", "table": "users"}
            )
        )
        assert join.type == "LEFT"

    def test_right_join(self):
        """Test RIGHT JOIN."""
        join = JoinExpr(
            type="RIGHT",
            table="departments",
            on=ConditionExpr(
                field="dept_id",
                table="users",
                op="=",
                value={"field": "id", "table": "departments"}
            )
        )
        assert join.type == "RIGHT"


class TestOrderExpr:
    """Tests for OrderExpr model."""

    def test_ascending_order(self):
        """Test ascending order."""
        order = OrderExpr(field="created_at", direction="ASC")
        assert order.field == "created_at"
        assert order.direction == "ASC"

    def test_descending_order(self):
        """Test descending order."""
        order = OrderExpr(field="name", direction="DESC")
        assert order.direction == "DESC"

    def test_order_with_table(self):
        """Test order with table qualifier."""
        order = OrderExpr(field="total", table="orders", direction="DESC")
        assert order.table == "orders"


class TestQueryIR:
    """Tests for QueryIR model."""

    def test_simple_select_all(self):
        """Test simple SELECT * query."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")]
        )
        assert query.operation == "SELECT"
        assert query.source.table == "users"
        assert len(query.fields) == 1
        assert query.fields[0].field == "*"

    def test_select_with_filters(self):
        """Test SELECT with WHERE clause."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="active")
        )
        assert query.filters is not None
        assert isinstance(query.filters, ConditionExpr)

    def test_select_with_join(self):
        """Test SELECT with JOIN."""
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
        assert len(query.joins) == 1
        assert query.joins[0].table == "orders"

    def test_select_with_order_by(self):
        """Test SELECT with ORDER BY."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=[OrderExpr(field="name", direction="ASC")]
        )
        assert len(query.order_by) == 1

    def test_select_with_limit(self):
        """Test SELECT with LIMIT."""
        query = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10
        )
        assert query.limit == 10

    def test_limit_must_be_positive(self):
        """Test that LIMIT must be >= 1."""
        with pytest.raises(ValidationError):
            QueryIR(
                operation="SELECT",
                source=TableSource(table="users"),
                fields=[FieldExpr(field="*")],
                limit=0
            )

    def test_requires_at_least_one_field(self):
        """Test that at least one field is required."""
        with pytest.raises(ValidationError):
            QueryIR(
                operation="SELECT",
                source=TableSource(table="users"),
                fields=[]
            )

    def test_complex_query_from_design_doc(self):
        """Test complex query example from DESIGN.md."""
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
        assert query.operation == "SELECT"
        assert len(query.fields) == 3
        assert len(query.joins) == 1
        assert isinstance(query.filters, LogicalExpr)
        assert len(query.order_by) == 1
