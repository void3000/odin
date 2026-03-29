"""
Intermediate Representation (IR) Pydantic Models

These models define the structured format that the LLM outputs when converting
natural language queries to SQL. The IR is then deterministically translated
to SQL by the SQLBuilder.
"""

from typing import Literal, Union, List, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class TableSource(BaseModel):
    """Represents a table in the query."""

    table: str = Field(..., description="Name of the table", min_length=1)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"table": "users"},
                {"table": "orders"},
            ]
        }
    }


class FieldExpr(BaseModel):
    """Represents a field to be selected."""

    field: str = Field(..., description="Column name or '*' for all columns", min_length=1)
    table: str | None = Field(None, description="Table qualifier (required for joins)")
    alias: str | None = Field(None, description="Optional alias for the field (AS clause)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"field": "name"},
                {"field": "email", "table": "users"},
                {"field": "total_price", "alias": "price"},
                {"field": "*"},
            ]
        }
    }


class ConditionExpr(BaseModel):
    """Leaf condition for filters (WHERE clause) or joins (ON clause)."""

    field: str = Field(..., description="Column name to filter/join on", min_length=1)
    table: str | None = Field(None, description="Table qualifier (for joins)")
    op: Literal["=", "!=", ">", ">=", "<", "<=", "LIKE", "IN"] = Field(
        ..., description="Comparison operator"
    )
    value: Union[str, int, float, List[Union[str, int, float]], dict] = Field(
        ..., description="Value to compare against (or array for IN, or dict for field references)"
    )

    @field_validator("value")
    @classmethod
    def validate_value_for_operator(cls, v: Any, info) -> Any:
        """Validate that value type matches the operator."""
        op = info.data.get("op")

        # IN operator requires a list
        if op == "IN":
            if not isinstance(v, list):
                raise ValueError(f"IN operator requires a list value, got {type(v).__name__}")
            if len(v) == 0:
                raise ValueError("IN operator requires non-empty list")

        # Other operators should not have lists (unless it's a field reference)
        elif isinstance(v, list):
            raise ValueError(f"Operator {op} does not support list values")

        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"field": "status", "op": "=", "value": "active"},
                {"field": "age", "op": ">=", "value": 18},
                {"field": "email", "op": "LIKE", "value": "%@example.com"},
                {"field": "category", "op": "IN", "value": ["electronics", "books"]},
                {
                    "field": "id",
                    "table": "users",
                    "op": "=",
                    "value": {"field": "user_id", "table": "orders"}
                },
            ]
        }
    }


class LogicalExpr(BaseModel):
    """Logical node combining multiple filter conditions with AND/OR."""

    logic: Literal["AND", "OR"] = Field(..., description="Logical operator")
    conditions: List[Union["ConditionExpr", "LogicalExpr"]] = Field(
        ..., description="List of conditions (minimum 2)", min_length=2
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "logic": "AND",
                    "conditions": [
                        {"field": "status", "op": "=", "value": "active"},
                        {"field": "age", "op": ">=", "value": 18}
                    ]
                },
                {
                    "logic": "OR",
                    "conditions": [
                        {"field": "role", "op": "=", "value": "admin"},
                        {
                            "logic": "AND",
                            "conditions": [
                                {"field": "status", "op": "=", "value": "active"},
                                {"field": "verified", "op": "=", "value": True}
                            ]
                        }
                    ]
                }
            ]
        }
    }


# FilterExpr is a union type that can be either a leaf condition or a logical expression
FilterExpr = Union[ConditionExpr, LogicalExpr]


class JoinExpr(BaseModel):
    """Represents a JOIN operation."""

    type: Literal["INNER", "LEFT", "RIGHT"] = Field(..., description="Type of join")
    table: str = Field(..., description="Table to join", min_length=1)
    on: ConditionExpr = Field(..., description="Join condition (must be a ConditionExpr)")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "INNER",
                    "table": "orders",
                    "on": {
                        "field": "id",
                        "table": "users",
                        "op": "=",
                        "value": {"field": "user_id", "table": "orders"}
                    }
                },
                {
                    "type": "LEFT",
                    "table": "profiles",
                    "on": {
                        "field": "user_id",
                        "table": "profiles",
                        "op": "=",
                        "value": {"field": "id", "table": "users"}
                    }
                }
            ]
        }
    }


class OrderExpr(BaseModel):
    """Represents an ORDER BY clause."""

    field: str = Field(..., description="Column name to sort by", min_length=1)
    table: str | None = Field(None, description="Table qualifier (for joins)")
    direction: Literal["ASC", "DESC"] = Field(..., description="Sort direction")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"field": "created_at", "direction": "DESC"},
                {"field": "name", "direction": "ASC"},
                {"field": "total", "table": "orders", "direction": "DESC"},
            ]
        }
    }


class QueryIR(BaseModel):
    """
    Root structure representing a complete SQL query.

    This is the main IR structure that the LLM generates when converting
    natural language to SQL.
    """

    operation: Literal["SELECT"] = Field(
        ..., description="Query operation (currently only SELECT is supported)"
    )
    source: TableSource = Field(..., description="Primary table to query")
    fields: List[FieldExpr] = Field(
        ..., description="List of fields to retrieve", min_length=1
    )
    joins: List[JoinExpr] | None = Field(None, description="Optional list of table joins")
    filters: FilterExpr | None = Field(
        None, description="Optional WHERE clause conditions (supports AND/OR trees)"
    )
    order_by: List[OrderExpr] | None = Field(None, description="Optional sorting specifications")
    limit: int | None = Field(None, description="Optional row limit", ge=1)

    @model_validator(mode="after")
    def validate_query(self) -> "QueryIR":
        """Additional validation for the complete query."""
        # If there are joins, ensure field references are qualified when needed
        if self.joins and len(self.joins) > 0:
            # Track all tables involved
            tables = {self.source.table}
            for join in self.joins:
                tables.add(join.table)

            # If multiple tables exist, warn about unqualified fields in complex queries
            if len(tables) > 1:
                # This is just a semantic check - we'll let the validator handle deeper checks
                pass

        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                # Simple query
                {
                    "operation": "SELECT",
                    "source": {"table": "users"},
                    "fields": [{"field": "*"}],
                    "filters": {"field": "status", "op": "=", "value": "active"}
                },
                # Query with join
                {
                    "operation": "SELECT",
                    "source": {"table": "users"},
                    "fields": [
                        {"field": "name", "table": "users"},
                        {"field": "total", "table": "orders", "alias": "order_total"}
                    ],
                    "joins": [
                        {
                            "type": "INNER",
                            "table": "orders",
                            "on": {
                                "field": "id",
                                "table": "users",
                                "op": "=",
                                "value": {"field": "user_id", "table": "orders"}
                            }
                        }
                    ],
                    "filters": {
                        "logic": "AND",
                        "conditions": [
                            {"field": "tier", "table": "users", "op": "=", "value": "premium"},
                            {"field": "total", "table": "orders", "op": ">", "value": 100}
                        ]
                    },
                    "order_by": [
                        {"field": "created_at", "table": "orders", "direction": "DESC"}
                    ],
                    "limit": 10
                }
            ]
        }
    }


# Update forward references for recursive models
LogicalExpr.model_rebuild()
