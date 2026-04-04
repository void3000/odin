from src.sources.base import (
    SourceField,
    SourceCollection,
    SourceSchema,
    SourceCapabilities,
    QueryResult,
)


class TestSourceModels:
    def test_source_field(self):
        field = SourceField(name="id", type="int")
        assert field.name == "id"
        assert field.type == "int"
        assert field.description is None

    def test_source_field_with_description(self):
        field = SourceField(name="status", type="str", description="User status")
        assert field.description == "User status"

    def test_source_collection(self):
        col = SourceCollection(
            name="users",
            fields=[SourceField(name="id", type="int"), SourceField(name="name", type="str")],
        )
        assert col.name == "users"
        assert len(col.fields) == 2

    def test_source_schema(self):
        schema = SourceSchema(collections=[
            SourceCollection(name="users", fields=[SourceField(name="id", type="int")]),
            SourceCollection(name="orders", fields=[SourceField(name="total", type="float")]),
        ])
        assert len(schema.collections) == 2

    def test_source_capabilities_defaults(self):
        caps = SourceCapabilities()
        assert caps.supports_joins is False
        assert caps.supports_aggregates is False
        assert caps.supports_time_range is False
        assert caps.supports_full_text is False
        assert caps.supports_filters is True

    def test_source_capabilities_database(self):
        caps = SourceCapabilities(
            supports_joins=True,
            supports_aggregates=True,
            supported_operators={"=", "!=", ">", "<", ">=", "<=", "IN", "LIKE"},
        )
        assert caps.supports_joins is True
        assert "IN" in caps.supported_operators

    def test_query_result(self):
        result = QueryResult(
            rows=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            columns=["id", "name"],
            row_count=2,
            source_name="main_db",
        )
        assert result.row_count == 2
        assert result.source_name == "main_db"
        assert result.rows[0]["name"] == "Alice"
