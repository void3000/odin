"""Tests for schema definition module."""

import pytest

from src.schema import (
    ColumnDef,
    TableDef,
    DatabaseSchema,
    create_schema_from_dict,
)


class TestColumnDef:
    """Tests for ColumnDef model."""

    def test_simple_column(self):
        """Test creating a simple column."""
        col = ColumnDef(name="id", type="int")
        assert col.name == "id"
        assert col.type == "int"
        assert col.nullable is True
        assert col.primary_key is False

    def test_primary_key_column(self):
        """Test primary key column."""
        col = ColumnDef(name="id", type="int", primary_key=True, nullable=False)
        assert col.primary_key is True
        assert col.nullable is False

    def test_foreign_key_column(self):
        """Test foreign key column."""
        col = ColumnDef(name="user_id", type="int", foreign_key="users.id")
        assert col.foreign_key == "users.id"


class TestTableDef:
    """Tests for TableDef model."""

    def test_simple_table(self):
        """Test creating a simple table."""
        table = TableDef(
            name="users",
            columns=[
                ColumnDef(name="id", type="int", primary_key=True),
                ColumnDef(name="name", type="str"),
            ]
        )
        assert table.name == "users"
        assert len(table.columns) == 2

    def test_get_column(self):
        """Test getting a column by name."""
        table = TableDef(
            name="users",
            columns=[
                ColumnDef(name="id", type="int"),
                ColumnDef(name="name", type="str"),
            ]
        )
        col = table.get_column("name")
        assert col is not None
        assert col.name == "name"
        assert col.type == "str"

    def test_get_column_not_found(self):
        """Test getting non-existent column returns None."""
        table = TableDef(name="users", columns=[])
        col = table.get_column("nonexistent")
        assert col is None

    def test_get_column_type(self):
        """Test getting column type."""
        table = TableDef(
            name="users",
            columns=[ColumnDef(name="age", type="int")]
        )
        col_type = table.get_column_type("age")
        assert col_type == "int"

    def test_has_column(self):
        """Test checking if column exists."""
        table = TableDef(
            name="users",
            columns=[ColumnDef(name="email", type="str")]
        )
        assert table.has_column("email") is True
        assert table.has_column("nonexistent") is False

    def test_get_primary_keys(self):
        """Test getting primary key columns."""
        table = TableDef(
            name="users",
            columns=[
                ColumnDef(name="id", type="int", primary_key=True),
                ColumnDef(name="name", type="str"),
            ]
        )
        pks = table.get_primary_keys()
        assert pks == ["id"]

    def test_get_foreign_keys(self):
        """Test getting foreign key mappings."""
        table = TableDef(
            name="orders",
            columns=[
                ColumnDef(name="id", type="int", primary_key=True),
                ColumnDef(name="user_id", type="int", foreign_key="users.id"),
            ]
        )
        fks = table.get_foreign_keys()
        assert fks == {"user_id": "users.id"}


class TestDatabaseSchema:
    """Tests for DatabaseSchema model."""

    def test_simple_schema(self):
        """Test creating a simple database schema."""
        schema = DatabaseSchema(
            tables=[
                TableDef(
                    name="users",
                    columns=[ColumnDef(name="id", type="int")]
                )
            ]
        )
        assert len(schema.tables) == 1

    def test_get_table(self):
        """Test getting a table by name."""
        schema = DatabaseSchema(
            tables=[
                TableDef(name="users", columns=[]),
                TableDef(name="orders", columns=[]),
            ]
        )
        table = schema.get_table("users")
        assert table is not None
        assert table.name == "users"

    def test_get_table_not_found(self):
        """Test getting non-existent table returns None."""
        schema = DatabaseSchema(tables=[])
        table = schema.get_table("nonexistent")
        assert table is None

    def test_has_table(self):
        """Test checking if table exists."""
        schema = DatabaseSchema(
            tables=[TableDef(name="users", columns=[])]
        )
        assert schema.has_table("users") is True
        assert schema.has_table("nonexistent") is False

    def test_get_table_names(self):
        """Test getting all table names."""
        schema = DatabaseSchema(
            tables=[
                TableDef(name="users", columns=[]),
                TableDef(name="orders", columns=[]),
                TableDef(name="products", columns=[]),
            ]
        )
        names = schema.get_table_names()
        assert names == {"users", "orders", "products"}

    def test_to_validator_schema(self):
        """Test converting to validator schema format."""
        schema = DatabaseSchema(
            tables=[
                TableDef(
                    name="users",
                    columns=[
                        ColumnDef(name="id", type="int"),
                        ColumnDef(name="name", type="str"),
                    ]
                ),
                TableDef(
                    name="orders",
                    columns=[
                        ColumnDef(name="id", type="int"),
                        ColumnDef(name="total", type="float"),
                    ]
                ),
            ]
        )
        validator_schema = schema.to_validator_schema()
        assert validator_schema == {
            "users": {"id": "int", "name": "str"},
            "orders": {"id": "int", "total": "float"},
        }


class TestCreateSchemaFromDict:
    """Tests for create_schema_from_dict helper."""

    def test_create_simple_schema(self):
        """Test creating schema from dictionary."""
        schema_dict = {
            "users": {"id": "int", "name": "str"},
            "orders": {"id": "int", "total": "float"},
        }
        schema = create_schema_from_dict(schema_dict)
        assert len(schema.tables) == 2
        assert schema.has_table("users")
        assert schema.has_table("orders")

    def test_created_schema_matches_dict(self):
        """Test that created schema converts back to matching dict."""
        schema_dict = {
            "users": {"id": "int", "name": "str", "email": "str"},
        }
        schema = create_schema_from_dict(schema_dict)
        validator_schema = schema.to_validator_schema()
        assert validator_schema == schema_dict

    def test_roundtrip_conversion(self):
        """Test roundtrip conversion: dict -> schema -> dict."""
        original = {
            "users": {"id": "int", "name": "str"},
            "orders": {"id": "int", "user_id": "int", "total": "float"},
        }
        schema = create_schema_from_dict(original)
        result = schema.to_validator_schema()
        assert result == original
