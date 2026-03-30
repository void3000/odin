"""
Query Executor.

Executes SQL queries against the database and returns results.
Handles connection management, error handling, and result formatting.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

import sqlite3

from src.logging_config import get_component_logger

logger = get_component_logger("executor")


class QueryExecutor:
    """
    Executes SQL queries against SQLite database.
    
    Handles:
        - Connection management
        - Query execution with parameter binding
        - Result formatting (dict or tuple)
        - Error handling and logging
    """
    
    def __init__(self, db_path: str):
        """
        Initialize executor with database path.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        logger.info(f"QueryExecutor initialized for database: {db_path}")
    
    def execute(
        self,
        sql: str,
        params: Optional[List[Any]] = None,
        return_format: str = "dict"
    ) -> Tuple[bool, Any]:
        """
        Execute a SQL query and return results.
        
        Args:
            sql: SQL query string
            params: Query parameters for parameterized queries
            return_format: "dict" for dict rows or "tuple" for tuple rows
            
        Returns:
            Tuple of (success, result_or_error_message)
        """
        logger.info(f"Executing query with {len(params) if params else 0} parameters")
        logger.debug(f"SQL: {sql}")
        logger.debug(f"Params: {params}")
        
        conn = None
        try:
            # Establish connection
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Set row factory for dict results
            if return_format == "dict":
                conn.row_factory = sqlite3.Row
            
            # Execute query
            logger.debug("Executing SQL...")
            cursor.execute(sql, params or [])
            
            # Fetch results
            rows = cursor.fetchall()
            
            # Format results based on return_format
            if return_format == "dict":
                results = [dict(row) for row in rows]
            else:
                results = [tuple(row) for row in rows]
            
            logger.info(f"Query executed successfully, returned {len(results)} row(s)")
            
            return True, results
            
        except sqlite3.Error as e:
            error_msg = f"Database error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error during query execution: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
            
        finally:
            if conn:
                conn.close()
                logger.debug("Database connection closed")
    
    def execute_with_schema(
        self,
        sql: str,
        params: Optional[List[Any]] = None,
        schema: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, Any]:
        """
        Execute query with optional schema for column information.
        
        Args:
            sql: SQL query string
            params: Query parameters
            schema: Database schema (optional)
            
        Returns:
            Tuple of (success, result_or_error_message)
        """
        success, results = self.execute(sql, params, return_format="dict")
        
        if success and isinstance(results, list) and len(results) > 0:
            # Add schema information to results
            column_info = []
            for col_name in results[0].keys():
                col_info.append({"name": col_name})
            
            return True, {
                "success": True,
                "data": results,
                "columns": column_info,
                "count": len(results)
            }
        
        return success, results
