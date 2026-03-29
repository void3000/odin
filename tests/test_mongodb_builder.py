"""
Tests for MongoDB query builder.

Tests the visitor pattern implementation for MongoDB query generation.
"""

import pytest
from src.ir.models import (
    QueryIR,
    TableSource,
    FieldExpr,
    ConditionExpr,
    LogicalExpr,
    JoinExpr,
    OrderExpr,
)
from src.query.mongodb import MongoDBBuilder
from src.query.base import UnsupportedFeatureError
from src.query.result import GenericQueryResult


class TestMongoDBBuilder:
    """Test MongoDB builder with various IR structures."""

    def test_build_simple_select_all(self):
        """Test SELECT * FROM users."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")]
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert isinstance(result, GenericQueryResult)
        assert result.database_type == "mongodb"
        assert result.query["collection"] == "users"
        assert result.query["filter"] == {}
        assert result.query["projection"] is None  # SELECT * → no projection
        assert result.query["sort"] is None
        assert result.query["limit"] is None

    def test_build_select_specific_fields(self):
        """Test SELECT name, email FROM users."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="name"),
                FieldExpr(field="email")
            ]
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["collection"] == "users"
        assert result.query["projection"] == {"name": 1, "email": 1, "_id": 0}

    def test_build_with_equality_filter(self):
        """Test WHERE status = 'active'."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="active")
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["filter"] == {"status": "active"}

    def test_build_with_inequality_filter(self):
        """Test WHERE age != 18."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="age", op="!=", value=18)
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["filter"] == {"age": {"$ne": 18}}

    def test_build_with_comparison_operators(self):
        """Test comparison operators (>, >=, <, <=)."""
        test_cases = [
            (">", {"$gt": 18}),
            (">=", {"$gte": 18}),
            ("<", {"$lt": 18}),
            ("<=", {"$lte": 18}),
        ]

        for op, expected in test_cases:
            query_ir = QueryIR(
                operation="SELECT",
                source=TableSource(table="users"),
                fields=[FieldExpr(field="*")],
                filters=ConditionExpr(field="age", op=op, value=18)
            )

            builder = MongoDBBuilder()
            result = builder.build(query_ir)

            assert result.query["filter"] == {"age": expected}, f"Failed for operator {op}"

    def test_build_with_in_operator(self):
        """Test WHERE status IN ('active', 'pending')."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="IN", value=["active", "pending"])
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["filter"] == {"status": {"$in": ["active", "pending"]}}

    def test_build_with_like_operator(self):
        """Test LIKE operator → $regex."""
        test_cases = [
            ("john%", "^john"),  # Starts with
            ("%john", "john$"),  # Ends with
            ("%john%", "john"),  # Contains
        ]

        for like_pattern, expected_regex in test_cases:
            query_ir = QueryIR(
                operation="SELECT",
                source=TableSource(table="users"),
                fields=[FieldExpr(field="*")],
                filters=ConditionExpr(field="name", op="LIKE", value=like_pattern)
            )

            builder = MongoDBBuilder()
            result = builder.build(query_ir)

            assert "$regex" in result.query["filter"]["name"]
            assert expected_regex in result.query["filter"]["name"]["$regex"]

    def test_build_with_and_condition(self):
        """Test AND logical operator."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=LogicalExpr(
                logic="AND",
                conditions=[
                    ConditionExpr(field="age", op=">", value=18),
                    ConditionExpr(field="status", op="=", value="active")
                ]
            )
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        # MongoDB optimizes simple AND into single dict
        filter_dict = result.query["filter"]
        assert filter_dict["age"] == {"$gt": 18}
        assert filter_dict["status"] == "active"

    def test_build_with_or_condition(self):
        """Test OR logical operator."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=LogicalExpr(
                logic="OR",
                conditions=[
                    ConditionExpr(field="status", op="=", value="active"),
                    ConditionExpr(field="status", op="=", value="pending")
                ]
            )
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert "$or" in result.query["filter"]
        assert len(result.query["filter"]["$or"]) == 2

    def test_build_with_nested_logical(self):
        """Test nested AND/OR conditions."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=LogicalExpr(
                logic="AND",
                conditions=[
                    ConditionExpr(field="age", op=">", value=18),
                    LogicalExpr(
                        logic="OR",
                        conditions=[
                            ConditionExpr(field="status", op="=", value="active"),
                            ConditionExpr(field="status", op="=", value="pending")
                        ]
                    )
                ]
            )
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        # Should have $and with nested $or
        assert "$and" in result.query["filter"]
        conditions = result.query["filter"]["$and"]
        assert any("$or" in str(c) for c in conditions)

    def test_build_with_order_by_asc(self):
        """Test ORDER BY created_at ASC."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=[OrderExpr(field="created_at", direction="ASC")]
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["sort"] == [("created_at", 1)]  # 1 = ascending

    def test_build_with_order_by_desc(self):
        """Test ORDER BY created_at DESC."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=[OrderExpr(field="created_at", direction="DESC")]
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["sort"] == [("created_at", -1)]  # -1 = descending

    def test_build_with_multiple_order_by(self):
        """Test multiple ORDER BY fields."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=[
                OrderExpr(field="status", direction="ASC"),
                OrderExpr(field="created_at", direction="DESC")
            ]
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["sort"] == [("status", 1), ("created_at", -1)]

    def test_build_with_limit(self):
        """Test LIMIT 10."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["limit"] == 10

    def test_build_complex_query(self):
        """Test complex query with all features."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="name"),
                FieldExpr(field="email"),
                FieldExpr(field="created_at")
            ],
            filters=LogicalExpr(
                logic="AND",
                conditions=[
                    ConditionExpr(field="age", op=">=", value=18),
                    ConditionExpr(field="status", op="IN", value=["active", "pending"])
                ]
            ),
            order_by=[OrderExpr(field="created_at", direction="DESC")],
            limit=20
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        assert result.query["collection"] == "users"
        assert result.query["projection"] == {"name": 1, "email": 1, "created_at": 1, "_id": 0}
        assert "age" in result.query["filter"]
        assert "status" in result.query["filter"]
        assert result.query["sort"] == [("created_at", -1)]
        assert result.query["limit"] == 20

    def test_joins_not_supported(self):
        """Test that JOINs raise UnsupportedFeatureError."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="orders",
                    on=ConditionExpr(
                        field="user_id",
                        table="orders",
                        op="=",
                        value={"table": "users", "field": "id"}
                    )
                )
            ]
        )

        builder = MongoDBBuilder()

        with pytest.raises(UnsupportedFeatureError, match="JOINs"):
            builder.build(query_ir)

    def test_get_capabilities(self):
        """Test MongoDB capabilities."""
        builder = MongoDBBuilder()
        caps = builder.get_capabilities()

        assert caps.supports_joins is False  # MongoDB doesn't support JOINs
        assert caps.supports_complex_filters is True
        assert "=" in caps.supported_operators
        assert "LIKE" in caps.supported_operators

    def test_result_to_dict(self):
        """Test GenericQueryResult to_dict method."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")]
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        result_dict = result.to_dict()

        assert result_dict["database_type"] == "mongodb"
        assert "query" in result_dict
        assert "metadata" in result_dict

    def test_result_str(self):
        """Test GenericQueryResult __str__ method."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="active")
        )

        builder = MongoDBBuilder()
        result = builder.build(query_ir)

        str_repr = str(result)

        assert "MongoDB Query" in str_repr
        assert "users" in str_repr
        assert "status" in str_repr
