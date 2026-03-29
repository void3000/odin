"""Pytest configuration and shared fixtures."""

import pytest
from src.schema import DatabaseSchema, TableDef, ColumnDef


@pytest.fixture
def sample_schema() -> DatabaseSchema:
    """Sample database schema for testing."""
    return DatabaseSchema(
        tables=[
            TableDef(
                name="users",
                columns=[
                    ColumnDef(name="id", type="int", primary_key=True, nullable=False),
                    ColumnDef(name="name", type="str", nullable=False),
                    ColumnDef(name="email", type="str", nullable=False),
                    ColumnDef(name="age", type="int"),
                    ColumnDef(name="status", type="str"),
                    ColumnDef(name="tier", type="str"),
                    ColumnDef(name="verified", type="bool"),
                ],
            ),
            TableDef(
                name="orders",
                columns=[
                    ColumnDef(name="id", type="int", primary_key=True, nullable=False),
                    ColumnDef(name="user_id", type="int", foreign_key="users.id"),
                    ColumnDef(name="total", type="float"),
                    ColumnDef(name="status", type="str"),
                    ColumnDef(name="created_at", type="datetime"),
                ],
            ),
            TableDef(
                name="products",
                columns=[
                    ColumnDef(name="id", type="int", primary_key=True, nullable=False),
                    ColumnDef(name="name", type="str", nullable=False),
                    ColumnDef(name="price", type="float"),
                    ColumnDef(name="category", type="str"),
                ],
            ),
        ]
    )


@pytest.fixture
def sample_schema_dict(sample_schema: DatabaseSchema) -> dict:
    """Sample schema in validator format."""
    return sample_schema.to_validator_schema()
