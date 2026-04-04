"""Application settings with environment variable and CLI override support."""

import argparse
import sys

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ODIN_")

    db: str | None = Field(default=None, description="Database connection string")
    config: str | None = Field(default=None, description="Path to sources YAML config file")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    llm_url: str = Field(default="http://localhost:1234/v1", description="LLM API base URL")
    llm_key: str = Field(default="lmstudio", description="LLM API key")
    llm_model: str = Field(
        default="qwen3.5-27b-claude-4.6-opus-reasoning-distilled",
        description="LLM model name",
    )
    temperature: float = Field(default=0.1, description="LLM temperature")
    default_limit: int = Field(default=100, description="Default row limit")
    log_level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR)")
    log_file: str | None = Field(default=None, description="Path to log file")


def settings_from_cli(argv: list[str] | None = None) -> ServerSettings:
    """Parse CLI arguments and merge with env vars.

    Priority: CLI flags > environment variables > defaults.
    """
    parser = argparse.ArgumentParser(description="Odin API Server")
    for name, field_info in ServerSettings.model_fields.items():
        flag = f"--{name.replace('_', '-')}"
        kwargs = {"help": f"{field_info.description} (env: ODIN_{name.upper()})", "default": None}
        if field_info.annotation is int:
            kwargs["type"] = int
        elif field_info.annotation is float:
            kwargs["type"] = float
        parser.add_argument(flag, **kwargs)

    args = parser.parse_args(argv)
    cli_overrides = {k: v for k, v in vars(args).items() if v is not None}

    try:
        return ServerSettings(**cli_overrides)
    except Exception as e:
        parser.error(str(e))
