from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from .config import LogoConfig
from .http import HttpClient
from .models import CanonicalChannel
from .normalize import slugify_channel
from .storage import Publisher


def _image_extension(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _read_manifest(path: Path) -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): {str(item_key): str(item_value) for item_key, item_value in value.items()}
        for key, value in raw.items()
        if isinstance(value, dict)
    }


class LogoCache:
    """Keeps safe raster channel logos next to the published XMLTV files."""

    def __init__(
        self,
        config: LogoConfig,
        http: HttpClient,
        publisher: Publisher,
        *,
        profile_name: str,
        output_directory: Path,
    ) -> None:
        self.config = config
        self.http = http
        self.publisher = publisher
        self.profile_name = profile_name
        self.directory = output_directory / "logos"
        self.manifest_path = self.directory / "manifest.json"

    @staticmethod
    def _is_fresh(entry: dict[str, str], refresh_days: int) -> bool:
        try:
            fetched_at = datetime.fromisoformat(entry["fetched_at"])
        except (KeyError, ValueError):
            return False
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        return datetime.now(UTC) - fetched_at < timedelta(days=refresh_days)

    def materialize(self, channels: list[CanonicalChannel]) -> list[Path]:
        if not self.config.enabled or not self.publisher.config.public_base_url:
            return []
        self.directory.mkdir(parents=True, exist_ok=True)
        manifest = _read_manifest(self.manifest_path)
        published: list[Path] = []
        changed = False
        pending: list[tuple[CanonicalChannel, str, Path | None]] = []
        public_base = (self.publisher.config.public_base_url or "").rstrip("/") + "/"

        for channel in channels:
            source_url = (channel.logo or "").strip()
            if urlparse(source_url).scheme not in {"http", "https"}:
                continue
            if source_url.startswith(public_base):
                continue
            entry = manifest.get(channel.id, {})
            filename = Path(entry.get("filename", "")).name
            cached_path = self.directory / filename if filename else None
            reusable = bool(
                cached_path
                and cached_path.is_file()
                and entry.get("source_url") == source_url
                and self._is_fresh(entry, self.config.refresh_days)
            )
            if reusable and cached_path:
                local_url = self.publisher.public_url(
                    self.profile_name, f"logos/{cached_path.name}"
                )
                if local_url:
                    channel.logo = local_url
                published.append(cached_path)
            else:
                pending.append((channel, source_url, cached_path))

        def download(source_url: str) -> tuple[bytes, str]:
            data = self.http.get_bytes(source_url)
            if len(data) > self.config.max_download_kb * 1024:
                raise ValueError("logo exceeds configured limit")
            extension = _image_extension(data)
            if extension is None:
                raise ValueError("unsupported logo format")
            return data, extension

        with ThreadPoolExecutor(max_workers=self.config.workers) as executor:
            futures = {
                executor.submit(download, source_url): (channel, source_url, cached_path)
                for channel, source_url, cached_path in pending
            }
            for future in as_completed(futures):
                channel, source_url, cached_path = futures[future]
                try:
                    data, extension = future.result()
                    filename = f"{slugify_channel(channel.id)}{extension}"
                    cached_path = self.directory / filename
                    temporary = cached_path.with_suffix(cached_path.suffix + ".tmp")
                    temporary.write_bytes(data)
                    temporary.replace(cached_path)
                    manifest[channel.id] = {
                        "source_url": source_url,
                        "filename": filename,
                        "fetched_at": datetime.now(UTC).isoformat(),
                    }
                    changed = True
                except Exception:
                    # A stale local logo is safer than losing it during a source outage.
                    if not cached_path or not cached_path.is_file():
                        continue
                if not cached_path or not cached_path.is_file():
                    continue
                local_url = self.publisher.public_url(
                    self.profile_name, f"logos/{cached_path.name}"
                )
                if local_url:
                    channel.logo = local_url
                published.append(cached_path)

        if changed or (manifest and not self.manifest_path.is_file()):
            temporary = self.manifest_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(self.manifest_path)
        if self.manifest_path.is_file():
            published.append(self.manifest_path)
        return published
