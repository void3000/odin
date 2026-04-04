import tempfile
import os
import pytest
from src.sources.config import load_sources_from_config, create_source_from_db_url
from src.sources.registry import SourceRegistry


class TestCreateSourceFromDbUrl:
    def test_postgresql_url(self):
        source = create_source_from_db_url("postgresql://user:pass@localhost:5432/mydb")
        assert source.name == "default"
        assert source.source_type == "database"

    def test_sqlite_url(self):
        source = create_source_from_db_url("sqlite:///tmp/test.db")
        assert source.name == "default"
        assert source.source_type == "database"

    def test_plain_path(self):
        source = create_source_from_db_url("/tmp/test.db")
        assert source.name == "default"
        assert source.source_type == "database"

    def test_custom_name(self):
        source = create_source_from_db_url("sqlite:///tmp/test.db", name="my_db")
        assert source.name == "my_db"

    def test_unsupported_scheme(self):
        with pytest.raises(ValueError, match="Unsupported"):
            create_source_from_db_url("mysql://localhost/db")


class TestLoadSourcesFromConfig:
    def test_load_yaml_config(self):
        config_content = """
sources:
  main_db:
    type: postgresql
    url: postgresql://user:pass@localhost:5432/mydb
  local_db:
    type: sqlite
    path: /tmp/test.db
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            try:
                registry = load_sources_from_config(f.name)
                sources = registry.list_sources()
                assert len(sources) == 2
                names = {s.name for s in sources}
                assert names == {"main_db", "local_db"}
            finally:
                os.unlink(f.name)

    def test_load_empty_config(self):
        config_content = "sources: {}\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            try:
                registry = load_sources_from_config(f.name)
                assert len(registry.list_sources()) == 0
            finally:
                os.unlink(f.name)

    def test_unsupported_type_raises(self):
        config_content = """
sources:
  bad:
    type: dynamodb
    region: us-east-1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(config_content)
            f.flush()
            try:
                with pytest.raises(ValueError, match="Unsupported source type"):
                    load_sources_from_config(f.name)
            finally:
                os.unlink(f.name)
