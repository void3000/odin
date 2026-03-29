"""
Schema Extractor - Extract database schema from live databases.

This module provides utilities to introspect database schemas from
SQLite, PostgreSQL, and other databases.
"""
import sqlite3
from typing import Dict, List, Tuple
from src.schema.schema import DatabaseSchema, TableDef, ColumnDef


class SQLiteSchemaExtractor:
    """Extract schema from SQLite databases."""

    def __init__(self, database_path: str):
        """
        Initialize schema extractor.

        Args:
            database_path: Path to SQLite database file
        """
        self.database_path = database_path

    def extract_schema(self) -> DatabaseSchema:
        """
        Extract complete database schema.

        Returns:
            DatabaseSchema with all tables and columns
        """
        conn = sqlite3.connect(self.database_path)
        try:
            tables = self._get_tables(conn)
            table_defs = []

            for table_name in tables:
                columns = self._get_columns(conn, table_name)
                foreign_keys = self._get_foreign_keys(conn, table_name)

                column_defs = []
                for col_name, col_type, not_null, default_val, is_pk in columns:
                    # Map SQLite types to IR types
                    ir_type = self._map_type(col_type)

                    # Check if this column has a foreign key
                    fk_ref = foreign_keys.get(col_name)

                    column_defs.append(ColumnDef(
                        name=col_name,
                        type=ir_type,
                        nullable=not not_null,
                        primary_key=bool(is_pk),
                        foreign_key=fk_ref
                    ))

                table_defs.append(TableDef(name=table_name, columns=column_defs))

            return DatabaseSchema(tables=table_defs)

        finally:
            conn.close()

    def _get_tables(self, conn: sqlite3.Connection) -> List[str]:
        """Get list of all table names."""
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in cursor.fetchall()]

    def _get_columns(self, conn: sqlite3.Connection, table_name: str) -> List[Tuple]:
        """Get column information for a table."""
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        # Returns: (cid, name, type, notnull, dflt_value, pk)
        return cursor.fetchall()

    def _get_foreign_keys(self, conn: sqlite3.Connection, table_name: str) -> Dict[str, str]:
        """Get foreign key mappings for a table."""
        cursor = conn.execute(f"PRAGMA foreign_key_list({table_name})")
        # Returns: (id, seq, table, from, to, on_update, on_delete, match)
        fk_map = {}
        for row in cursor.fetchall():
            from_col = row[3]
            to_table = row[2]
            to_col = row[4]
            fk_map[from_col] = f"{to_table}.{to_col}"
        return fk_map

    def _map_type(self, sqlite_type: str) -> str:
        """Map SQLite type to IR type."""
        if not sqlite_type:
            return "str"

        sqlite_type = sqlite_type.upper()

        # Integer types
        if any(t in sqlite_type for t in ["INT", "INTEGER", "TINYINT", "SMALLINT", "MEDIUMINT", "BIGINT"]):
            return "int"

        # Float types
        if any(t in sqlite_type for t in ["REAL", "DOUBLE", "FLOAT", "NUMERIC", "DECIMAL"]):
            return "float"

        # Boolean
        if "BOOL" in sqlite_type:
            return "bool"

        # Date/Time
        if "DATE" in sqlite_type:
            return "date"
        if "TIME" in sqlite_type or "TIMESTAMP" in sqlite_type:
            return "datetime"

        # Default to string
        return "str"
