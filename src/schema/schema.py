"""
Database Schema Definition

Provides classes for defining database schemas that can be used for
IR validation and SQL generation.
"""

from typing import Dict, List, Set
from pydantic import BaseModel, Field


class ColumnDef(BaseModel):
    """Definition of a database column."""

    name: str = Field(..., description="Column name")
    type: str = Field(
        ...,
        description="Column type (int, float, str, bool, date, datetime, etc.)"
    )
    nullable: bool = Field(default=True, description="Whether the column can be NULL")
    primary_key: bool = Field(default=False, description="Whether this is a primary key")
    foreign_key: str | None = Field(
        None,
        description="Foreign key reference in format 'table.column'"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"name": "id", "type": "int", "primary_key": True, "nullable": False},
                {"name": "name", "type": "str", "nullable": False},
                {"name": "age", "type": "int"},
                {"name": "user_id", "type": "int", "foreign_key": "users.id"},
            ]
        }
    }


class TableDef(BaseModel):
    """Definition of a database table."""

    name: str = Field(..., description="Table name")
    columns: List[ColumnDef] = Field(..., description="List of column definitions")

    def get_column(self, name: str) -> ColumnDef | None:
        """Get a column by name."""
        for col in self.columns:
            if col.name == name:
                return col
        return None

    def get_column_type(self, name: str) -> str | None:
        """Get the type of a column by name."""
        col = self.get_column(name)
        return col.type if col else None

    def has_column(self, name: str) -> bool:
        """Check if a column exists in this table."""
        return self.get_column(name) is not None

    def get_primary_keys(self) -> List[str]:
        """Get list of primary key column names."""
        return [col.name for col in self.columns if col.primary_key]

    def get_foreign_keys(self) -> Dict[str, str]:
        """Get mapping of column names to their foreign key references."""
        return {
            col.name: col.foreign_key
            for col in self.columns
            if col.foreign_key
        }

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "users",
                    "columns": [
                        {"name": "id", "type": "int", "primary_key": True, "nullable": False},
                        {"name": "name", "type": "str", "nullable": False},
                        {"name": "email", "type": "str", "nullable": False},
                        {"name": "age", "type": "int"},
                        {"name": "status", "type": "str"},
                    ]
                }
            ]
        }
    }


class DatabaseSchema(BaseModel):
    """Complete database schema definition."""

    tables: List[TableDef] = Field(..., description="List of table definitions")

    def get_table(self, name: str) -> TableDef | None:
        """Get a table by name."""
        for table in self.tables:
            if table.name == name:
                return table
        return None

    def has_table(self, name: str) -> bool:
        """Check if a table exists in the schema."""
        return self.get_table(name) is not None

    def get_table_names(self) -> Set[str]:
        """Get set of all table names."""
        return {table.name for table in self.tables}

    def to_validator_schema(self) -> Dict[str, Dict[str, str]]:
        """
        Convert to the simplified schema format used by IRValidator.

        Returns:
            Dictionary mapping table names to field type dictionaries.
            Format: {"table_name": {"field_name": "field_type", ...}, ...}
        """
        result = {}
        for table in self.tables:
            result[table.name] = {col.name: col.type for col in table.columns}
        return result

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "tables": [
                        {
                            "name": "users",
                            "columns": [
                                {"name": "id", "type": "int", "primary_key": True, "nullable": False},
                                {"name": "name", "type": "str", "nullable": False},
                                {"name": "email", "type": "str", "nullable": False},
                                {"name": "tier", "type": "str"},
                            ]
                        },
                        {
                            "name": "orders",
                            "columns": [
                                {"name": "id", "type": "int", "primary_key": True, "nullable": False},
                                {"name": "user_id", "type": "int", "foreign_key": "users.id"},
                                {"name": "total", "type": "float"},
                                {"name": "status", "type": "str"},
                            ]
                        }
                    ]
                }
            ]
        }
    }


def create_schema_from_dict(schema_dict: Dict[str, Dict[str, str]]) -> DatabaseSchema:
    """
    Create a DatabaseSchema from a simplified dictionary format.

    Args:
        schema_dict: Dictionary in format {"table": {"field": "type", ...}, ...}

    Returns:
        DatabaseSchema instance
    """
    tables = []
    for table_name, fields in schema_dict.items():
        columns = [
            ColumnDef(name=field_name, type=field_type)
            for field_name, field_type in fields.items()
        ]
        tables.append(TableDef(name=table_name, columns=columns))

    return DatabaseSchema(tables=tables)
