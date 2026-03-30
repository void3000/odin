"""
Intermediate Representation (IR) module.

Provides data models, parsing, and validation for query IR.
"""

from .models import (
    QueryIR,
    TableSource,
    FieldExpr,
    JoinExpr,
    ConditionExpr,
    LogicalExpr,
    FilterExpr,
    OrderExpr,
)
from .parser import IRParser
from .validator import IRValidator

__all__ = [
    "QueryIR",
    "TableSource",
    "FieldExpr",
    "JoinExpr",
    "ConditionExpr",
    "LogicalExpr",
    "FilterExpr",
    "OrderExpr",
    "IRParser",
    "IRValidator",
]
