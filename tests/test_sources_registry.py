import pytest
from unittest.mock import MagicMock
from src.sources.registry import SourceRegistry, SourceInfo


def _make_mock_source(name="test_db", source_type="database"):
    source = MagicMock()
    source.name = name
    source.source_type = source_type
    return source


class TestSourceRegistry:
    def test_register_and_get(self):
        registry = SourceRegistry()
        source = _make_mock_source()
        registry.register("test_db", source)
        assert registry.get("test_db") is source

    def test_get_unknown_raises(self):
        registry = SourceRegistry()
        with pytest.raises(KeyError, match="test_db"):
            registry.get("test_db")

    def test_list_sources(self):
        registry = SourceRegistry()
        registry.register("db1", _make_mock_source("db1", "database"))
        registry.register("logs1", _make_mock_source("logs1", "logs"))
        sources = registry.list_sources()
        assert len(sources) == 2
        names = {s.name for s in sources}
        assert names == {"db1", "logs1"}

    def test_list_sources_returns_source_info(self):
        registry = SourceRegistry()
        registry.register("db1", _make_mock_source("db1", "database"))
        info = registry.list_sources()[0]
        assert isinstance(info, SourceInfo)
        assert info.name == "db1"
        assert info.source_type == "database"

    def test_get_default_single_source(self):
        registry = SourceRegistry()
        source = _make_mock_source()
        registry.register("only_one", source)
        assert registry.get_default() is source

    def test_get_default_named_default(self):
        registry = SourceRegistry()
        source1 = _make_mock_source("db1")
        source2 = _make_mock_source("default")
        registry.register("db1", source1)
        registry.register("default", source2)
        assert registry.get_default() is source2

    def test_get_default_multiple_no_default_raises(self):
        registry = SourceRegistry()
        registry.register("db1", _make_mock_source("db1"))
        registry.register("db2", _make_mock_source("db2"))
        with pytest.raises(ValueError, match="multiple sources"):
            registry.get_default()

    def test_register_duplicate_raises(self):
        registry = SourceRegistry()
        registry.register("db1", _make_mock_source())
        with pytest.raises(ValueError, match="already registered"):
            registry.register("db1", _make_mock_source())

    def test_is_empty(self):
        registry = SourceRegistry()
        assert len(registry.list_sources()) == 0
