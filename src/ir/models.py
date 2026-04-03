"""
IR (Intermediate Representation) models for SQL queries.

These Pydantic models define the structure of parsed natural language queries,
serving as an intermediate representation before SQL generation.
"""

from __future__ import annotations
import logging
from enum import Enum
from typing import Any, List, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

# Import logging configuration
from src.logging_config import get_component_logger

logger = get_component_logger("ir")


class TableSource(BaseModel):
    """
    Represents a table reference in the query.
    
    Attributes:
        table: The table name to query from
        alias: Optional alias for the table (e.g., SELECT u.name FROM users AS u)
    """
    table: str = Field(..., description="Table name")
    alias: str | None = Field(None, description="Optional table alias")

    @field_validator("table")
    @classmethod
    def validate_table_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Table name cannot be empty")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"table": "users"},
                {"table": "orders", "alias": "o"}
            ]
        }
    }


class FieldExpr(BaseModel):
    """
    Represents a field/column in the SELECT clause.
    
    Attributes:
        field: The column name (use "*" for wildcard)
        table: Optional table qualifier for disambiguation
        alias: Optional alias for the selected field
    """
    field: str = Field(..., description="Column name or * for all columns")
    table: str | None = Field(None, description="Table name if field needs qualification")
    alias: str | None = Field(None, description="Alias for the selected column")
    function: Literal["COUNT", "SUM", "AVG", "MIN", "MAX"] | None = Field(
        None, description="Aggregate function to apply (COUNT, SUM, AVG, MIN, MAX)"
    )

    @field_validator("field")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        if v != "*" and not v.strip():
            raise ValueError("Field name cannot be empty (use * for wildcard)")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"field": "name"},
                {"field": "*"},
                {"field": "total", "table": "orders", "alias": "order_total"}
            ]
        }
    }


class ConditionExpr(BaseModel):
    """
    Represents a single condition in the WHERE clause.
    
    Attributes:
        field: The column name to compare
        table: Optional table qualifier
        op: Comparison operator (=, !=, >, >=, <, <=, LIKE, IN)
        value: The value to compare against (can be literal or field reference)
    """
    field: str = Field(..., description="Column name")
    table: str | None = Field(None, description="Table name if needed")
    op: Literal["=", "!=", ">", ">=", "<", "<=", "LIKE", "IN"] = Field(...)
    value: Union[str, int, float, List[Union[str, int, float]], dict] = Field(...)

    @field_validator("field")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Condition field cannot be empty")
        return v.strip()

    @field_validator("value")
    @classmethod  
    def validate_value_for_operator(cls, v: Any, info) -> Any:
        op = info.data.get("op")
        if op == "IN":
            if not isinstance(v, list):
                raise ValueError("IN operator requires a list value")
            if len(v) == 0:
                raise ValueError("IN operator requires at least one value in the list")
        elif op != "LIKE" and isinstance(v, dict):
            # Allow dict for field references (e.g., {"field": "id", "table": "users"})
            pass
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"field": "status", "op": "=", "value": "active"},
                {"field": "age", "op": ">=", "value": 18},
                {"field": "name", "op": "LIKE", "value": "%john%"},
                {"field": "status", "op": "IN", "value": ["active", "pending"]}
            ]
        }
    }


class LogicalExpr(BaseModel):
    """
    Represents a compound condition using AND/OR logic.
    
    Attributes:
        logic: The logical operator (AND or OR)
        conditions: List of conditions (ConditionExpr or nested LogicalExpr)
    """
    logic: Literal["AND", "OR"] = Field(..., description="Logical operator")
    conditions: List[Union["ConditionExpr", "LogicalExpr"]] = Field(
        ..., min_length=2, description="Conditions to combine"
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
                        {"field": "type", "op": "=", "value": "premium"},
                        {"field": "total_spend", "op": ">", "value": 1000}
                    ]
                }
            ]
        }
    }


class JoinExpr(BaseModel):
    """
    Represents a JOIN clause in the query.
    
    Attributes:
        type: Type of join (INNER, LEFT, RIGHT)
        table: The table to join with
        on: Join condition (can be ConditionExpr or LogicalExpr)
    """
    type: Literal["INNER", "LEFT", "RIGHT"] = Field(..., description="Join type")
    table: str = Field(..., description="Table to join")
    on: Union[ConditionExpr, LogicalExpr] = Field(..., description="Join condition")

    @field_validator("table")
    @classmethod
    def validate_table_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Join table name cannot be empty")
        return v.strip()

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
                        "field": "id",
                        "table": "users",
                        "op": "=",
                        "value": {"field": "user_id", "table": "profiles"}
                    }
                }
            ]
        }
    }


class OrderExpr(BaseModel):
    """
    Represents an ORDER BY clause specification.
    
    Attributes:
        field: Column name to sort by
        table: Optional table qualifier
        direction: Sort direction (ASC or DESC)
    """
    field: str = Field(..., description="Column to order by")
    table: str | None = Field(None, description="Table name if needed")
    direction: Literal["ASC", "DESC"] = Field("ASC", description="Sort direction")

    @field_validator("field")
    @classmethod
    def validate_field_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Order field cannot be empty")
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"field": "created_at", "direction": "DESC"},
                {"field": "name", "direction": "ASC"},
                {"field": "total", "table": "orders", "direction": "DESC"}
            ]
        }
    }


class QueryIR(BaseModel):
    """
    Root structure representing a complete SQL query.

    This is the main IR structure that the LLM generates when converting
    natural language to SQL.
    
    Attributes:
        operation: Query operation (currently only SELECT is supported)
        source: Primary table to query
        fields: List of fields to retrieve
        joins: Optional list of table joins
        filters: Optional WHERE clause conditions (supports AND/OR trees)
        order_by: Optional sorting specifications
        limit: Optional row limit
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
        logger.debug(f"Validating QueryIR: source={self.source.table}, fields={len(self.fields)}")
        
        # If there are joins, ensure field references are qualified when needed
        if self.joins and len(self.joins) > 0:
            # Track all tables involved
            tables = {self.source.table}
            for join in self.joins:
                tables.add(join.table)

            # If multiple tables exist, warn about unqualified fields in complex queries
            if len(tables) > 1:
                # This is just a semantic check - we'll let the validator handle deeper checks
                logger.debug(f"Multi-table query detected: {tables}")
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
FilterExpr = Union[ConditionExpr, LogicalExpr]
