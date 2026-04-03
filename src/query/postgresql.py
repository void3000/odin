"""
PostgreSQL Query Builder using Visitor Pattern.

Translates IR to PostgreSQL-specific SQL with parameterized queries.
Uses recursive visitor pattern for tree walking (like compiler AST visitors).
"""

from typing import Any, List

from src.ir.models import (
    QueryIR,
    TableSource,
    FieldExpr,
    JoinExpr,
    ConditionExpr,
    LogicalExpr,
    OrderExpr,
    FilterExpr,
)
from .base import QueryBuilder, QueryCapabilities, QueryBuildError
from .result import GenericQueryResult


class PostgreSQLBuilder(QueryBuilder):
    """PostgreSQL query builder using visitor pattern.

    Walks the IR tree recursively (like a compiler AST visitor),
    generating SQL by visiting each node type.

    Features:
    - Double-quoted identifiers: "table"."column"
    - Numbered parameters: $1, $2, $3
    - Recursive visiting for nested queries
    - Full SQL feature support (JOINs, complex filters, etc.)
    """

    def __init__(self):
        """Initialize PostgreSQL builder."""
        self.params: List[Any] = []
        self.param_counter: int = 0

    def build(self, query_ir: QueryIR) -> GenericQueryResult:
        """Build PostgreSQL query from IR.

        Entry point - initializes state and starts tree walking.

        Args:
            query_ir: Validated intermediate representation

        Returns:
            GenericQueryResult with SQL and parameters

        Raises:
            UnsupportedFeatureError: If IR uses unsupported features
            QueryBuildError: If query cannot be built
        """
        # Validate IR against capabilities
        self.validate_ir(query_ir)

        # Reset state for new query
        self.params = []
        self.param_counter = 0

        # Visit IR tree recursively
        sql = self.visit_query(query_ir)

        return GenericQueryResult(
            database_type="postgresql",
            query={
                "sql": sql,
                "params": self.params
            },
            metadata={
                "builder": "PostgreSQLBuilder",
                "param_style": "numbered"  # $1, $2, etc.
            }
        )

    def get_capabilities(self) -> QueryCapabilities:
        """Get PostgreSQL capabilities.

        PostgreSQL supports all standard SQL features plus extensions.

        Returns:
            QueryCapabilities with full feature support
        """
        return QueryCapabilities(
            supports_joins=True,
            supports_complex_filters=True,
            supports_aggregates=True,
            supports_subqueries=True,
            max_join_depth=None,  # No practical limit
            supported_operators={"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE", "ILIKE"}
        )

    def visit_query(self, node: QueryIR) -> str:
        """Visit a QueryIR node.

        This is the main recursive entry point. Each component visits
        its children, allowing natural recursion for subqueries.

        Args:
            node: QueryIR node to visit

        Returns:
            Complete SQL query string
        """
        parts = []

        # Visit each component - they handle their own recursion
        parts.append(self.visit_select(node.fields))
        parts.append(self.visit_from(node.source))

        if node.joins:
            parts.append(self.visit_joins(node.joins))

        if node.filters:
            parts.append(self.visit_where(node.filters))

        if node.order_by:
            parts.append(self.visit_order_by(node.order_by))

        if node.limit:
            parts.append(self.visit_limit(node.limit))

        return "\n".join(p for p in parts if p)

    def visit_select(self, fields: List[FieldExpr]) -> str:
        """Visit SELECT clause.

        Args:
            fields: List of field expressions

        Returns:
            SELECT clause SQL
        """
        field_parts = [self.visit_field(field) for field in fields]
        return "SELECT " + ", ".join(field_parts)

    def visit_field(self, field: FieldExpr) -> str:
        """Visit a field expression.

        Handles regular fields, wildcards, and aggregate functions.

        Args:
            field: Field expression to visit

        Returns:
            Field SQL fragment
        """
        # Aggregate function
        if getattr(field, "function", None) is not None:
            if field.field == "*":
                inner = "*"
            elif field.table:
                inner = self._quote_qualified(field.table, field.field)
            else:
                inner = self._quote_identifier(field.field)

            result = f"{field.function}({inner})"

            if field.alias:
                result += f" AS {self._quote_identifier(field.alias)}"
            return result

        # Wildcard
        if field.field == "*":
            if field.table:
                return f"{self._quote_identifier(field.table)}.*"
            return "*"

        # Regular field
        if field.table:
            result = self._quote_qualified(field.table, field.field)
        else:
            result = self._quote_identifier(field.field)

        # Add alias if present
        if field.alias:
            result += f" AS {self._quote_identifier(field.alias)}"

        return result

    def visit_from(self, source: TableSource) -> str:
        """Visit FROM clause.

        Args:
            source: Table source

        Returns:
            FROM clause SQL
        """
        table_ref = self.visit_table_source(source)
        return f"FROM {table_ref}"

    def visit_table_source(self, source: TableSource) -> str:
        """Visit a table source.

        Handles both simple tables and derived tables (subqueries).

        Args:
            source: Table source to visit

        Returns:
            Table reference SQL
        """
        # Simple table
        table = self._quote_identifier(source.table)

        # Add alias if present (for future subquery support)
        if hasattr(source, 'alias') and source.alias:
            table += f" AS {self._quote_identifier(source.alias)}"

        return table

    def visit_joins(self, joins: List[JoinExpr]) -> str:
        """Visit JOIN clauses.

        Args:
            joins: List of join expressions

        Returns:
            JOIN clauses SQL
        """
        join_parts = [self.visit_join(join) for join in joins]
        return "\n".join(join_parts)

    def visit_join(self, join: JoinExpr) -> str:
        """Visit a single JOIN.

        Args:
            join: Join expression to visit

        Returns:
            JOIN clause SQL
        """
        join_type = join.type  # "INNER", "LEFT", "RIGHT"
        table = self._quote_identifier(join.table)
        condition = self.visit_condition(join.on)

        return f"{join_type} JOIN {table} ON {condition}"

    def visit_where(self, filters: FilterExpr) -> str:
        """Visit WHERE clause.

        Args:
            filters: Filter expression

        Returns:
            WHERE clause SQL
        """
        condition = self.visit_filter(filters)
        return f"WHERE {condition}"

    def visit_filter(self, expr: FilterExpr) -> str:
        """Visit a filter expression.

        Dispatches to specific visitor based on expression type.
        This enables recursion for nested logical expressions.

        Args:
            expr: Filter expression (ConditionExpr or LogicalExpr)

        Returns:
            Filter SQL fragment

        Raises:
            QueryBuildError: If expression type is unknown
        """
        if isinstance(expr, ConditionExpr):
            return self.visit_condition(expr)
        elif isinstance(expr, LogicalExpr):
            return self.visit_logical(expr)
        else:
            raise QueryBuildError(f"Unknown filter expression type: {type(expr)}")

    def visit_condition(self, cond: ConditionExpr) -> str:
        """Visit a condition expression.

        Handles field comparisons with values or field references.

        Args:
            cond: Condition expression to visit

        Returns:
            Condition SQL fragment
        """
        # Build left side (field reference)
        left = self.visit_field_reference(cond.field, cond.table)

        # Get operator
        op = cond.op

        # Build right side (value or field reference)
        right = self.visit_value(cond.value, op)

        return f"{left} {op} {right}"

    def visit_logical(self, expr: LogicalExpr) -> str:
        """Visit a logical expression (AND/OR).

        Recursively visits sub-conditions, enabling nested logic.

        Args:
            expr: Logical expression to visit

        Returns:
            Logical expression SQL with parentheses
        """
        logic_op = expr.logic  # "AND" or "OR"

        # Recursively visit each sub-condition
        sub_conditions = [self.visit_filter(cond) for cond in expr.conditions]

        # Join with operator and wrap in parentheses
        joined = f" {logic_op} ".join(f"({c})" for c in sub_conditions)

        return f"({joined})"

    def visit_field_reference(self, field: str, table: str | None) -> str:
        """Visit a field reference.

        Args:
            field: Field name
            table: Optional table qualifier

        Returns:
            Quoted field reference
        """
        if table:
            return self._quote_qualified(table, field)
        return self._quote_identifier(field)

    def visit_value(self, value: Any, operator: str) -> str:
        """Visit a value in a condition.

        Handles scalars, lists (for IN), and field references.

        Args:
            value: Value to visit
            operator: Operator context (affects handling of lists)

        Returns:
            Value SQL (parameter placeholder or field reference)

        Raises:
            QueryBuildError: If value type is invalid
        """
        # Field reference (for joins)
        if isinstance(value, dict):
            if "field" in value and "table" in value:
                return self._quote_qualified(value["table"], value["field"])
            elif "field" in value:
                return self._quote_identifier(value["field"])
            else:
                raise QueryBuildError(f"Invalid field reference: {value}")

        # List (for IN operator)
        elif operator == "IN":
            if not isinstance(value, list):
                raise QueryBuildError(f"IN operator requires list value, got {type(value)}")
            placeholders = [self._add_param(v) for v in value]
            return f"({', '.join(placeholders)})"

        # Scalar value
        else:
            return self._add_param(value)

    def visit_order_by(self, order_by: List[OrderExpr]) -> str:
        """Visit ORDER BY clause.

        Args:
            order_by: List of order expressions

        Returns:
            ORDER BY clause SQL
        """
        order_parts = [self.visit_order_expr(expr) for expr in order_by]
        return "ORDER BY " + ", ".join(order_parts)

    def visit_order_expr(self, expr: OrderExpr) -> str:
        """Visit an ORDER BY expression.

        Args:
            expr: Order expression to visit

        Returns:
            ORDER BY expression SQL
        """
        # Build field reference
        field = self.visit_field_reference(expr.field, expr.table)

        # Add direction
        direction = expr.direction  # "ASC" or "DESC"

        return f"{field} {direction}"

    def visit_limit(self, limit: int) -> str:
        """Visit LIMIT clause.

        Args:
            limit: Maximum number of rows

        Returns:
            LIMIT clause SQL
        """
        return f"LIMIT {limit}"

    # ========== Helper Methods ==========

    def _quote_identifier(self, name: str) -> str:
        """Quote identifier with double quotes.

        Args:
            name: Identifier to quote (table or column name)

        Returns:
            Quoted identifier safe for SQL

        Example:
            _quote_identifier('users') -> '"users"'
            _quote_identifier('my"table') -> '"my""table"'
        """
        # Escape internal double quotes by doubling them
        escaped = name.replace('"', '""')
        return f'"{escaped}"'

    def _quote_qualified(self, table: str, column: str) -> str:
        """Quote qualified identifier (table.column).

        Args:
            table: Table name
            column: Column name

        Returns:
            Quoted qualified identifier

        Example:
            _quote_qualified('users', 'email') -> '"users"."email"'
        """
        return f"{self._quote_identifier(table)}.{self._quote_identifier(column)}"

    def _add_param(self, value: Any) -> str:
        """Add parameter and return placeholder.

        Parameters are accumulated in shared state across the entire
        query tree (including subqueries when supported).

        Args:
            value: Parameter value to add

        Returns:
            Parameter placeholder ($1, $2, etc.)
        """
        self.params.append(value)
        self.param_counter += 1
        return f"${self.param_counter}"


# Register with factory
from .factory import QueryBuilderFactory
QueryBuilderFactory.register("postgresql", PostgreSQLBuilder)
