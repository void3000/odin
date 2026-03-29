"""
MongoDB Query Builder using Visitor Pattern.

Translates IR to MongoDB query structure (find, filter, projection, etc.).
Uses recursive visitor pattern for tree walking.
"""

from typing import Any, Dict, List, Optional, Tuple

from src.ir.models import (
    QueryIR,
    TableSource,
    FieldExpr,
    ConditionExpr,
    LogicalExpr,
    OrderExpr,
    FilterExpr,
)
from .base import QueryBuilder, QueryCapabilities, QueryBuildError, UnsupportedFeatureError
from .result import GenericQueryResult


class MongoDBBuilder(QueryBuilder):
    """MongoDB query builder using visitor pattern.

    Walks the IR tree recursively (like a compiler AST visitor),
    generating MongoDB query structure by visiting each node type.

    Features:
    - Field projection (SELECT → projection dict)
    - Filters (WHERE → filter dict with $operators)
    - Sorting (ORDER BY → sort list)
    - Limit (LIMIT → limit int)
    - Logical operators (AND/OR → $and/$or)

    Limitations:
    - No JOIN support (MongoDB doesn't have traditional JOINs)
    - For JOINs, would need $lookup aggregation pipeline (future)
    """

    def __init__(self):
        """Initialize MongoDB builder."""
        pass

    def build(self, query_ir: QueryIR) -> GenericQueryResult:
        """Build MongoDB query from IR.

        Entry point - starts tree walking.

        Args:
            query_ir: Validated intermediate representation

        Returns:
            GenericQueryResult with MongoDB query structure

        Raises:
            UnsupportedFeatureError: If IR uses unsupported features
            QueryBuildError: If query cannot be built
        """
        # Validate IR against capabilities
        self.validate_ir(query_ir)

        # Visit IR tree recursively
        mongo_query = self.visit_query(query_ir)

        return GenericQueryResult(
            database_type="mongodb",
            query=mongo_query,
            metadata={
                "builder": "MongoDBBuilder",
                "driver": "pymongo"
            }
        )

    def get_capabilities(self) -> QueryCapabilities:
        """Get MongoDB capabilities.

        MongoDB limitations:
        - No native JOINs (would need $lookup aggregation)
        - LIKE operator translated to $regex
        - No subqueries in current implementation

        Returns:
            QueryCapabilities with MongoDB feature support
        """
        return QueryCapabilities(
            supports_joins=False,  # No JOINs without $lookup
            supports_complex_filters=True,
            supports_aggregates=False,  # Not yet implemented
            supports_subqueries=False,  # Not yet implemented
            max_join_depth=None,
            supported_operators={"=", "!=", ">", ">=", "<", "<=", "IN", "LIKE"}
        )

    def visit_query(self, node: QueryIR) -> Dict[str, Any]:
        """Visit a QueryIR node.

        This is the main recursive entry point.

        Args:
            node: QueryIR node to visit

        Returns:
            Complete MongoDB query structure
        """
        query = {}

        # Collection name (table → collection)
        query["collection"] = node.source.table

        # Filter (WHERE clause)
        if node.filters:
            query["filter"] = self.visit_filter(node.filters)
        else:
            query["filter"] = {}

        # Projection (SELECT fields)
        query["projection"] = self.visit_projection(node.fields)

        # Sort (ORDER BY)
        if node.order_by:
            query["sort"] = self.visit_sort(node.order_by)
        else:
            query["sort"] = None

        # Limit
        query["limit"] = node.limit

        return query

    def visit_projection(self, fields: List[FieldExpr]) -> Optional[Dict[str, int]]:
        """Visit SELECT clause (projection in MongoDB).

        Args:
            fields: List of field expressions

        Returns:
            Projection dict or None for all fields
        """
        # Check if wildcard
        if len(fields) == 1 and fields[0].field == "*":
            # SELECT * → no projection (return all fields)
            return None

        # Build projection dict
        projection = {}

        for field in fields:
            if field.field == "*":
                # Can't mix * with other fields
                if len(fields) > 1:
                    raise QueryBuildError(
                        "Cannot mix wildcard (*) with specific fields in MongoDB"
                    )
                return None

            # Include field in projection
            # MongoDB: 1 = include, 0 = exclude
            projection[field.field] = 1

        # Always exclude _id unless explicitly requested
        if "_id" not in projection:
            projection["_id"] = 0

        return projection

    def visit_filter(self, expr: FilterExpr) -> Dict[str, Any]:
        """Visit a filter expression.

        Dispatches to specific visitor based on expression type.
        This enables recursion for nested logical expressions.

        Args:
            expr: Filter expression (ConditionExpr or LogicalExpr)

        Returns:
            MongoDB filter dict

        Raises:
            QueryBuildError: If expression type is unknown
        """
        if isinstance(expr, ConditionExpr):
            return self.visit_condition(expr)
        elif isinstance(expr, LogicalExpr):
            return self.visit_logical(expr)
        else:
            raise QueryBuildError(f"Unknown filter expression type: {type(expr)}")

    def visit_condition(self, cond: ConditionExpr) -> Dict[str, Any]:
        """Visit a condition expression.

        Translates SQL operators to MongoDB operators.

        Args:
            cond: Condition expression to visit

        Returns:
            MongoDB condition dict

        Examples:
            age > 18 → {"age": {"$gt": 18}}
            status = "active" → {"status": "active"}
            name LIKE "%john%" → {"name": {"$regex": ".*john.*"}}
        """
        field = cond.field
        op = cond.op
        value = cond.value

        # Map SQL operators to MongoDB operators
        if op == "=":
            # Direct equality
            return {field: value}

        elif op == "!=":
            return {field: {"$ne": value}}

        elif op == ">":
            return {field: {"$gt": value}}

        elif op == ">=":
            return {field: {"$gte": value}}

        elif op == "<":
            return {field: {"$lt": value}}

        elif op == "<=":
            return {field: {"$lte": value}}

        elif op == "IN":
            return {field: {"$in": value}}

        elif op == "LIKE":
            # Convert SQL LIKE to MongoDB $regex
            # SQL: "john%" → Regex: "^john"
            # SQL: "%john" → Regex: "john$"
            # SQL: "%john%" → Regex: ".*john.*"
            regex_value = self._like_to_regex(value)
            return {field: {"$regex": regex_value, "$options": "i"}}  # case-insensitive

        else:
            raise QueryBuildError(f"Unsupported operator for MongoDB: {op}")

    def visit_logical(self, expr: LogicalExpr) -> Dict[str, Any]:
        """Visit a logical expression (AND/OR).

        Recursively visits sub-conditions, enabling nested logic.

        Args:
            expr: Logical expression to visit

        Returns:
            MongoDB logical operator dict

        Examples:
            AND → {"$and": [cond1, cond2]}
            OR → {"$or": [cond1, cond2]}
        """
        logic_op = expr.logic  # "AND" or "OR"

        # Recursively visit each sub-condition
        sub_conditions = [self.visit_filter(cond) for cond in expr.conditions]

        # MongoDB logical operators
        if logic_op == "AND":
            # Optimization: if simple conditions, merge into single dict
            # {"$and": [{"age": 18}, {"status": "active"}]} → {"age": 18, "status": "active"}
            if all(len(c) == 1 and "$" not in list(c.keys())[0] for c in sub_conditions):
                merged = {}
                for cond in sub_conditions:
                    merged.update(cond)
                return merged
            else:
                return {"$and": sub_conditions}

        elif logic_op == "OR":
            return {"$or": sub_conditions}

        else:
            raise QueryBuildError(f"Unsupported logical operator: {logic_op}")

    def visit_sort(self, order_by: List[OrderExpr]) -> List[Tuple[str, int]]:
        """Visit ORDER BY clause (sort in MongoDB).

        Args:
            order_by: List of order expressions

        Returns:
            List of (field, direction) tuples
            Direction: 1 = ASC, -1 = DESC

        Example:
            ORDER BY created_at DESC → [("created_at", -1)]
        """
        sort = []

        for expr in order_by:
            field = expr.field
            direction = 1 if expr.direction == "ASC" else -1
            sort.append((field, direction))

        return sort

    def _like_to_regex(self, like_pattern: str) -> str:
        """Convert SQL LIKE pattern to MongoDB regex.

        Args:
            like_pattern: SQL LIKE pattern (with % and _)

        Returns:
            MongoDB regex pattern

        Examples:
            "john%" → "^john"
            "%john" → "john$"
            "%john%" → ".*john.*"
            "j_hn" → "j.hn"
        """
        # Escape special regex characters (except % and _)
        import re
        escaped = re.escape(like_pattern)

        # Convert SQL wildcards to regex
        # % (any characters) → .*
        # _ (single character) → .
        regex = escaped.replace(r"\%", ".*").replace(r"\_", ".")

        # Add anchors if needed
        if not regex.startswith(".*"):
            regex = "^" + regex
        if not regex.endswith(".*"):
            regex = regex + "$"

        # Clean up redundant anchors
        regex = regex.replace("^.*", "").replace(".*$", "")

        return regex if regex else ".*"


# Register with factory
from .factory import QueryBuilderFactory
QueryBuilderFactory.register("mongodb", MongoDBBuilder)
