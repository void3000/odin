"""Source registry — holds configured data sources."""

from dataclasses import dataclass
from typing import Any

from src.sources.base import DataSource


@dataclass
class SourceInfo:
    """Lightweight summary of a registered source."""
    name: str
    source_type: str


class SourceRegistry:
    """Registry of configured data sources."""

    def __init__(self):
        self._sources: dict[str, DataSource] = {}

    def register(self, name: str, source: DataSource) -> None:
        """Register a source under a given name."""
        if name in self._sources:
            raise ValueError(f"Source '{name}' is already registered")
        self._sources[name] = source

    def get(self, name: str) -> DataSource:
        """Get a source by name. Raises KeyError if not found."""
        if name not in self._sources:
            raise KeyError(f"Source '{name}' not found")
        return self._sources[name]

    def get_default(self) -> DataSource:
        """Get the default source."""
        if len(self._sources) == 1:
            return next(iter(self._sources.values()))
        if "default" in self._sources:
            return self._sources["default"]
        raise ValueError(
            "Cannot determine default source: multiple sources registered "
            "and none named 'default'"
        )

    def list_sources(self) -> list[SourceInfo]:
        """List all registered sources."""
        return [
            SourceInfo(name=name, source_type=source.source_type)
            for name, source in self._sources.items()
        ]
