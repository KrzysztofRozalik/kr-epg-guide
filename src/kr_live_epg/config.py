from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from .exceptions import ConfigurationError
from .models import PlaylistKind

_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?}")
_SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if not isinstance(value, str):
        return value

    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise ConfigurationError(f"Brak wymaganej zmiennej środowiskowej: {name}")

    return _ENV_PATTERN.sub(replace, value)


class HttpConfig(BaseModel):
    timeout_seconds: float = Field(default=30.0, ge=1, le=300)
    retries: int = Field(default=3, ge=0, le=8)
    user_agent: str = "KR-Live-EPG/0.2.1 (+private XMLTV aggregator)"
    max_download_mb: int = Field(default=200, ge=1, le=1024)
    max_uncompressed_mb: int = Field(default=512, ge=1, le=2048)


class GuideSourceConfig(BaseModel):
    id: str
    type: Literal["xmltv"] = "xmltv"
    url: str
    priority: int = Field(default=50, ge=0, le=1000)
    enabled: bool = True
    trusted: bool = False
    timezone: str = "Europe/Warsaw"
    headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not _SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("source id contains unsafe characters")
        return value


class SentinelFeedConfig(BaseModel):
    id: str
    url: str
    type: Literal["rss", "atom", "ics", "html"] = "rss"
    enabled: bool = True
    official: bool = False
    headers: dict[str, str] = Field(default_factory=dict)
    item_xpath: str | None = None
    title_xpath: str = ".//h1//text() | .//h2//text() | .//h3//text()"
    body_xpath: str = ".//text()"
    link_xpath: str = ".//a/@href"

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not _SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("feed id contains unsafe characters")
        return value

    @model_validator(mode="after")
    def xpath_for_html(self) -> SentinelFeedConfig:
        if self.type == "html" and not self.item_xpath:
            raise ValueError("HTML feed requires item_xpath")
        return self


class SentinelRuleConfig(BaseModel):
    id: str
    pattern: str
    channel_ids: list[str] = Field(default_factory=list)
    required_terms: list[str] = Field(default_factory=lambda: ["transmisja"])
    default_duration_minutes: int = Field(default=180, ge=5, le=720)
    min_confidence: float = Field(default=0.86, ge=0, le=1)
    title_template: str | None = None

    @field_validator("id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        if not _SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("rule id contains unsafe characters")
        return value

    @field_validator("pattern")
    @classmethod
    def valid_regex(cls, value: str) -> str:
        re.compile(value, re.IGNORECASE)
        return value


class SentinelConfig(BaseModel):
    enabled: bool = True
    near_window_hours: int = Field(default=36, ge=1, le=504)
    feeds: list[SentinelFeedConfig] = Field(default_factory=list)
    rules: list[SentinelRuleConfig] = Field(default_factory=list)


class PlaylistConfig(BaseModel):
    type: PlaylistKind = PlaylistKind.NONE
    source_id: str = "provider"

    # M3U
    url: str | None = None
    path: str | None = None

    # Xtream Codes
    base_url: str | None = None
    username: SecretStr | None = None
    password: SecretStr | None = None
    output: Literal["ts", "m3u8"] = "ts"

    # Stalker / MAG
    portal_url: str | None = None
    mac: SecretStr | None = None
    serial: SecretStr | None = None
    device_id: SecretStr | None = None
    stalker_user_agent: str = (
        "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 "
        "(KHTML, like Gecko) MAG200 stbapp ver: 4 rev: 2721 Mobile Safari/533.3"
    )

    @field_validator("source_id")
    @classmethod
    def safe_source_id(cls, value: str) -> str:
        if not _SAFE_ID_PATTERN.fullmatch(value):
            raise ValueError("playlist source_id contains unsafe characters")
        return value

    @model_validator(mode="after")
    def required_fields_for_kind(self) -> PlaylistConfig:
        if self.type == PlaylistKind.M3U and not (self.url or self.path):
            raise ValueError("M3U requires url or path")
        if self.type == PlaylistKind.XTREAM and not (
            self.base_url and self.username and self.password
        ):
            raise ValueError("Xtream requires base_url, username and password")
        if self.type == PlaylistKind.STALKER and not (self.portal_url and self.mac):
            raise ValueError("Stalker requires portal_url and mac")
        return self


class ProfileConfig(BaseModel):
    playlist: PlaylistConfig = Field(default_factory=PlaylistConfig)
    delivery_token: SecretStr | None = None
    past_days: int = Field(default=1, ge=0, le=14)
    future_days: int = Field(default=10, ge=1, le=21)
    auto_match_threshold: float = Field(default=92.0, ge=60, le=100)
    auto_match_margin: float = Field(default=6.0, ge=0, le=30)
    include_unmatched_channels: bool = True
    emit_provider_aliases: bool = True
    emit_uncompressed_xml: bool = True
    max_description_chars: int = Field(default=1200, ge=200, le=5000)


class TmdbConfig(BaseModel):
    enabled: bool = False
    api_token: SecretStr | None = None
    language: str = "pl-PL"
    region: str = "PL"
    cache_days: int = Field(default=90, ge=1, le=3650)
    max_cast: int = Field(default=8, ge=0, le=30)
    max_requests_per_run: int = Field(default=80, ge=0, le=1000)
    min_duration_minutes: int = Field(default=50, ge=1, le=300)

    @model_validator(mode="after")
    def token_when_enabled(self) -> TmdbConfig:
        if self.enabled and not self.api_token:
            raise ValueError("TMDb enrichment is enabled but api_token is missing")
        return self


class LogoConfig(BaseModel):
    enabled: bool = True
    refresh_days: int = Field(default=30, ge=1, le=365)
    max_download_kb: int = Field(default=2048, ge=16, le=10240)
    workers: int = Field(default=8, ge=1, le=16)


class StorageConfig(BaseModel):
    type: Literal["local", "s3"] = "local"
    local_directory: str = "output"
    bucket: str | None = None
    endpoint_url: str | None = None
    access_key_id: SecretStr | None = None
    secret_access_key: SecretStr | None = None
    region: str = "auto"
    prefix: str = "v1"
    public_base_url: str | None = None

    @model_validator(mode="after")
    def s3_fields(self) -> StorageConfig:
        if self.type == "s3" and not all(
            [self.bucket, self.endpoint_url, self.access_key_id, self.secret_access_key]
        ):
            raise ValueError("S3 storage requires bucket, endpoint_url and credentials")
        return self


class AppConfig(BaseModel):
    timezone: str = "Europe/Warsaw"
    state_path: str = "state/kr-live-epg.sqlite3"
    registry_path: str | None = None
    http: HttpConfig = Field(default_factory=HttpConfig)
    guide_sources: list[GuideSourceConfig]
    profiles: dict[str, ProfileConfig]
    sentinel: SentinelConfig = Field(default_factory=SentinelConfig)
    tmdb: TmdbConfig = Field(default_factory=TmdbConfig)
    logos: LogoConfig = Field(default_factory=LogoConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)

    @field_validator("guide_sources")
    @classmethod
    def unique_source_ids(cls, value: list[GuideSourceConfig]) -> list[GuideSourceConfig]:
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("guide source IDs must be unique")
        return value

    @field_validator("profiles")
    @classmethod
    def safe_profile_names(cls, value: dict[str, ProfileConfig]) -> dict[str, ProfileConfig]:
        invalid = [name for name in value if not _SAFE_ID_PATTERN.fullmatch(name)]
        if invalid:
            raise ValueError(f"unsafe profile names: {', '.join(invalid)}")
        return value


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigurationError(f"Nie znaleziono konfiguracji: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Nieprawidłowy YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError("Główny element konfiguracji musi być mapą YAML")
    try:
        config = AppConfig.model_validate(_expand_env(raw))
    except Exception as exc:
        raise ConfigurationError(str(exc)) from exc

    base = config_path.parent
    if not Path(config.state_path).is_absolute():
        config.state_path = str((base / config.state_path).resolve())
    if config.registry_path and not Path(config.registry_path).is_absolute():
        config.registry_path = str((base / config.registry_path).resolve())
    if not Path(config.storage.local_directory).is_absolute():
        config.storage.local_directory = str((base / config.storage.local_directory).resolve())
    for profile in config.profiles.values():
        if profile.playlist.path and not Path(profile.playlist.path).is_absolute():
            profile.playlist.path = str((base / profile.playlist.path).resolve())
    return config
