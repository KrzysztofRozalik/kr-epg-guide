from __future__ import annotations

import json
import re
from contextlib import suppress
from pathlib import Path

from .http import HttpClient
from .models import Channel

_ATTRIBUTE_RE = re.compile(r'([\w-]+)=(?:"([^"]*)"|([^\s,]+))')


def _split_extinf(value: str) -> tuple[str, str]:
    in_quotes = False
    for index, character in enumerate(value):
        if character == '"':
            in_quotes = not in_quotes
        elif character == "," and not in_quotes:
            return value[:index], value[index + 1 :]
    return value, ""


def parse_m3u(text: str, source_id: str = "provider") -> list[Channel]:
    channels: list[Channel] = []
    pending: tuple[dict[str, str], str, list[str]] | None = None
    directives: list[str] = []
    for raw_line in text.lstrip("\ufeff").splitlines():
        line = raw_line.strip()
        if not line or line == "#EXTM3U":
            continue
        if line.startswith("#EXTINF:"):
            metadata, name = _split_extinf(line.partition(":")[2])
            attributes = {
                match.group(1).lower(): match.group(2) or match.group(3) or ""
                for match in _ATTRIBUTE_RE.finditer(metadata)
            }
            pending = (attributes, name.strip() or attributes.get("tvg-name", ""), [])
            directives = []
            continue
        if line.startswith("#"):
            if pending is not None:
                directives.append(line)
            continue
        if pending is None:
            continue
        attributes, name, _ = pending
        if not name:
            pending = None
            continue
        provider_id = (
            attributes.get("tvg-id") or attributes.get("channel-id") or str(len(channels) + 1)
        )
        extra = dict(attributes)
        if directives:
            extra["kr-directives"] = json.dumps(directives, ensure_ascii=False)
        channels.append(
            Channel(
                source_id=source_id,
                provider_id=provider_id,
                name=name,
                tvg_id=attributes.get("tvg-id") or None,
                group=attributes.get("group-title") or None,
                logo=attributes.get("tvg-logo") or None,
                stream_url=line,
                aliases=[attributes["tvg-name"]] if attributes.get("tvg-name") else [],
                attributes=extra,
            )
        )
        pending = None
        directives = []
    return channels


def load_m3u(*, path: str | None, url: str | None, http: HttpClient) -> list[Channel]:
    if path:
        data = Path(path).read_bytes()
    elif url:
        data = http.get_bytes(url)
    else:
        return []
    return parse_m3u(data.decode("utf-8-sig", errors="replace"))


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def render_m3u(channels: list[Channel], *, xmltv_url: str | None = None) -> str:
    header = "#EXTM3U"
    if xmltv_url:
        header += f' x-tvg-url="{_escape(xmltv_url)}"'
    lines = [header]
    for channel in channels:
        if not channel.stream_url:
            continue
        tvg_id = channel.canonical_id or channel.tvg_id or channel.provider_id
        display_name = channel.canonical_name or channel.name
        attributes = [
            f'tvg-id="{_escape(tvg_id)}"',
            f'tvg-name="{_escape(display_name)}"',
        ]
        if channel.logo:
            attributes.append(f'tvg-logo="{_escape(channel.logo)}"')
        if channel.group:
            attributes.append(f'group-title="{_escape(channel.group)}"')
        # Preserve provider-specific archive instructions. Historical XMLTV
        # supplies the programme grid, while these tags tell the player how to
        # request the corresponding catch-up stream.
        for key in (
            "catchup",
            "catchup-type",
            "catchup-source",
            "catchup-days",
            "catchup-correction",
            "timeshift",
            "tvg-shift",
        ):
            if value := channel.attributes.get(key):
                attributes.append(f'{key}="{_escape(value)}"')
        lines.append(f"#EXTINF:-1 {' '.join(attributes)},{display_name}")
        raw_directives = channel.attributes.get("kr-directives")
        if raw_directives:
            with suppress(json.JSONDecodeError, TypeError):
                lines.extend(
                    item for item in json.loads(raw_directives) if str(item).startswith("#")
                )
        lines.append(channel.stream_url)
    return "\n".join(lines) + "\n"
