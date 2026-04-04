"""Source configuration — load sources from YAML config or DB URL."""

import yaml

from src.db import parse_db_url
from src.sources.base import DataSource
from src.sources.postgresql import PostgreSQLSource
from src.sources.registry import SourceRegistry
from src.sources.sqlite import SQLiteSource

SOURCE_TYPES = {
    "postgresql": lambda name, cfg: PostgreSQLSource(
        name=name,
        url=cfg["url"],
        search_path=cfg.get("search_path"),
    ),
    "sqlite": lambda name, cfg: SQLiteSource(
        name=name,
        path=cfg["path"],
    ),
}


def create_source_from_db_url(db_url: str, name: str = "default") -> DataSource:
    """Create a DataSource from a database URL (backwards compatible)."""
    scheme, connection_info = parse_db_url(db_url)

    if scheme in ("postgresql", "postgres"):
        return PostgreSQLSource(name=name, url=db_url)
    elif scheme == "sqlite":
        return SQLiteSource(name=name, path=connection_info)
    else:
        raise ValueError(f"Unsupported database scheme: {scheme}")


def load_sources_from_config(config_path: str) -> SourceRegistry:
    """Load sources from a YAML config file."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    registry = SourceRegistry()
    sources = config.get("sources", {})

    for name, cfg in sources.items():
        source_type = cfg.get("type", "")
        factory = SOURCE_TYPES.get(source_type)
        if factory is None:
            raise ValueError(
                f"Unsupported source type: '{source_type}' for source '{name}'. "
                f"Supported types: {', '.join(SOURCE_TYPES.keys())}"
            )
        source = factory(name, cfg)
        registry.register(name, source)

    return registry
