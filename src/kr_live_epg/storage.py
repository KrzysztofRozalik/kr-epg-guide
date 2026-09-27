from __future__ import annotations

from pathlib import Path

import boto3

from .config import StorageConfig


class Publisher:
    def __init__(self, config: StorageConfig) -> None:
        self.config = config

    def public_url(self, profile: str, filename: str) -> str | None:
        if not self.config.public_base_url:
            return None
        base = self.config.public_base_url.rstrip("/")
        return f"{base}/{profile}/{filename}"

    def publish(self, profile: str, files: list[Path]) -> None:
        if self.config.type == "local":
            return
        client = boto3.client(
            "s3",
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=(
                self.config.access_key_id.get_secret_value() if self.config.access_key_id else None
            ),
            aws_secret_access_key=(
                self.config.secret_access_key.get_secret_value()
                if self.config.secret_access_key
                else None
            ),
            region_name=self.config.region,
        )
        content_types = {
            ".m3u": "application/vnd.apple.mpegurl",
            ".json": "application/json",
            ".xml": "application/xml",
            ".gz": "application/gzip",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        prefix = self.config.prefix.strip("/")
        profile_root = Path(self.config.local_directory) / profile
        for path in files:
            try:
                relative = path.relative_to(profile_root).as_posix()
            except ValueError:
                relative = path.name
            key = "/".join(part for part in (prefix, profile, relative) if part)
            extra: dict[str, str] = {
                "ContentType": content_types.get(path.suffix, "application/octet-stream"),
                "CacheControl": "public, max-age=60, stale-while-revalidate=300",
            }
            client.upload_file(str(path), self.config.bucket, key, ExtraArgs=extra)
