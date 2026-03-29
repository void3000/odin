"""Tests for PostgreSQL query builder."""

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
from src.query.postgresql import PostgreSQLBuilder
from src.query.result import GenericQueryResult
from src.query.base import UnsupportedFeatureError


class TestPostgreSQLBuilder:
    """Tests for PostgreSQLBuilder."""

    def test_build_simple_select_all(self):
        """Test simple SELECT * query."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert isinstance(result, GenericQueryResult)
        assert result.query['sql'] == 'SELECT *\nFROM "users"'
        assert result.query['params'] == []

    def test_build_select_specific_fields(self):
        """Test SELECT with specific fields."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="id"),
                FieldExpr(field="name"),
                FieldExpr(field="email"),
            ]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert result.query['sql'] == 'SELECT "id", "name", "email"\nFROM "users"'
        assert result.query['params'] == []

    def test_build_select_with_alias(self):
        """Test SELECT with field aliases."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="products"),
            fields=[
                FieldExpr(field="name"),
                FieldExpr(field="price", alias="cost"),
            ]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert result.query['sql'] == 'SELECT "name", "price" AS "cost"\nFROM "products"'
        assert result.query['params'] == []

    def test_build_with_simple_filter(self):
        """Test query with simple WHERE clause."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="active")
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'WHERE "status" = $1' in result.query['sql']
        assert result.query['params'] == ["active"]

    def test_build_with_numeric_comparison(self):
        """Test query with numeric comparison."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="age", op=">=", value=18)
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'WHERE "age" >= $1' in result.query['sql']
        assert result.query['params'] == [18]

    def test_build_with_in_operator(self):
        """Test query with IN operator."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="products"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(
                field="category",
                op="IN",
                value=["electronics", "books", "clothing"]
            )
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'WHERE "category" IN ($1, $2, $3)' in result.query['sql']
        assert result.query['params'] == ["electronics", "books", "clothing"]

    def test_build_with_like_operator(self):
        """Test query with LIKE operator."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="email", op="LIKE", value="%@example.com")
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'WHERE "email" LIKE $1' in result.query['sql']
        assert result.query['params'] == ["%@example.com"]

    def test_build_with_and_condition(self):
        """Test query with AND condition."""
        query_ir = QueryIR(
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

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'AND' in result.query['sql']
        assert '"status" = $1' in result.query['sql']
        assert '"age" >= $2' in result.query['sql']
        assert result.query['params'] == ["active", 18]

    def test_build_with_or_condition(self):
        """Test query with OR condition."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=LogicalExpr(
                logic="OR",
                conditions=[
                    ConditionExpr(field="role", op="=", value="admin"),
                    ConditionExpr(field="role", op="=", value="moderator")
                ]
            )
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'OR' in result.query['sql']
        assert '"role" = $1' in result.query['sql']
        assert '"role" = $2' in result.query['sql']
        assert result.query['params'] == ["admin", "moderator"]

    def test_build_with_nested_logical(self):
        """Test query with nested AND/OR conditions."""
        query_ir = QueryIR(
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
                            ConditionExpr(field="age", op=">", value=10)
                        ]
                    )
                ]
            )
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'WHERE' in result.query['sql']
        assert result.query['params'] == ["VIP", "active", 10]

    def test_build_with_inner_join(self):
        """Test query with INNER JOIN."""
        query_ir = QueryIR(
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

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'SELECT "users"."name", "orders"."total"' in result.query['sql']
        assert 'FROM "users"' in result.query['sql']
        assert 'INNER JOIN "orders" ON "users"."id" = "orders"."user_id"' in result.query['sql']
        assert result.query['params'] == []

    def test_build_with_left_join(self):
        """Test query with LEFT JOIN."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*", table="users")],
            joins=[
                JoinExpr(
                    type="LEFT",
                    table="profiles",
                    on=ConditionExpr(
                        field="user_id",
                        table="profiles",
                        op="=",
                        value={"field": "id", "table": "users"}
                    )
                )
            ]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'LEFT JOIN "profiles"' in result.query['sql']

    def test_build_with_order_by(self):
        """Test query with ORDER BY."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=[
                OrderExpr(field="created_at", direction="DESC")
            ]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'ORDER BY "created_at" DESC' in result.query['sql']

    def test_build_with_multiple_order_by(self):
        """Test query with multiple ORDER BY fields."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=[
                OrderExpr(field="status", direction="ASC"),
                OrderExpr(field="created_at", direction="DESC")
            ]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'ORDER BY "status" ASC, "created_at" DESC' in result.query['sql']

    def test_build_with_limit(self):
        """Test query with LIMIT."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'LIMIT 10' in result.query['sql']

    def test_build_complex_query_from_design_doc(self):
        """Test complex query from design documentation."""
        query_ir = QueryIR(
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
            ],
            limit=10
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Verify all components present
        assert 'SELECT "users"."name", "orders"."total", "orders"."created_at" AS "order_date"' in result.query['sql']
        assert 'FROM "users"' in result.query['sql']
        assert 'INNER JOIN "orders"' in result.query['sql']
        assert 'WHERE' in result.query['sql']
        assert 'ORDER BY "orders"."created_at" DESC' in result.query['sql']
        assert 'LIMIT 10' in result.query['sql']
        assert result.query['params'] == ["premium", 100]

    def test_quote_identifier_escapes_quotes(self):
        """Test identifier quoting escapes internal quotes."""
        builder = PostgreSQLBuilder()

        # Table name with quote
        quoted = builder._quote_identifier('my"table')
        assert quoted == '"my""table"'

    def test_get_capabilities(self):
        """Test capabilities reporting."""
        builder = PostgreSQLBuilder()
        capabilities = builder.get_capabilities()

        assert capabilities.supports_joins is True
        assert capabilities.supports_complex_filters is True
        assert capabilities.supports_aggregates is True
        assert "=" in capabilities.supported_operators
        assert "LIKE" in capabilities.supported_operators
        assert "ILIKE" in capabilities.supported_operators

    def test_result_to_dict(self):
        """Test QueryResult.to_dict()."""
        result = GenericQueryResult(
            database_type="postgresql",
            query={
                "sql": 'SELECT * FROM "users"',
                "params": ["active"]
            }
        )

        result_dict = result.to_dict()

        assert result_dict["database_type"] == "postgresql"
        assert result_dict["query"]["sql"] == 'SELECT * FROM "users"'
        assert result_dict["query"]["params"] == ["active"]

    def test_result_str(self):
        """Test QueryResult.__str__()."""
        result = GenericQueryResult(
            database_type="postgresql",
            query={
                "sql": 'SELECT * FROM "users"',
                "params": ["active"]
            }
        )

        str_repr = str(result)

        assert "POSTGRESQL Query:" in str_repr
        assert 'SELECT * FROM "users"' in str_repr
        assert "['active']" in str_repr


class TestPostgreSQLBuilderEdgeCases:
    """Test edge cases and error conditions."""

    def test_wildcard_with_table_qualifier(self):
        """Test wildcard selection with table qualifier."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*", table="users")]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert result.query['sql'] == 'SELECT "users".*\nFROM "users"'

    def test_mixed_qualified_and_unqualified_fields(self):
        """Test mixing qualified and unqualified fields."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="id"),
                FieldExpr(field="email", table="users"),
            ]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'SELECT "id", "users"."email"' in result.query['sql']

    def test_parameter_counter_resets(self):
        """Test that parameter counter resets between builds."""
        builder = PostgreSQLBuilder()

        # First query
        query1 = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="active")
        )
        result1 = builder.build(query1)
        assert "$1" in result1.query['sql']

        # Second query should reset counter
        query2 = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="inactive")
        )
        result2 = builder.build(query2)
        assert "$1" in result2.query['sql']  # Should be $1 again, not $2
        assert result2.query['params'] == ["inactive"]

    def test_empty_joins_list(self):
        """Test query with empty joins list."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            joins=[]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert "JOIN" not in result.query['sql']

    def test_no_filters(self):
        """Test query without filters."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=None
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert "WHERE" not in result.query['sql']

    def test_no_order_by(self):
        """Test query without ORDER BY."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            order_by=None
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert "ORDER BY" not in result.query['sql']

    def test_no_limit(self):
        """Test query without LIMIT."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=None
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert "LIMIT" not in result.query['sql']
