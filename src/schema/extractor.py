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
                for cid, col_name, col_type, not_null, default_val, is_pk in columns:
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

        if any(t in sqlite_type for t in ["INT", "INTEGER", "TINYINT", "SMALLINT", "MEDIUMINT", "BIGINT"]):
            return "int"

        if any(t in sqlite_type for t in ["REAL", "DOUBLE", "FLOAT", "NUMERIC", "DECIMAL"]):
            return "float"

        if "BOOL" in sqlite_type:
            return "bool"

        if "DATE" in sqlite_type:
            return "date"
        if "TIME" in sqlite_type or "TIMESTAMP" in sqlite_type:
            return "datetime"

        return "str"


class PostgreSQLSchemaExtractor:
    """Extract schema from PostgreSQL databases.

    Discovers all user-created schemas (excludes pg_* and information_schema).
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.schemas: List[str] = []

    def extract_schema(self) -> DatabaseSchema:
        import psycopg2

        conn = psycopg2.connect(self.connection_string)
        try:
            schemas = self._get_schemas(conn)
            self.schemas = schemas
            tables = self._get_tables(conn, schemas)
            table_defs = []

            for schema_name, table_name in tables:
                columns = self._get_columns(conn, schema_name, table_name)
                foreign_keys = self._get_foreign_keys(conn, schema_name, table_name)

                column_defs = []
                for col_name, col_type, is_nullable, is_pk in columns:
                    ir_type = self._map_type(col_type)
                    fk_ref = foreign_keys.get(col_name)

                    column_defs.append(ColumnDef(
                        name=col_name,
                        type=ir_type,
                        nullable=is_nullable,
                        primary_key=is_pk,
                        foreign_key=fk_ref,
                    ))

                table_defs.append(TableDef(name=table_name, columns=column_defs))

            return DatabaseSchema(tables=table_defs)
        finally:
            conn.close()

    def _get_schemas(self, conn) -> List[str]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name NOT LIKE 'pg_%%' "
            "AND schema_name != 'information_schema'"
        )
        schemas = [row[0] for row in cursor.fetchall()]
        cursor.close()
        return schemas

    def _get_tables(self, conn, schemas: List[str]) -> List[Tuple[str, str]]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema = ANY(%s) AND table_type = 'BASE TABLE'",
            (schemas,)
        )
        tables = [(row[0], row[1]) for row in cursor.fetchall()]
        cursor.close()
        return tables

    def _get_columns(self, conn, schema_name: str, table_name: str) -> List[Tuple]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT c.column_name, c.data_type, "
            "  c.is_nullable = 'YES', "
            "  EXISTS("
            "    SELECT 1 FROM information_schema.key_column_usage k "
            "    JOIN information_schema.table_constraints t "
            "      ON k.constraint_name = t.constraint_name "
            "      AND k.table_schema = t.table_schema "
            "    WHERE t.constraint_type = 'PRIMARY KEY' "
            "      AND k.table_name = c.table_name "
            "      AND k.column_name = c.column_name "
            "      AND k.table_schema = c.table_schema"
            "  ) "
            "FROM information_schema.columns c "
            "WHERE c.table_schema = %s AND c.table_name = %s "
            "ORDER BY c.ordinal_position",
            (schema_name, table_name)
        )
        rows = cursor.fetchall()
        cursor.close()
        return rows

    def _get_foreign_keys(self, conn, schema_name: str, table_name: str) -> Dict[str, str]:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT kcu.column_name, ccu.table_name, ccu.column_name "
            "FROM information_schema.key_column_usage kcu "
            "JOIN information_schema.referential_constraints rc "
            "  ON kcu.constraint_name = rc.constraint_name "
            "  AND kcu.constraint_schema = rc.constraint_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON rc.unique_constraint_name = ccu.constraint_name "
            "  AND rc.unique_constraint_schema = ccu.constraint_schema "
            "WHERE kcu.table_schema = %s AND kcu.table_name = %s",
            (schema_name, table_name)
        )
        fk_map = {}
        for from_col, to_table, to_col in cursor.fetchall():
            fk_map[from_col] = f"{to_table}.{to_col}"
        cursor.close()
        return fk_map

    def _map_type(self, pg_type: str) -> str:
        pg_type = pg_type.lower()

        if pg_type in ("integer", "bigint", "smallint", "serial", "bigserial"):
            return "int"
        if pg_type in ("real", "double precision", "numeric", "decimal", "money"):
            return "float"
        if pg_type == "boolean":
            return "bool"
        if pg_type == "date":
            return "date"
        if pg_type in ("timestamp without time zone", "timestamp with time zone"):
            return "datetime"

        return "str"
