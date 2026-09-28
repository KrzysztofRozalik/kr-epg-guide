from __future__ import annotations

import gzip
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from lxml import etree

from .descriptions import visible_description
from .exceptions import ValidationError
from .models import CanonicalChannel, Channel, Programme
from .providers.xmltv import parse_xmltv_datetime


def _xmltv_time(value: object) -> str:
    return value.strftime("%Y%m%d%H%M%S %z")  # type: ignore[union-attr]


def _sub(parent: etree._Element, tag: str, value: str | None, **attributes: str) -> None:
    if not value:
        return
    child = etree.SubElement(parent, tag, **attributes)
    child.text = value


def _channel_element(
    channel_id: str,
    name: str,
    *,
    aliases: Iterable[str] = (),
    logo: str | None = None,
) -> etree._Element:
    element = etree.Element("channel", id=channel_id)
    seen: set[str] = set()
    for display_name in [name, *aliases]:
        clean = " ".join(display_name.split())
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        _sub(element, "display-name", clean, lang="pl")
    if logo:
        etree.SubElement(element, "icon", src=logo)
    return element


def _trim(value: str | None, limit: int) -> str | None:
    if value and len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


def _programme_element(
    programme: Programme, channel_id: str, max_description_chars: int
) -> etree._Element:
    element = etree.Element(
        "programme",
        start=_xmltv_time(programme.start),
        stop=_xmltv_time(programme.stop),
        channel=channel_id,
    )
    _sub(element, "title", programme.title, lang=programme.language)
    if (
        programme.original_title
        and programme.original_title.casefold() != programme.title.casefold()
    ):
        _sub(
            element,
            "title",
            programme.original_title,
            lang=programme.original_language or "und",
        )
    _sub(element, "sub-title", programme.subtitle, lang=programme.language)
    _sub(
        element,
        "desc",
        _trim(visible_description(programme), max_description_chars),
        lang=programme.language,
    )
    credits = programme.credits
    if any(
        [
            credits.directors,
            credits.producers,
            credits.actors,
            credits.writers,
            credits.presenters,
            credits.commentators,
            credits.guests,
        ]
    ):
        block = etree.SubElement(element, "credits")
        for tag, values in (
            ("director", credits.directors),
            (
                "producer",
                list(dict.fromkeys([*credits.producers, *programme.production_companies])),
            ),
            ("actor", credits.actors),
            ("writer", credits.writers),
            ("presenter", credits.presenters),
            ("commentator", credits.commentators),
            ("guest", credits.guests),
        ):
            for value in values:
                _sub(block, tag, value)
    if programme.year:
        _sub(element, "date", str(programme.year))
    for category in programme.categories:
        _sub(element, "category", category, lang=programme.language)
    for country in programme.country:
        _sub(element, "country", country)
    _sub(
        element,
        "episode-num",
        programme.episode_num,
        system=programme.episode_num_system,
    )
    if programme.duration_minutes:
        _sub(element, "length", str(programme.duration_minutes), units="minutes")
    if programme.icon:
        etree.SubElement(element, "icon", src=programme.icon)
    _sub(element, "url", programme.url)
    _sub(element, "language", programme.language)
    _sub(element, "orig-language", programme.original_language)
    for keyword in programme.keywords:
        _sub(element, "keyword", keyword, lang=programme.language)
    if programme.is_live:
        etree.SubElement(element, "live")
    if programme.is_premiere:
        etree.SubElement(element, "premiere")
    if programme.is_new:
        etree.SubElement(element, "new")
    if programme.is_repeat:
        attributes = {}
        if programme.previously_shown_at:
            attributes["start"] = _xmltv_time(programme.previously_shown_at)
        etree.SubElement(element, "previously-shown", **attributes)
    if programme.age_rating:
        block = etree.SubElement(element, "rating")
        _sub(block, "value", programme.age_rating)
    if programme.star_rating:
        block = etree.SubElement(element, "star-rating")
        _sub(block, "value", programme.star_rating)
    for review in programme.reviews:
from __future__ import annotations

import gzip
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from lxml import etree

from .descriptions import visible_description
from .exceptions import ValidationError
from .models import CanonicalChannel, Channel, Programme
from .normalize import compact_signature
from .providers.xmltv import parse_xmltv_datetime


def _xmltv_time(value: object) -> str:
    return value.strftime("%Y%m%d%H%M%S %z")  # type: ignore[union-attr]


def _sub(parent: etree._Element, tag: str, value: str | None, **attributes: str) -> None:
    if not value:
        return
    child = etree.SubElement(parent, tag, **attributes)
    child.text = value


def _channel_element(
    channel_id: str,
    name: str,
    *,
    aliases: Iterable[str] = (),
    logo: str | None = None,
) -> etree._Element:
    element = etree.Element("channel", id=channel_id)
    seen: set[str] = set()
    for display_name in [name, *aliases]:
        clean = " ".join(display_name.split())
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        _sub(element, "display-name", clean, lang="pl")
    if logo:
        etree.SubElement(element, "icon", src=logo)
    return element


def _tivimate_display_names(channel: CanonicalChannel) -> list[str]:
    """Emit common reseller spellings because TiViMate matches XMLTV names itself."""

    signature = compact_signature(channel.name)
    equivalent = sorted(
        {
            " ".join(alias.split())
            for alias in channel.aliases
            if alias.strip() and compact_signature(alias) == signature
        },
        key=lambda value: (len(value), value.casefold()),
    )
    # A few shortest spellings cover e.g. both ``TVP 3`` and ``TVP3`` without
    # multiplying every provider decoration already collected from upstream.
    bases = list(dict.fromkeys([channel.name, *equivalent[:3]]))
    names: list[str] = []
    suffixes = ("", " PL", " HD", " FHD", " UHD", " 4K", " RAW", " HD PL", " FHD PL")
    prefixes = ("", "PL| ", "PL-VIP| ", "PL: ")
    for base in bases:
        for prefix in prefixes:
            for suffix in suffixes:
                names.append(f"{prefix}{base}{suffix}")
    return names


def _trim(value: str | None, limit: int) -> str | None:
    if value and len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


def _programme_element(
    programme: Programme, channel_id: str, max_description_chars: int
) -> etree._Element:
    element = etree.Element(
        "programme",
        start=_xmltv_time(programme.start),
        stop=_xmltv_time(programme.stop),
        channel=channel_id,
    )
    _sub(element, "title", programme.title, lang=programme.language)
    if (
        programme.original_title
        and programme.original_title.casefold() != programme.title.casefold()
    ):
        _sub(
            element,
            "title",
            programme.original_title,
            lang=programme.original_language or "und",
        )
    _sub(element, "sub-title", programme.subtitle, lang=programme.language)
    _sub(
        element,
        "desc",
        _trim(visible_description(programme), max_description_chars),
        lang=programme.language,
    )
    credits = programme.credits
    if any(
        [
            credits.directors,
            credits.producers,
            credits.actors,
            credits.writers,
            credits.presenters,
            credits.commentators,
            credits.guests,
        ]
    ):
        block = etree.SubElement(element, "credits")
        for tag, values in (
            ("director", credits.directors),
            (
                "producer",
                list(dict.fromkeys([*credits.producers, *programme.production_companies])),
            ),
            ("actor", credits.actors),
            ("writer", credits.writers),
            ("presenter", credits.presenters),
            ("commentator", credits.commentators),
            ("guest", credits.guests),
        ):
            for value in values:
                _sub(block, tag, value)
    if programme.year:
        _sub(element, "date", str(programme.year))
    for category in programme.categories:
        _sub(element, "category", category, lang=programme.language)
    for country in programme.country:
        _sub(element, "country", country)
    _sub(
        element,
        "episode-num",
        programme.episode_num,
        system=programme.episode_num_system,
    )
    if programme.duration_minutes:
        _sub(element, "length", str(programme.duration_minutes), units="minutes")
    if programme.icon:
        etree.SubElement(element, "icon", src=programme.icon)
    _sub(element, "url", programme.url)
    _sub(element, "language", programme.language)
    _sub(element, "orig-language", programme.original_language)
    for keyword in programme.keywords:
        _sub(element, "keyword", keyword, lang=programme.language)
    if programme.is_live:
        etree.SubElement(element, "live")
    if programme.is_premiere:
        etree.SubElement(element, "premiere")
    if programme.is_new:
        etree.SubElement(element, "new")
    if programme.is_repeat:
        attributes = {}
from __future__ import annotations

import gzip
import os
import tempfile
from collections import defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

from lxml import etree

from .descriptions import visible_description
from .exceptions import ValidationError
from .models import CanonicalChannel, Channel, Programme
from .normalize import compact_signature
from .providers.xmltv import parse_xmltv_datetime


def _xmltv_time(value: object) -> str:
    return value.strftime("%Y%m%d%H%M%S %z")  # type: ignore[union-attr]


def _sub(parent: etree._Element, tag: str, value: str | None, **attributes: str) -> None:
    if not value:
        return
    child = etree.SubElement(parent, tag, **attributes)
    child.text = value


def _channel_element(
    channel_id: str,
    name: str,
    *,
    aliases: Iterable[str] = (),
    logo: str | None = None,
) -> etree._Element:
    element = etree.Element("channel", id=channel_id)
    seen: set[str] = set()
    for display_name in [name, *aliases]:
        clean = " ".join(display_name.split())
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        _sub(element, "display-name", clean, lang="pl")
    if logo:
        etree.SubElement(element, "icon", src=logo)
    return element


def _tivimate_display_names(channel: CanonicalChannel) -> list[str]:
    """Emit common reseller spellings because TiViMate matches XMLTV names itself."""

    signature = compact_signature(channel.name)
    equivalent = sorted(
        {
            " ".join(alias.split())
            for alias in channel.aliases
            if alias.strip() and compact_signature(alias) == signature
        },
        key=lambda value: (len(value), value.casefold()),
    )
    # A few shortest spellings cover e.g. both ``TVP 3`` and ``TVP3`` without
    # multiplying every provider decoration already collected from upstream.
    bases = list(dict.fromkeys([channel.name, *equivalent[:3]]))
    names: list[str] = []
    suffixes = ("", " PL", " HD", " FHD", " UHD", " 4K", " RAW", " HD PL", " FHD PL")
    prefixes = ("", "PL| ", "PL-VIP| ", "PL: ")
    for base in bases:
        for prefix in prefixes:
            for suffix in suffixes:
                names.append(f"{prefix}{base}{suffix}")
    return names


def _trim(value: str | None, limit: int) -> str | None:
    if value and len(value) > limit:
        return value[: limit - 1].rstrip() + "…"
    return value


def _programme_element(
    programme: Programme, channel_id: str, max_description_chars: int
) -> etree._Element:
    element = etree.Element(
        "programme",
        start=_xmltv_time(programme.start),
        stop=_xmltv_time(programme.stop),
        channel=channel_id,
    )
    _sub(element, "title", programme.title, lang=programme.language)
    if (
        programme.original_title
        and programme.original_title.casefold() != programme.title.casefold()
    ):
        _sub(
            element,
            "title",
            programme.original_title,
            lang=programme.original_language or "und",
        )
    _sub(element, "sub-title", programme.subtitle, lang=programme.language)
    _sub(
        element,
        "desc",
        _trim(visible_description(programme), max_description_chars),
        lang=programme.language,
    )
    credits = programme.credits
    if any(
        [
            credits.directors,
            credits.producers,
            credits.actors,
            credits.writers,
            credits.presenters,
            credits.commentators,
            credits.guests,
        ]
    ):
        block = etree.SubElement(element, "credits")
        for tag, values in (
            ("director", credits.directors),
            (
                "producer",
                list(dict.fromkeys([*credits.producers, *programme.production_companies])),
            ),
            ("actor", credits.actors),
            ("writer", credits.writers),
            ("presenter", credits.presenters),
            ("commentator", credits.commentators),
            ("guest", credits.guests),
        ):
            for value in values:
                _sub(block, tag, value)
    if programme.year:
        _sub(element, "date", str(programme.year))
    for category in programme.categories:
        _sub(element, "category", category, lang=programme.language)
    for country in programme.country:
        _sub(element, "country", country)
    _sub(
        element,
        "episode-num",
        programme.episode_num,
        system=programme.episode_num_system,
    )
    if programme.duration_minutes:
        _sub(element, "length", str(programme.duration_minutes), units="minutes")
    if programme.icon:
        etree.SubElement(element, "icon", src=programme.icon)
    _sub(element, "url", programme.url)
    _sub(element, "language", programme.language)
    _sub(element, "orig-language", programme.original_language)
    for keyword in programme.keywords:
        _sub(element, "keyword", keyword, lang=programme.language)
    if programme.is_live:
        etree.SubElement(element, "live")
    if programme.is_premiere:
        etree.SubElement(element, "premiere")
    if programme.is_new:
        etree.SubElement(element, "new")
    if programme.is_repeat:
        attributes = {}
        if programme.previously_shown_at:
            attributes["start"] = _xmltv_time(programme.previously_shown_at)
        etree.SubElement(element, "previously-shown", **attributes)
    if programme.age_rating:
        block = etree.SubElement(element, "rating")
        _sub(block, "value", programme.age_rating)
    if programme.star_rating:
        block = etree.SubElement(element, "star-rating")
        _sub(block, "value", programme.star_rating)
    for review in programme.reviews:
        _sub(element, "review", _trim(review, max_description_chars), lang=programme.language)
    return element


def _alias_ids(
    channels: list[CanonicalChannel], provider_channels: list[Channel]
) -> tuple[dict[str, list[Channel]], dict[str, str]]:
    grouped: dict[str, list[Channel]] = defaultdict(list)
    canonical_ids = {channel.id for channel in channels}
    alias_to_canonical: dict[str, str] = {}
    for provider in provider_channels:
        if not provider.canonical_id:
            continue
        grouped[provider.canonical_id].append(provider)
        for raw_candidate in (provider.tvg_id, provider.provider_id):
            candidate = (raw_candidate or "").strip()
            if not candidate or candidate in canonical_ids:
                continue
            existing = alias_to_canonical.get(candidate)
            if existing and existing != provider.canonical_id:
                continue
            alias_to_canonical[candidate] = provider.canonical_id
    return grouped, alias_to_canonical


@contextmanager
def _output_stream(path: Path, *, compressed: bool) -> Iterator[BinaryIO]:
    if compressed:
        with (
            path.open("wb") as raw_stream,
            gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=6,
                fileobj=raw_stream,
                mtime=0,
            ) as gzip_stream,
        ):
            yield gzip_stream
    else:
        with path.open("wb") as stream:
            yield stream


def write_xmltv(
    path: str | Path,
    channels: list[CanonicalChannel],
    programmes: list[Programme],
    *,
    provider_channels: list[Channel] | None = None,
    emit_provider_aliases: bool = False,
    max_description_chars: int = 5000,
) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    provider_channels = provider_channels or []
    grouped, alias_to_canonical = _alias_ids(channels, provider_channels)
    if not emit_provider_aliases:
        alias_to_canonical = {}

    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with (
            _output_stream(temporary, compressed=destination.suffix == ".gz") as stream,
            etree.xmlfile(stream, encoding="UTF-8") as document,
        ):
            document.write_declaration()
            with document.element(
                "tv",
                {
                    "generator-info-name": "KR Live EPG",
                    "generator-info-url": "https://localhost.invalid/kr-live-epg",
                },
            ):
                for channel in sorted(channels, key=lambda item: item.name.casefold()):
                    provider_names = [item.name for item in grouped.get(channel.id, [])]
                    document.write(
                        _channel_element(
                            channel.id,
                            channel.name,
                            aliases=[
                                *channel.aliases,
                                *provider_names,
                                *_tivimate_display_names(channel),
                            ],
                            logo=channel.logo,
                        )
                    )
                if emit_provider_aliases:
                    by_id = {channel.id: channel for channel in channels}
                    provider_by_alias = {}
                    for item in provider_channels:
                        if not item.canonical_id:
                            continue
                        for raw_alias in (item.tvg_id, item.provider_id):
                            if raw_alias and raw_alias.strip():
                                provider_by_alias[raw_alias.strip()] = item
                    for alias_id, canonical_id in sorted(alias_to_canonical.items()):
                        provider = provider_by_alias.get(alias_id)
                        canonical = by_id.get(canonical_id)
                        if provider and canonical:
                            document.write(
                                _channel_element(
                                    alias_id,
                                    provider.name,
                                    aliases=[canonical.name],
                                    logo=provider.logo or canonical.logo,
                                )
                            )
                aliases_by_canonical: dict[str, list[str]] = defaultdict(list)
                for alias, canonical in alias_to_canonical.items():
                    aliases_by_canonical[canonical].append(alias)
                for programme in programmes:
                    document.write(
                        _programme_element(programme, programme.channel_id, max_description_chars)
                    )
                    for alias_id in aliases_by_canonical.get(programme.channel_id, []):
                        document.write(
                            _programme_element(programme, alias_id, max_description_chars)
                        )
        validate_xmltv(temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination.stat().st_size


def validate_xmltv(path: str | Path) -> None:
    file_path = Path(path)
    raw = file_path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationError(f"Wygenerowany XMLTV jest nieprawidłowy: {exc}") from exc
    if root.tag != "tv":
        raise ValidationError("Wygenerowany plik nie ma elementu <tv>")
    channel_ids = [item.get("id") or "" for item in root.findall("channel")]
    if len(channel_ids) != len(set(channel_ids)):
        raise ValidationError("XMLTV zawiera zduplikowane identyfikatory kanałów")
    known = set(channel_ids)
    for programme in root.findall("programme"):
        if programme.get("channel") not in known:
            raise ValidationError("Program odwołuje się do nieistniejącego kanału")
        start = parse_xmltv_datetime(programme.get("start") or "")
        stop = parse_xmltv_datetime(programme.get("stop") or "")
        if stop <= start:
            raise ValidationError("Program ma czas końca wcześniejszy od początku")
        if programme.previously_shown_at:
            attributes["start"] = _xmltv_time(programme.previously_shown_at)
        etree.SubElement(element, "previously-shown", **attributes)
    if programme.age_rating:
        block = etree.SubElement(element, "rating")
        _sub(block, "value", programme.age_rating)
    if programme.star_rating:
        block = etree.SubElement(element, "star-rating")
        _sub(block, "value", programme.star_rating)
    for review in programme.reviews:
        _sub(element, "review", _trim(review, max_description_chars), lang=programme.language)
    return element


def _alias_ids(
    channels: list[CanonicalChannel], provider_channels: list[Channel]
) -> tuple[dict[str, list[Channel]], dict[str, str]]:
    grouped: dict[str, list[Channel]] = defaultdict(list)
    canonical_ids = {channel.id for channel in channels}
    alias_to_canonical: dict[str, str] = {}
    for provider in provider_channels:
        if not provider.canonical_id:
            continue
        grouped[provider.canonical_id].append(provider)
        for raw_candidate in (provider.tvg_id, provider.provider_id):
            candidate = (raw_candidate or "").strip()
            if not candidate or candidate in canonical_ids:
                continue
            existing = alias_to_canonical.get(candidate)
            if existing and existing != provider.canonical_id:
                continue
            alias_to_canonical[candidate] = provider.canonical_id
    return grouped, alias_to_canonical


@contextmanager
def _output_stream(path: Path, *, compressed: bool) -> Iterator[BinaryIO]:
    if compressed:
        with (
            path.open("wb") as raw_stream,
            gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=6,
                fileobj=raw_stream,
                mtime=0,
            ) as gzip_stream,
        ):
            yield gzip_stream
    else:
        with path.open("wb") as stream:
            yield stream


def write_xmltv(
    path: str | Path,
    channels: list[CanonicalChannel],
    programmes: list[Programme],
    *,
    provider_channels: list[Channel] | None = None,
    emit_provider_aliases: bool = False,
    max_description_chars: int = 5000,
) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    provider_channels = provider_channels or []
    grouped, alias_to_canonical = _alias_ids(channels, provider_channels)
    if not emit_provider_aliases:
        alias_to_canonical = {}

    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with (
            _output_stream(temporary, compressed=destination.suffix == ".gz") as stream,
            etree.xmlfile(stream, encoding="UTF-8") as document,
        ):
            document.write_declaration()
            with document.element(
                "tv",
                {
                    "generator-info-name": "KR Live EPG",
                    "generator-info-url": "https://localhost.invalid/kr-live-epg",
                },
            ):
                for channel in sorted(channels, key=lambda item: item.name.casefold()):
                    provider_names = [item.name for item in grouped.get(channel.id, [])]
                    document.write(
                        _channel_element(
                            channel.id,
                            channel.name,
                            aliases=[
                                *channel.aliases,
                                *provider_names,
                                *_tivimate_display_names(channel),
                            ],
                            logo=channel.logo,
                        )
                    )
                if emit_provider_aliases:
                    by_id = {channel.id: channel for channel in channels}
                    provider_by_alias = {}
                    for item in provider_channels:
                        if not item.canonical_id:
                            continue
                        for raw_alias in (item.tvg_id, item.provider_id):
                            if raw_alias and raw_alias.strip():
                                provider_by_alias[raw_alias.strip()] = item
                    for alias_id, canonical_id in sorted(alias_to_canonical.items()):
                        provider = provider_by_alias.get(alias_id)
                        canonical = by_id.get(canonical_id)
                        if provider and canonical:
                            document.write(
                                _channel_element(
                                    alias_id,
                                    provider.name,
                                    aliases=[canonical.name],
                                    logo=provider.logo or canonical.logo,
                                )
                            )
                aliases_by_canonical: dict[str, list[str]] = defaultdict(list)
                for alias, canonical in alias_to_canonical.items():
                    aliases_by_canonical[canonical].append(alias)
                for programme in programmes:
                    document.write(
                        _programme_element(programme, programme.channel_id, max_description_chars)
                    )
                    for alias_id in aliases_by_canonical.get(programme.channel_id, []):
                        document.write(
                            _programme_element(programme, alias_id, max_description_chars)
                        )
        validate_xmltv(temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination.stat().st_size


def validate_xmltv(path: str | Path) -> None:
    file_path = Path(path)
    raw = file_path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationError(f"Wygenerowany XMLTV jest nieprawidłowy: {exc}") from exc
    if root.tag != "tv":
        raise ValidationError("Wygenerowany plik nie ma elementu <tv>")
    channel_ids = [item.get("id") or "" for item in root.findall("channel")]
    if len(channel_ids) != len(set(channel_ids)):
        raise ValidationError("XMLTV zawiera zduplikowane identyfikatory kanałów")
    known = set(channel_ids)
    for programme in root.findall("programme"):
        if programme.get("channel") not in known:
            raise ValidationError("Program odwołuje się do nieistniejącego kanału")
        start = parse_xmltv_datetime(programme.get("start") or "")
        stop = parse_xmltv_datetime(programme.get("stop") or "")
        if stop <= start:
            raise ValidationError("Program ma czas końca wcześniejszy od początku")
        _sub(element, "review", _trim(review, max_description_chars), lang=programme.language)
    return element


def _alias_ids(
    channels: list[CanonicalChannel], provider_channels: list[Channel]
) -> tuple[dict[str, list[Channel]], dict[str, str]]:
    grouped: dict[str, list[Channel]] = defaultdict(list)
    canonical_ids = {channel.id for channel in channels}
    alias_to_canonical: dict[str, str] = {}
    for provider in provider_channels:
        if not provider.canonical_id:
            continue
        grouped[provider.canonical_id].append(provider)
        for raw_candidate in (provider.tvg_id, provider.provider_id):
            candidate = (raw_candidate or "").strip()
            if not candidate or candidate in canonical_ids:
                continue
            existing = alias_to_canonical.get(candidate)
            if existing and existing != provider.canonical_id:
                continue
            alias_to_canonical[candidate] = provider.canonical_id
    return grouped, alias_to_canonical


@contextmanager
def _output_stream(path: Path, *, compressed: bool) -> Iterator[BinaryIO]:
    if compressed:
        with (
            path.open("wb") as raw_stream,
            gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=6,
                fileobj=raw_stream,
                mtime=0,
            ) as gzip_stream,
        ):
            yield gzip_stream
    else:
        with path.open("wb") as stream:
            yield stream


def write_xmltv(
    path: str | Path,
    channels: list[CanonicalChannel],
    programmes: list[Programme],
    *,
    provider_channels: list[Channel] | None = None,
    emit_provider_aliases: bool = False,
    max_description_chars: int = 5000,
) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    provider_channels = provider_channels or []
    grouped, alias_to_canonical = _alias_ids(channels, provider_channels)
    if not emit_provider_aliases:
        alias_to_canonical = {}

    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with (
            _output_stream(temporary, compressed=destination.suffix == ".gz") as stream,
            etree.xmlfile(stream, encoding="UTF-8") as document,
        ):
            document.write_declaration()
            with document.element(
                "tv",
                {
                    "generator-info-name": "KR Live EPG",
                    "generator-info-url": "https://localhost.invalid/kr-live-epg",
                },
            ):
                for channel in sorted(channels, key=lambda item: item.name.casefold()):
                    provider_names = [item.name for item in grouped.get(channel.id, [])]
                    document.write(
                        _channel_element(
                            channel.id,
                            channel.name,
                            aliases=[*channel.aliases, *provider_names],
                            logo=channel.logo,
                        )
                    )
                if emit_provider_aliases:
                    by_id = {channel.id: channel for channel in channels}
                    provider_by_alias = {}
                    for item in provider_channels:
                        if not item.canonical_id:
                            continue
                        for raw_alias in (item.tvg_id, item.provider_id):
                            if raw_alias and raw_alias.strip():
                                provider_by_alias[raw_alias.strip()] = item
                    for alias_id, canonical_id in sorted(alias_to_canonical.items()):
                        provider = provider_by_alias.get(alias_id)
                        canonical = by_id.get(canonical_id)
                        if provider and canonical:
                            document.write(
                                _channel_element(
                                    alias_id,
                                    provider.name,
                                    aliases=[canonical.name],
                                    logo=provider.logo or canonical.logo,
                                )
                            )
                aliases_by_canonical: dict[str, list[str]] = defaultdict(list)
                for alias, canonical in alias_to_canonical.items():
                    aliases_by_canonical[canonical].append(alias)
                for programme in programmes:
                    document.write(
                        _programme_element(programme, programme.channel_id, max_description_chars)
                    )
                    for alias_id in aliases_by_canonical.get(programme.channel_id, []):
                        document.write(
                            _programme_element(programme, alias_id, max_description_chars)
                        )
        validate_xmltv(temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination.stat().st_size


def validate_xmltv(path: str | Path) -> None:
    file_path = Path(path)
    raw = file_path.read_bytes()
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    try:
        root = etree.fromstring(raw, parser)
    except etree.XMLSyntaxError as exc:
        raise ValidationError(f"Wygenerowany XMLTV jest nieprawidłowy: {exc}") from exc
    if root.tag != "tv":
        raise ValidationError("Wygenerowany plik nie ma elementu <tv>")
    channel_ids = [item.get("id") or "" for item in root.findall("channel")]
    if len(channel_ids) != len(set(channel_ids)):
        raise ValidationError("XMLTV zawiera zduplikowane identyfikatory kanałów")
    known = set(channel_ids)
    for programme in root.findall("programme"):
        if programme.get("channel") not in known:
            raise ValidationError("Program odwołuje się do nieistniejącego kanału")
        start = parse_xmltv_datetime(programme.get("start") or "")
        stop = parse_xmltv_datetime(programme.get("stop") or "")
        if stop <= start:
            raise ValidationError("Program ma czas końca wcześniejszy od początku")
