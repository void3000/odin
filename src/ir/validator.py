"""
IR (Intermediate Representation) Validator.

Validates parsed queries against the database schema before SQL generation,
catching errors early and providing helpful feedback to users.
"""

import logging
from typing import Any, Dict, List, Set

from pydantic import ValidationError

from src.ir.models import (
    ConditionExpr, FilterExpr, JoinExpr, LogicalExpr, OrderExpr, QueryIR
)
from src.schema.extractor import SQLiteSchemaExtractor
from src.logging_config import get_component_logger

logger = get_component_logger("ir.validator")


class IRValidator:
    """
    Validates IR queries against the database schema.
    
    Ensures that all referenced tables, columns, and operators are valid
    before attempting SQL generation.
    """
    
    def __init__(self, schema: Dict[str, Any]):
        """
        Initialize validator with a parsed design document schema.
        
        Args:
            schema: Parsed design document containing table definitions
        """
        self.schema = schema
        self.tables: Set[str] = set(schema.keys())
        logger.debug(f"IRValidator initialized with {len(self.tables)} tables")
    
    def validate_query(self, query_ir: QueryIR) -> List[str]:
        """
        Validate a complete IR query against the schema.
        
        Args:
            query_ir: The parsed query to validate
            
        Returns:
            List of error messages (empty if validation passes)
        """
        errors = []
        logger.info(f"Validating query for table: {query_ir.source.table}")
        
        # Validate source table exists
        if query_ir.source.table not in self.tables:
            error_msg = f"Table '{query_ir.source.table}' does not exist. Available tables: {', '.join(sorted(self.tables))}"
            errors.append(error_msg)
            logger.error(error_msg)
            return errors  # Can't validate further without valid source table
        
        # Validate fields
        field_errors = self._validate_fields(query_ir.fields, query_ir.source.table)
        errors.extend(field_errors)
        
        # Validate joins
        if query_ir.joins:
            join_errors = self._validate_joins(query_ir.joins, query_ir.source.table)
            errors.extend(join_errors)
        
        # Validate filters
        if query_ir.filters:
            filter_errors = self._validate_filters(
                query_ir.filters,
                self._get_available_tables(query_ir.source.table, query_ir.joins or [])
            )
            errors.extend(filter_errors)
        
        # Validate order by
        if query_ir.order_by:
            order_errors = self._validate_order_by(
                query_ir.order_by,
                self._get_available_tables(query_ir.source.table, query_ir.joins or [])
            )
            errors.extend(order_errors)
        
        # Validate limit
        if query_ir.limit is not None and query_ir.limit < 1:
            error_msg = "Limit must be a positive integer >= 1"
            errors.append(error_msg)
            logger.error(error_msg)
        
        if errors:
            logger.warning(f"Validation failed with {len(errors)} error(s)")
        else:
            logger.info("Query validation passed")
        
        return errors
    
    def _validate_fields(self, fields: List[Any], source_table: str) -> List[str]:
        """Validate SELECT field references."""
        errors = []
        table_schema = self.schema.get(source_table, {})
        available_columns = set(table_schema.get("columns", {}).keys())
        
        for field in fields:
            if field.field == "*":
                continue  # Wildcard is always valid
            
            # Determine which table to check against
            target_table = field.table or source_table
            
            if target_table not in self.tables:
                error_msg = f"Field '{field.field}' references unknown table '{target_table}'"
                errors.append(error_msg)
                logger.error(error_msg)
                continue
            
            # Check if column exists in the specified table
            target_schema = self.schema.get(target_table, {})
            target_columns = set(target_schema.get("columns", {}).keys())
            
            if field.field not in target_columns:
                error_msg = f"Column '{field.field}' does not exist in table '{target_table}'. Available: {', '.join(sorted(target_columns))}"
                errors.append(error_msg)
                logger.error(error_msg)
        
        return errors
    
    def _validate_joins(self, joins: List[JoinExpr], source_table: str) -> List[str]:
        """Validate JOIN clauses."""
        errors = []
        available_tables = {source_table}
        
        for join in joins:
            # Check if joined table exists
            if join.table not in self.tables:
                error_msg = f"JOIN table '{join.table}' does not exist. Available tables: {', '.join(sorted(self.tables))}"
                errors.append(error_msg)
                logger.error(error_msg)
                continue
            
            # Validate join condition
            cond_errors = self._validate_filters(
                join.on,
                available_tables | {join.table}
            )
            errors.extend(cond_errors)
            
            # Add joined table to available tables for subsequent joins
            available_tables.add(join.table)
        
        return errors
    
    def _validate_filters(self, filter_expr: FilterExpr, available_tables: Set[str]) -> List[str]:
        """Recursively validate WHERE clause conditions."""
        errors = []
        logger.debug(f"Validating filter expression type: {type(filter_expr).__name__}")
        
        if isinstance(filter_expr, ConditionExpr):
            # Validate single condition
            target_table = filter_expr.table
            field_name = filter_expr.field
            
            # If no table specified, check all available tables
            if target_table is None:
                matching_tables = [t for t in available_tables 
                                  if self._column_exists(t, field_name)]
                if len(matching_tables) == 0:
                    error_msg = f"Column '{field_name}' not found in any available table: {', '.join(sorted(available_tables))}"
                    errors.append(error_msg)
                    logger.error(error_msg)
                elif len(matching_tables) > 1 and len(available_tables) > 1:
                    # Ambiguous column reference - warn but don't error
                    warning_msg = f"Column '{field_name}' exists in multiple tables: {', '.join(sorted(matching_tables))}. Consider qualifying with table name."
                    errors.append(warning_msg)
                    logger.warning(warning_msg)
            else:
                # Table is specified - validate it exists and has the column
                if target_table not in available_tables:
                    error_msg = f"Column '{field_name}' references table '{target_table}' which is not available in this query"
                    errors.append(error_msg)
                    logger.error(error_msg)
                elif not self._column_exists(target_table, field_name):
                    available_cols = set(self.schema.get(target_table, {}).get("columns", {}).keys())
                    error_msg = f"Column '{field_name}' does not exist in table '{target_table}'. Available: {', '.join(sorted(available_cols))}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            # Validate operator compatibility with column type
            self._validate_operator_type(filter_expr, target_table or list(available_tables)[0])
        
        elif isinstance(filter_expr, LogicalExpr):
            # Recursively validate nested conditions
            for condition in filter_expr.conditions:
                cond_errors = self._validate_filters(condition, available_tables)
                errors.extend(cond_errors)
        
        return errors
    
    def _validate_order_by(self, order_expressions: List[OrderExpr], available_tables: Set[str]) -> List[str]:
        """Validate ORDER BY clause."""
        errors = []
        
        for expr in order_expressions:
            target_table = expr.table
            field_name = expr.field
            
            if target_table is None:
                matching_tables = [t for t in available_tables 
                                  if self._column_exists(t, field_name)]
                if len(matching_tables) == 0:
                    error_msg = f"ORDER BY column '{field_name}' not found in any available table"
                    errors.append(error_msg)
                    logger.error(error_msg)
            else:
                if target_table not in available_tables:
                    error_msg = f"ORDER BY column '{field_name}' references unavailable table '{target_table}'"
                    errors.append(error_msg)
                    logger.error(error_msg)
                elif not self._column_exists(target_table, field_name):
                    available_cols = set(self.schema.get(target_table, {}).get("columns", {}).keys())
                    error_msg = f"ORDER BY column '{field_name}' does not exist in table '{target_table}'. Available: {', '.join(sorted(available_cols))}"
                    errors.append(error_msg)
                    logger.error(error_msg)
        
        return errors
    
    def _validate_operator_type(self, condition: ConditionExpr, table: str):
        """Validate that the operator is compatible with the column type."""
        schema = self.schema.get(table, {})
        columns = schema.get("columns", {})
        col_info = columns.get(condition.field, {})
        col_type = col_info.get("type", "").upper()
        
        logger.debug(f"Checking operator '{condition.op}' for column type '{col_type}'")
        
        # LIKE only works with string types
        if condition.op == "LIKE":
            if not any(t in col_type for t in ["CHAR", "VARCHAR", "TEXT"]):
                error_msg = f"LIKE operator requires a string column, but '{condition.field}' is {col_type}"
                logger.error(error_msg)
        
        # Comparison operators work best with numeric types
        if condition.op in (">", ">=", "<", "<="):
            if not any(t in col_type for t in ["INT", "BIGINT", "FLOAT", "DOUBLE", "DECIMAL"]):
                logger.warning(f"Comparison operator '{condition.op}' on non-numeric column '{condition.field}' ({col_type})")
        
        # IN operator validation
        if condition.op == "IN":
            if isinstance(condition.value, list) and len(condition.value) > 0:
                first_val = condition.value[0]
                val_type = type(first_val).__name__.upper()
                if any(t in col_type for t in ["INT", "BIGINT"]):
                    if not isinstance(first_val, (int, float)):
                        logger.warning(f"IN operator on numeric column '{condition.field}' with non-numeric value")
                elif any(t in col_type for t in ["CHAR", "VARCHAR", "TEXT"]):
                    if not isinstance(first_val, str):
                        logger.warning(f"IN operator on string column '{condition.field}' with non-string value")
    
    def _column_exists(self, table: str, column: str) -> bool:
        """Check if a column exists in a table."""
        schema = self.schema.get(table, {})
        columns = schema.get("columns", {})
        return column in columns
    
    def _get_available_tables(self, source_table: str, joins: List[JoinExpr] | None) -> Set[str]:
        """Get all tables available for field references."""
        tables = {source_table}
        if joins:
            for join in joins:
                tables.add(join.table)
        return tables
