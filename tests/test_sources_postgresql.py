from unittest.mock import MagicMock, patch
from src.sources.postgresql import PostgreSQLSource, SQLNativeQuery
from src.sources.base import SourceSchema, SourceCapabilities, QueryResult, DataSource
from src.ir.models import QueryIR, TableSource, FieldExpr, ConditionExpr


class TestPostgreSQLSource:
    def test_implements_datasource_protocol(self):
        source = PostgreSQLSource(name="test_db", url="postgresql://localhost/test")
        assert isinstance(source, DataSource)

    def test_name_and_type(self):
        source = PostgreSQLSource(name="main_db", url="postgresql://localhost/test")
        assert source.name == "main_db"
        assert source.source_type == "database"

    def test_get_capabilities(self):
        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        caps = source.get_capabilities()
        assert isinstance(caps, SourceCapabilities)
        assert caps.supports_joins is True
        assert caps.supports_aggregates is True
        assert caps.supports_time_range is False

    def test_build_query_returns_native_query(self):
        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10,
        )
        query = source.build_query(ir)
        assert isinstance(query, SQLNativeQuery)
        assert "users" in query.sql.lower() or "users" in query.sql
        assert isinstance(query.params, list)

    def test_build_query_with_filter(self):
        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="name")],
            filters=ConditionExpr(field="status", op="=", value="active"),
            limit=10,
        )
        query = source.build_query(ir)
        assert isinstance(query, SQLNativeQuery)
        assert len(query.params) >= 1

    @patch("src.sources.postgresql.create_connector")
    def test_connect_and_disconnect(self, mock_create):
        mock_connector = MagicMock()
        mock_create.return_value = mock_connector
        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        source.connect()
        mock_connector.connect.assert_called_once()
        assert source.is_connected() is True
        source.disconnect()
        mock_connector.disconnect.assert_called_once()

    @patch("src.sources.postgresql.create_connector")
    def test_execute_returns_query_result(self, mock_create):
        mock_connector = MagicMock()
        mock_raw = MagicMock()
        mock_raw.rows = [(1, "Alice"), (2, "Bob")]
        mock_raw.columns = ["id", "name"]
        mock_connector.execute_query.return_value = mock_raw
        mock_create.return_value = mock_connector

        source = PostgreSQLSource(name="db", url="postgresql://localhost/test")
        source.connect()

        query = SQLNativeQuery(sql="SELECT id, name FROM users", params=[])
        result = source.execute(query)

        assert isinstance(result, QueryResult)
        assert result.row_count == 2
        assert result.source_name == "db"
        assert result.rows[0] == {"id": 1, "name": "Alice"}
        assert result.columns == ["id", "name"]
