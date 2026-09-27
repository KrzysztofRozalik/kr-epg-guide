from __future__ import annotations

import gzip
import re
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

from lxml import etree

from ..config import GuideSourceConfig
from ..exceptions import SourceError
from ..http import HttpClient
from ..models import Channel, Credits, Guide, Programme
from ..quality import ProgrammeQuality, classify_programme

_XMLTV_DATE = re.compile(r"^(\d{14}|\d{12}|\d{8})(?:\s*([+-]\d{4}|Z))?")


def _gunzip_bounded(data: bytes, limit: int, source_id: str) -> bytes:
    output = BytesIO()
    try:
        with gzip.GzipFile(fileobj=BytesIO(data)) as archive:
            while chunk := archive.read(min(1024 * 1024, limit + 1 - output.tell())):
                output.write(chunk)
                if output.tell() > limit:
                    raise SourceError(f"Rozpakowany XMLTV ze źródła {source_id} przekracza limit")
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise SourceError(f"Uszkodzony gzip ze źródła {source_id}") from exc
    return output.getvalue()


def _text(element: etree._Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = " ".join(element.text.split())
    return value or None


def _preferred_text(parent: etree._Element, tag: str) -> str | None:
    elements = parent.findall(tag)
    for language in ("pl", "pol", None):
        for element in elements:
            if (
                element.get("lang") == language or (language is None and not element.get("lang"))
            ) and (value := _text(element)):
                return value
    return next((value for item in elements if (value := _text(item))), None)


def _original_title(element: etree._Element, preferred: str) -> tuple[str | None, str | None]:
    for title in element.findall("title"):
        value = _text(title)
        language = title.get("lang")
        if value and value.casefold() != preferred.casefold() and language not in {"pl", "pol"}:
            return value, language
    return None, None


def parse_xmltv_datetime(value: str, default_timezone: str = "Europe/Warsaw") -> datetime:
    match = _XMLTV_DATE.match(value.strip())
    if not match:
        raise ValueError(f"Nieprawidłowa data XMLTV: {value!r}")
    raw, offset = match.groups()
    formats = {8: "%Y%m%d", 12: "%Y%m%d%H%M", 14: "%Y%m%d%H%M%S"}
    parsed = datetime.strptime(raw, formats[len(raw)])
    if offset == "Z":
        return parsed.replace(tzinfo=UTC)
    if offset:
        sign = 1 if offset[0] == "+" else -1
        delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5])) * sign
        return parsed.replace(tzinfo=UTC) - delta
    return parsed.replace(tzinfo=ZoneInfo(default_timezone))


def _credits(element: etree._Element) -> Credits:
    block = element.find("credits")
    if block is None:
        return Credits()

    def values(tag: str) -> list[str]:
        return [value for item in block.findall(tag) if (value := _text(item))]

    return Credits(
        directors=values("director"),
        producers=values("producer"),
        actors=values("actor"),
        writers=values("writer") + values("adapter"),
        presenters=values("presenter"),
        commentators=values("commentator"),
        guests=values("guest"),
    )


def _rating(element: etree._Element, tag: str) -> str | None:
    block = element.find(tag)
    return _text(block.find("value")) if block is not None else None


def parse_xmltv(
    data: bytes,
    *,
    source_id: str,
    priority: int = 50,
    default_timezone: str = "Europe/Warsaw",
    max_uncompressed_bytes: int = 512 * 1024 * 1024,
) -> Guide:
    if data.startswith(b"\x1f\x8b"):
        data = _gunzip_bounded(data, max_uncompressed_bytes, source_id)
    elif len(data) > max_uncompressed_bytes:
        raise SourceError(f"XMLTV ze źródła {source_id} przekracza limit")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        recover=False,
        remove_comments=True,
        huge_tree=False,
    )
    try:
        root = etree.parse(BytesIO(data), parser).getroot()
    except (etree.XMLSyntaxError, OSError) as exc:
        raise SourceError(f"Nieprawidłowy XMLTV ze źródła {source_id}: {exc}") from exc
    if root.tag != "tv":
        raise SourceError(f"Źródło {source_id} nie ma elementu głównego <tv>")

    channels: list[Channel] = []
    for element in root.findall("channel"):
        provider_id = (element.get("id") or "").strip()
        display_names = [
            value for item in element.findall("display-name") if (value := _text(item))
        ]
        if not provider_id or not display_names:
            continue
        icon = element.find("icon")
        channels.append(
            Channel(
                source_id=source_id,
                provider_id=provider_id,
                tvg_id=provider_id,
                name=display_names[0],
                aliases=display_names[1:],
                logo=icon.get("src") if icon is not None else None,
            )
        )

    programmes: list[Programme] = []
    rejected_programme_count = 0
    placeholder_programme_count = 0
    for element in root.findall("programme"):
        channel_id = (element.get("channel") or "").strip()
        start_raw = element.get("start")
        stop_raw = element.get("stop")
        title = _preferred_text(element, "title")
        if not channel_id or not start_raw or not title:
            continue
        try:
            start = parse_xmltv_datetime(start_raw, default_timezone)
            stop = (
                parse_xmltv_datetime(stop_raw, default_timezone)
                if stop_raw
                else start + timedelta(minutes=30)
            )
        except ValueError:
            continue
        if stop <= start:
            continue
        description = _preferred_text(element, "desc")
        quality = classify_programme(title, description)
        if quality == ProgrammeQuality.SOURCE_AD:
            rejected_programme_count += 1
            continue
        is_placeholder = quality == ProgrammeQuality.PLACEHOLDER
        placeholder_programme_count += int(is_placeholder)
        categories = [value for item in element.findall("category") if (value := _text(item))]
        countries = [value for item in element.findall("country") if (value := _text(item))]
        keywords = [value for item in element.findall("keyword") if (value := _text(item))]
        icon = element.find("icon")
        episodes = element.findall("episode-num")
        episode = next(
            (item for item in episodes if item.get("system") == "onscreen"),
            episodes[0] if episodes else None,
        )
        date = _preferred_text(element, "date")
        year = int(date[:4]) if date and date[:4].isdigit() else None
        reviews = [value for item in element.findall("review") if (value := _text(item))]
        original_title, title_language = _original_title(element, title)
        language = _preferred_text(element, "language") or "pl"
        original_language = _preferred_text(element, "orig-language") or title_language
        length = element.find("length")
        duration_minutes = None
        if length is not None and (raw_length := _text(length)) and raw_length.isdigit():
            duration_minutes = int(raw_length)
            if length.get("units") == "hours":
                duration_minutes *= 60
        previously_shown = element.find("previously-shown")
        previously_shown_at = None
        if previously_shown is not None and previously_shown.get("start"):
            with suppress(ValueError):
                previously_shown_at = parse_xmltv_datetime(
                    previously_shown.get("start") or "", default_timezone
                )
        credits = _credits(element)
        programmes.append(
            Programme(
                channel_id=channel_id,
                start=start,
                stop=stop,
                title=title,
                original_title=original_title,
                subtitle=_preferred_text(element, "sub-title"),
                description=description,
                categories=categories,
                credits=credits,
                year=year,
                country=countries,
                production_companies=credits.producers,
                episode_num=_text(episode),
                episode_num_system=(episode.get("system") or "onscreen")
                if episode is not None
                else "onscreen",
                duration_minutes=duration_minutes,
                icon=icon.get("src") if icon is not None else None,
                url=_preferred_text(element, "url"),
                age_rating=_rating(element, "rating"),
                star_rating=_rating(element, "star-rating"),
                reviews=reviews,
                keywords=keywords,
                language=language,
                original_language=original_language,
                is_live=element.find("live") is not None,
                is_premiere=element.find("premiere") is not None,
                is_new=element.find("new") is not None,
                is_repeat=previously_shown is not None,
                is_placeholder=is_placeholder,
                previously_shown_at=previously_shown_at,
                source_id=source_id,
                source_priority=priority,
            )
        )
    return Guide(
        source_id=source_id,
        channels=channels,
        programmes=programmes,
        rejected_programme_count=rejected_programme_count,
        placeholder_programme_count=placeholder_programme_count,
    )


class XmltvProvider:
    def __init__(
        self,
        config: GuideSourceConfig,
        http: HttpClient,
        *,
        cache_directory: str | Path | None = None,
    ) -> None:
        self.config = config
        self.http = http
        self.cache_path = (
            Path(cache_directory) / f"{config.id}.xmltv.cache" if cache_directory else None
        )
        self.used_stale_cache = False

    def _download(self) -> bytes:
        parsed = urlparse(self.config.url)
        if parsed.scheme == "file":
            return Path(unquote(parsed.path)).read_bytes()
        if parsed.scheme in {"http", "https"}:
            return self.http.get_bytes(self.config.url, headers=self.config.headers)
        local = Path(self.config.url)
        if local.is_file():
            return local.read_bytes()
        raise SourceError(f"Nieobsługiwany adres źródła {self.config.id}")

    def fetch(self) -> Guide:
        try:
            data = self._download()
            guide = parse_xmltv(
                data,
                source_id=self.config.id,
                priority=self.config.priority,
                default_timezone=self.config.timezone,
                max_uncompressed_bytes=self.http.config.max_uncompressed_mb * 1024 * 1024,
            )
            if self.cache_path:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = self.cache_path.with_suffix(".tmp")
                temporary.write_bytes(data)
                temporary.replace(self.cache_path)
            return guide
        except Exception:
            if not self.cache_path or not self.cache_path.is_file():
                raise
            self.used_stale_cache = True
            return parse_xmltv(
                self.cache_path.read_bytes(),
                source_id=self.config.id,
                priority=self.config.priority,
                default_timezone=self.config.timezone,
                max_uncompressed_bytes=self.http.config.max_uncompressed_mb * 1024 * 1024,
            )
