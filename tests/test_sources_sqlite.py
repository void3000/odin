from unittest.mock import MagicMock, patch
from src.sources.sqlite import SQLiteSource
from src.sources.postgresql import SQLNativeQuery
from src.sources.base import SourceSchema, SourceCapabilities, QueryResult, DataSource
from src.ir.models import QueryIR, TableSource, FieldExpr


class TestSQLiteSource:
    def test_implements_datasource_protocol(self):
        source = SQLiteSource(name="test_db", path="/tmp/test.db")
        assert isinstance(source, DataSource)

    def test_name_and_type(self):
        source = SQLiteSource(name="local_db", path="/tmp/test.db")
        assert source.name == "local_db"
        assert source.source_type == "database"

    def test_get_capabilities(self):
        source = SQLiteSource(name="db", path="/tmp/test.db")
        caps = source.get_capabilities()
        assert isinstance(caps, SourceCapabilities)
        assert caps.supports_joins is True
        assert caps.supports_aggregates is True
        assert caps.supports_time_range is False

    def test_build_query_returns_native_query(self):
        source = SQLiteSource(name="db", path="/tmp/test.db")
        ir = QueryIR(
            operation="SELECT",
            source=TableSource(table="users"),
            fields=[FieldExpr(field="*")],
            limit=10,
        )
        query = source.build_query(ir)
        assert isinstance(query, SQLNativeQuery)
        assert "users" in query.sql.lower() or "users" in query.sql

    @patch("src.sources.sqlite.SQLiteConnector")
    def test_connect_and_disconnect(self, mock_cls):
        mock_connector = MagicMock()
        mock_cls.return_value = mock_connector
        source = SQLiteSource(name="db", path="/tmp/test.db")
        source.connect()
        mock_connector.connect.assert_called_once()
        assert source.is_connected() is True
        source.disconnect()
        mock_connector.disconnect.assert_called_once()

    @patch("src.sources.sqlite.SQLiteConnector")
    def test_execute_returns_query_result(self, mock_cls):
        mock_connector = MagicMock()
        mock_raw = MagicMock()
        mock_raw.rows = [(1, "Alice")]
        mock_raw.columns = ["id", "name"]
        mock_connector.execute_query.return_value = mock_raw
        mock_cls.return_value = mock_connector

        source = SQLiteSource(name="db", path="/tmp/test.db")
        source.connect()

        query = SQLNativeQuery(sql="SELECT id, name FROM users", params=[])
        result = source.execute(query)

        assert isinstance(result, QueryResult)
        assert result.row_count == 1
        assert result.source_name == "db"
