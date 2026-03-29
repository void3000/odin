"""
Test edge cases for PostgreSQL visitor pattern implementation.

Tests critical edge cases identified in docs/EDGE_CASES.md.
"""

import pytest
import threading
from src.ir.models import (
    QueryIR,
    TableSource,
    FieldExpr,
    ConditionExpr,
    LogicalExpr,
    JoinExpr,
)
from src.query.postgresql import PostgreSQLBuilder
from src.query.base import QueryBuildError


class TestNullValueHandling:
    """Test handling of NULL values in conditions."""

    def test_null_value_rejected_by_ir_validation(self):
        """Test that NULL values are rejected at IR validation."""
        # IR model doesn't accept None - validates it's caught
        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryIR(
                operation="SELECT",
                source=TableSource(table="users"),
                fields=[FieldExpr(field="*")],
                filters=ConditionExpr(field="deleted_at", op="=", value=None)
            )


class TestEmptyInList:
    """Test handling of empty lists with IN operator."""

    def test_empty_in_list_raises_error(self):
        """Test that empty IN list is caught at IR validation."""
        # IR model should catch this
        with pytest.raises(Exception, match="IN operator requires non-empty list"):
            QueryIR(
                operation="SELECT",
                source=TableSource(table="users"),
                fields=[FieldExpr(field="*")],
                filters=ConditionExpr(field="status", op="IN", value=[])
            )


class TestDeepRecursion:
    """Test handling of deeply nested logical expressions."""

    def test_moderately_deep_nesting(self):
        """Test nesting depth of 10 levels."""
        # Build nested structure: (((...((A OR B) AND C) OR D) AND E)...)
        def build_nested(depth):
            if depth == 0:
                return ConditionExpr(field="status", op="=", value=f"level_{depth}")

            return LogicalExpr(
                logic="AND" if depth % 2 == 0 else "OR",
                conditions=[
                    build_nested(depth - 1),
                    ConditionExpr(field="level", op="=", value=depth)
                ]
            )

        nested_filter = build_nested(10)

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="test"),
            fields=[FieldExpr(field="*")],
            filters=nested_filter
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Should succeed without stack overflow
        assert "WHERE" in result.query['sql']
        assert len(result.query['params']) == 11  # 11 conditions

    def test_very_deep_nesting(self):
        """Test nesting depth of 100 levels (stress test)."""
        def build_nested(depth):
            if depth == 0:
                return ConditionExpr(field="id", op="=", value=depth)

            return LogicalExpr(
                logic="AND",
                conditions=[
                    build_nested(depth - 1),
                    ConditionExpr(field="level", op="=", value=depth)
                ]
            )

        nested_filter = build_nested(100)

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="test"),
            fields=[FieldExpr(field="*")],
            filters=nested_filter
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Should succeed without hitting recursion limit
        assert "WHERE" in result.query['sql']
        assert len(result.query['params']) == 101


class TestSpecialCharactersInIdentifiers:
    """Test handling of special characters in table/field names."""

    def test_double_quotes_in_identifier(self):
        """Test identifier containing double quotes."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table='my"table'),
            fields=[FieldExpr(field='field"name')]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Should escape double quotes by doubling them
        assert 'FROM "my""table"' in result.query['sql']
        assert 'SELECT "field""name"' in result.query['sql']

    def test_unicode_identifiers(self):
        """Test Unicode characters in identifiers."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="用户表"),
            fields=[FieldExpr(field="名前")]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'FROM "用户表"' in result.query['sql']
        assert 'SELECT "名前"' in result.query['sql']

    def test_spaces_in_identifiers(self):
        """Test spaces in identifiers."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="my table"),
            fields=[FieldExpr(field="first name")]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'FROM "my table"' in result.query['sql']
        assert 'SELECT "first name"' in result.query['sql']

    def test_sql_injection_attempt_in_identifier(self):
        """Test SQL injection attempt in identifier."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table='users"; DROP TABLE users--'),
            fields=[FieldExpr(field='id"; DELETE FROM users WHERE "x')]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Should be safely escaped
        assert 'FROM "users""; DROP TABLE users--"' in result.query['sql']
        assert 'SELECT "id""; DELETE FROM users WHERE ""x"' in result.query['sql']
        # The malicious code is now part of the identifier name, not executable

    def test_reserved_words_as_identifiers(self):
        """Test SQL reserved words as identifiers."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="select"),
            fields=[FieldExpr(field="from"), FieldExpr(field="where")]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Should quote reserved words
        assert 'FROM "select"' in result.query['sql']
        assert 'SELECT "from", "where"' in result.query['sql']


class TestSelfJoins:
    """Test handling of self-joins."""

    def test_self_join_without_alias(self):
        """Test self-join without alias (problematic but valid SQL)."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            joins=[
                JoinExpr(
                    type="INNER",
                    table="users",
                    on=ConditionExpr(
                        field="manager_id",
                        op="=",
                        value={"field": "id"}
                    )
                )
            ]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Generates valid SQL syntax but semantically ambiguous
        assert 'FROM "users"' in result.query['sql']
        assert 'INNER JOIN "users"' in result.query['sql']
        # This is a known limitation - user should use aliases in IR


class TestThreadSafety:
    """Test thread safety of builder."""

    def test_concurrent_builds_are_isolated(self):
        """Test that concurrent builds don't interfere with each other."""
        # Use separate builder instances (recommended usage)
        query1 = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="status", op="=", value="active")
        )

        query2 = QueryIR(
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="total", op=">", value=100)
        )

        results = {}
        errors = {}

        def build_query(name, builder, query):
            try:
                results[name] = builder.build(query)
            except Exception as e:
                errors[name] = e

        # Create separate builders for each thread
        builder1 = PostgreSQLBuilder()
        builder2 = PostgreSQLBuilder()

        thread1 = threading.Thread(target=build_query, args=("query1", builder1, query1))
        thread2 = threading.Thread(target=build_query, args=("query2", builder2, query2))

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        # Both should succeed
        assert len(errors) == 0
        assert len(results) == 2

        # Check results are correct
        assert "users" in results["query1"].query["sql"]
        assert results["query1"].query["params"] == ["active"]

        assert "orders" in results["query2"].query["sql"]
        assert results["query2"].query["params"] == [100]

    def test_shared_builder_instance_not_thread_safe(self):
        """Test that sharing builder instance between threads is NOT safe."""
        shared_builder = PostgreSQLBuilder()

        query1 = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="id", op="=", value=1)
        )

        query2 = QueryIR(
            operation="SELECT",
            source=TableSource(table="orders"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="id", op="=", value=2)
        )

        results = {}

        def build_query(name, query):
            # Small delay to increase chance of race condition
            import time
            time.sleep(0.001)
            results[name] = shared_builder.build(query)

        threads = [
            threading.Thread(target=build_query, args=("query1", query1)),
            threading.Thread(target=build_query, args=("query2", query2))
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # This test documents that shared instances are NOT thread-safe
        # Results may be corrupted due to race conditions
        # (This is expected behavior - document, don't fix)


class TestLargeQueries:
    """Test handling of very large queries."""

    def test_large_select_list(self):
        """Test query with many fields in SELECT."""
        fields = [FieldExpr(field=f"field_{i}") for i in range(100)]

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="wide_table"),
            fields=fields
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Should generate SQL with 100 fields
        assert result.query['sql'].startswith("SELECT")
        assert result.query['sql'].count('"field_') == 100

    def test_large_in_list(self):
        """Test query with large IN list."""
        values = list(range(500))

        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="id", op="IN", value=values)
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Should generate 500 parameters
        assert len(result.query['params']) == 500
        assert result.query['sql'].count("$") == 500


class TestLimitEdgeCases:
    """Test LIMIT clause edge cases."""

    def test_limit_zero_rejected_by_ir_validation(self):
        """Test LIMIT 0 is rejected at IR validation (ge=1)."""
        # IR validation should catch this (ge=1)
        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryIR(
                operation="SELECT",
                source=TableSource(table="users"),
                fields=[FieldExpr(field="*")],
                limit=0
            )


class TestMultipleWildcards:
    """Test multiple wildcards in SELECT."""

    def test_multiple_table_wildcards(self):
        """Test selecting all fields from multiple tables."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="*", table="users"),
                FieldExpr(field="*", table="orders")
            ],
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

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'SELECT "users".*, "orders".*' in result.query['sql']

    def test_wildcard_mixed_with_specific_fields(self):
        """Test mixing wildcard with specific fields."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[
                FieldExpr(field="*"),
                FieldExpr(field="created_at")  # Redundant but valid
            ]
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # PostgreSQL allows this
        assert 'SELECT *, "created_at"' in result.query['sql']


class TestEmptyStringValues:
    """Test handling of empty string values."""

    def test_empty_string_in_equality(self):
        """Test empty string value in condition."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="name", op="=", value="")
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'WHERE "name" = $1' in result.query['sql']
        assert result.query['params'] == [""]

    def test_empty_string_in_like(self):
        """Test empty string with LIKE operator."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="name", op="LIKE", value="")
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        assert 'WHERE "name" LIKE $1' in result.query['sql']
        assert result.query['params'] == [""]


class TestOperatorCaseSensitivity:
    """Test operator case handling."""

    def test_uppercase_operators(self):
        """Test that operators are preserved as-is."""
        query_ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            filters=ConditionExpr(field="name", op="LIKE", value="%test%")
        )

        builder = PostgreSQLBuilder()
        result = builder.build(query_ir)

        # Operator should be uppercase as provided
        assert "LIKE" in result.query['sql']

    def test_ilike_operator_not_in_base_ir(self):
        """Test that ILIKE is not in base IR operators (PostgreSQL-specific)."""
        # ILIKE is PostgreSQL-specific but not in base IR model
        # IR model only supports standard operators
        with pytest.raises(Exception):  # Pydantic ValidationError
            QueryIR(
                operation="SELECT",
                source=TableSource(table="users"),
                fields=[FieldExpr(field="*")],
                filters=ConditionExpr(field="name", op="ILIKE", value="%test%")
            )
