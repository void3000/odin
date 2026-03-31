"""
SQL Query Builder.

Converts validated IR (Intermediate Representation) structures into executable SQL queries.
Supports SELECT statements with JOIN, WHERE, ORDER BY, and LIMIT clauses.
"""

import json
import logging
from typing import Any, Dict, List, Tuple, Union

from src.ir.models import (
    ConditionExpr, FilterExpr, JoinExpr, LogicalExpr, OrderExpr, QueryIR,
    TableSource
)
from src.logging_config import get_component_logger

logger = get_component_logger("query_builder")


class SQLBuilder:
    """
    Builds SQL queries from IR structures.
    
    Supports:
        - SELECT with field aliases and table qualification
        - JOIN (INNER, LEFT, RIGHT)
        - WHERE with AND/OR conditions
        - ORDER BY multiple fields
        - LIMIT
    """
    
    def build(self, query_ir: QueryIR) -> Tuple[str, List[Any]]:
        """
        Build a SQL query and parameters from an IR structure.
        
        Args:
            query_ir: The parsed query to convert to SQL
            
        Returns:
            Tuple of (sql_string, parameters_list)
        """
        logger.info(f"Building SQL for query on table: {query_ir.source.table}")
        logger.debug("QueryIR:\n%s", json.dumps(query_ir.model_dump(), indent=2, default=str))
        
        # Build SELECT clause
        select_clause = self._build_select(query_ir.fields)
        from_clause = self._build_from(query_ir.source)
        
        # Build JOIN clauses if present
        join_clauses = []
        params: List[Any] = []
        if query_ir.joins:
            for join in query_ir.joins:
                clause, join_params = self._build_join(join)
                join_clauses.append(clause)
                params.extend(join_params)
        
        # Build WHERE clause if present
        where_clause = None
        if query_ir.filters:
            where_clause, filter_params = self._build_where(query_ir.filters)
            params.extend(filter_params)
        
        # Build ORDER BY clause if present
        order_clause = None
        if query_ir.order_by:
            order_clause = self._build_order_by(query_ir.order_by)
        
        # Build LIMIT clause if present
        limit_clause = f"LIMIT {query_ir.limit}" if query_ir.limit else None
        
        # Assemble complete query
        sql_parts = [select_clause, from_clause]
        if join_clauses:
            sql_parts.extend(join_clauses)
        if where_clause:
            sql_parts.append(where_clause)
        if order_clause:
            sql_parts.append(order_clause)
        if limit_clause:
            sql_parts.append(limit_clause)
        
        sql = " ".join(sql_parts) + ";"
        
        logger.debug(f"Generated SQL: {sql}")
        logger.info(f"SQL built successfully with {len(params)} parameters")
        
        return sql, params
    
    def _build_select(self, fields: List[Any]) -> str:
        """Build SELECT clause."""
        select_parts = []
        for field in fields:
            if field.field == "*":
                select_parts.append("*")
            else:
                # Build qualified column name
                col_name = f"{field.table}.{field.field}" if field.table else field.field
                # Add alias if specified
                if field.alias:
                    select_parts.append(f"{col_name} AS {field.alias}")
                else:
                    select_parts.append(col_name)
        
        return f"SELECT {', '.join(select_parts)}"
    
    def _build_from(self, source: TableSource) -> str:
        """Build FROM clause."""
        table = source.table
        if source.alias:
            return f"FROM {table} AS {source.alias}"
        return f"FROM {table}"
    
    def _build_join(self, join: JoinExpr) -> Tuple[str, List[Any]]:
        """Build JOIN clause."""
        params = []
        join_type = join.type
        table = join.table
        
        # Build ON condition
        on_clause, on_params = self._build_condition(join.on)
        params.extend(on_params)
        
        return f"{join_type} JOIN {table} ON {on_clause}", params
    
    def _build_where(self, filter_expr: FilterExpr) -> Tuple[str, List[Any]]:
        """Build WHERE clause."""
        condition_sql, params = self._build_condition(filter_expr)
        return f"WHERE {condition_sql}", params
    
    def _build_condition(self, expr: Union[ConditionExpr, LogicalExpr]) -> Tuple[str, List[Any]]:
        """Build a single or compound condition."""
        if isinstance(expr, ConditionExpr):
            return self._build_single_condition(expr)
        elif isinstance(expr, LogicalExpr):
            return self._build_logical_condition(expr)
    
    def _build_single_condition(self, cond: ConditionExpr) -> Tuple[str, List[Any]]:
        """Build a single condition."""
        params = []
        field_name = f"{cond.table}.{cond.field}" if cond.table else cond.field
        
        # Handle different operators
        if cond.op == "IN":
            placeholders = ", ".join("?" for _ in cond.value)
            clause = f"{field_name} IN ({placeholders})"
            params.extend(cond.value)
        elif cond.op == "LIKE":
            # Handle dict value (field reference) or literal
            if isinstance(cond.value, dict):
                ref_field = f"{cond.value['table']}.{cond.value['field']}" \
                           if cond.value.get('table') else cond.value['field']
                clause = f"{field_name} LIKE {ref_field}"
            else:
                clause = f"{field_name} LIKE ?"
                params.append(cond.value)
        elif isinstance(cond.value, dict):
            # Field reference (e.g., for JOIN conditions)
            ref_field = f"{cond.value['table']}.{cond.value['field']}" \
                       if cond.value.get('table') else cond.value['field']
            clause = f"{field_name} {cond.op} {ref_field}"
        else:
            # Literal value
            clause = f"{field_name} {cond.op} ?"
            params.append(cond.value)
        
        return clause, params
    
    def _build_logical_condition(self, logical: LogicalExpr) -> Tuple[str, List[Any]]:
        """Build a compound AND/OR condition."""
        all_params = []
        conditions = []
        
        for sub_cond in logical.conditions:
            clause, params = self._build_condition(sub_cond)
            conditions.append(clause)
            all_params.extend(params)
        
        combined = f" {logical.logic} ".join(conditions)
        if len(logical.conditions) > 1:
            combined = f"({combined})"
        
        return combined, all_params
    
    def _build_order_by(self, order_exprs: List[OrderExpr]) -> str:
        """Build ORDER BY clause."""
        order_parts = []
        for expr in order_exprs:
            col_name = f"{expr.table}.{expr.field}" if expr.table else expr.field
            direction = expr.direction
            order_parts.append(f"{col_name} {direction}")
        
        return f"ORDER BY {', '.join(order_parts)}"
