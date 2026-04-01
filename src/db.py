"""Database URL parsing and factory functions for connectors and schema extractors."""

from urllib.parse import urlparse

from src.executor.connectors.sqlite import SQLiteConnector
from src.executor.connectors.postgresql import PostgreSQLConnector
from src.schema.extractor import SQLiteSchemaExtractor, PostgreSQLSchemaExtractor


def parse_db_url(db_url: str) -> tuple[str, str]:
    """Parse a database URL and return (scheme, connection_info).

    Supported formats:
        postgresql://user:pass@host:port/dbname
        sqlite:///path/to/file.db
        sqlite://path/to/file.db
        /path/to/file.db  (plain path, treated as sqlite)
    """
    if "://" in db_url:
        parsed = urlparse(db_url)
        scheme = parsed.scheme.lower()
        if scheme == "sqlite":
            # sqlite:///absolute/path or sqlite://relative/path
            path = parsed.path
            if parsed.netloc:
                path = parsed.netloc + path
            return "sqlite", path
        return scheme, db_url
    # Plain path — assume sqlite
    return "sqlite", db_url


def create_connector(db_url: str, search_path: list[str] | None = None):
    """Create the appropriate database connector for a given URL."""
    scheme, connection_info = parse_db_url(db_url)

    if scheme == "sqlite":
        return SQLiteConnector(database=connection_info, check_same_thread=False)
    elif scheme in ("postgresql", "postgres"):
        return PostgreSQLConnector(connection_string=connection_info, search_path=search_path)
    else:
        raise ValueError(f"Unsupported database scheme: {scheme}")


def create_schema_extractor(db_url: str):
    """Create the appropriate schema extractor for a given URL."""
    scheme, connection_info = parse_db_url(db_url)

    if scheme == "sqlite":
        return SQLiteSchemaExtractor(connection_info)
    elif scheme in ("postgresql", "postgres"):
        return PostgreSQLSchemaExtractor(connection_info)
    else:
        raise ValueError(f"Unsupported database scheme: {scheme}")
