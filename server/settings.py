"""Configuration, and the one invariant that must hold before the app is allowed to start.

Loading order (later wins): config.toml -> environment (JARVIS_*) -> explicit constructor args.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


class BindRefused(RuntimeError):
    """Raised when the configured bind would expose an unauthenticated server."""


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    auth_token: str = ""


class PathsConfig(BaseModel):
    data_dir: Path = Path("./data")
    models_dir: Path = Path("./models")
    memory_dir: Path = Path("./memory")
    """Plain Markdown, in its own git repo. The files are the truth (BRIEF.md 4.7)."""

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jarvis.db"


class LlamaCppConfig(BaseModel):
    enabled: bool = True
    base_url: str = "http://127.0.0.1:8081"
    autostart: bool = False
    model_path: str = ""
    ctx_len: int = 0


class HttpProviderConfig(BaseModel):
    enabled: bool = False
    base_url: str = ""


class ProvidersConfig(BaseModel):
    llamacpp: LlamaCppConfig = Field(default_factory=LlamaCppConfig)
    ollama: HttpProviderConfig = Field(
        default_factory=lambda: HttpProviderConfig(enabled=True, base_url="http://127.0.0.1:11434")
    )
    lmstudio: HttpProviderConfig = Field(
        default_factory=lambda: HttpProviderConfig(enabled=True, base_url="http://127.0.0.1:1234")
    )
    openai: HttpProviderConfig = Field(
        default_factory=lambda: HttpProviderConfig(base_url="https://api.openai.com/v1")
    )


class MemoryConfig(BaseModel):
    auto_extract: bool = True
    """Capture facts automatically after a turn. Always visible, always undoable."""
    min_answer_chars: int = 200
    """Short exchanges rarely contain durable facts and are not worth a second generation."""
    max_facts_per_turn: int = 3


class VisualConfig(BaseModel):
    preset: Literal["aurora", "solar", "deep"] = "aurora"
    performance_mode: Literal["auto", "on", "off"] = "auto"


class HardwareConfig(BaseModel):
    # Chromium's GPU process and the Windows compositor live on the same card as the model.
    # Reserving for them up front is what keeps the preflight check honest (PLAN.md 1.1).
    browser_vram_reserve_mb: int = 700
    kv_cache_dtype: Literal["f16", "q8_0"] = "q8_0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_nested_delimiter="__",
        toml_file=CONFIG_PATH,
        extra="ignore",
    )

    server: ServerConfig = Field(default_factory=ServerConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    visual: VisualConfig = Field(default_factory=VisualConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    hardware: HardwareConfig = Field(default_factory=HardwareConfig)
    openai_api_key: str = ""

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls))

    @model_validator(mode="after")
    def enforce_bind_invariant(self) -> Settings:
        """Non-loopback bind without auth is a startup failure, not a warning (BRIEF.md 7)."""
        if not is_loopback(self.server.host) and not self.server.auth_token:
            raise BindRefused(
                f"Refusing to start: host is {self.server.host!r}, which is not loopback, and "
                "no auth_token is set. Either bind 127.0.0.1 (the default) or set "
                "[server] auth_token in config.toml / JARVIS_SERVER__AUTH_TOKEN."
            )
        return self


def is_loopback(host: str) -> bool:
    """True for localhost and anything in 127.0.0.0/8 or ::1."""
    if host in ("localhost", "localhost.localdomain"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def load_settings(**overrides: object) -> Settings:
    return Settings(**overrides)  # type: ignore[arg-type]
