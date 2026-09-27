from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from unidecode import unidecode

# Tokens describing transport quality, language or a reseller package. They are
# deliberately separate from words such as PREMIUM, EXTRA, SPORT, FILM and NEWS,
# which are often part of the real station name.
_NOISE_TOKENS = {
    "1080i",
    "1080p",
    "2160p",
    "25fps",
    "50fps",
    "4k",
    "8k",
    "backup",
    "bckp",
    "dd51",
    "dolby",
    "fhd",
    "fullhd",
    "full-hd",
    "h264",
    "h265",
    "hd",
    "hdr",
    "hdr10",
    "hevc",
    "low",
    "multi",
    "multiaudio",
    "pl",
    "pol",
    "raw",
    "sd",
    "source",
    "uhd",
    "vip",
    "x264",
    "x265",
}

_SEMANTIC_TOKENS = {
    "2",
    "3",
    "4",
    "24",
    "action",
    "adventure",
    "cafe",
    "comedy",
    "document",
    "doku",
    "extra",
    "fight",
    "film",
    "games",
    "gold",
    "historia",
    "history",
    "info",
    "kids",
    "kobieta",
    "kuchnia",
    "life",
    "max",
    "music",
    "news",
    "premium",
    "seriale",
    "sport",
    "style",
    "turbo",
}

_BRACKET_RE = re.compile(r"([\[({<])([^\])}>]{1,80})([\])}>])")
_SEPARATOR_RE = re.compile(r"[|:;\u2022\u00b7\u2015\u2013\u2014/_\\]+")
_NON_WORD_RE = re.compile(r"[^a-z0-9+]+")
_SPACE_RE = re.compile(r"\s+")
_QUALITY_PHRASES_RE = re.compile(
    r"\b(?:full\s*hd|ultra\s*hd|high\s*definition|h[ .-]?26[45]|"
    r"(?:25|50|60)\s*fps|dolby\s*(?:digital|5[ .]?1))\b",
    re.IGNORECASE,
)
_COUNTRY_PREFIX_RE = re.compile(
    r"^(?:(?:\[|\(|\{)?(?:pl|pol|polska)(?:\]|\)|\})?\s*[-:|•·]+\s*)+",
    re.IGNORECASE,
)
_COUNTRY_SUFFIX_RE = re.compile(
    r"(?:\s*[-:|•·]+\s*(?:\[|\(|\{)?(?:pl|pol|polska)(?:\]|\)|\})?)+$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class NormalizedName:
    raw: str
    normalized: str
    tokens: tuple[str, ...]
    numbers: tuple[str, ...]
    semantic_tokens: tuple[str, ...]


def _is_noise_fragment(fragment: str) -> bool:
    folded = unidecode(fragment).lower().replace(".", "").replace(" ", "")
    if folded in _NOISE_TOKENS:
        return True
    parts = [part for part in re.split(r"[\s,;|/+_-]+", folded) if part]
    return bool(parts) and all(part in _NOISE_TOKENS for part in parts)


def _drop_noise_brackets(value: str) -> str:
    previous = None
    while previous != value:
        previous = value

        def replace(match: re.Match[str]) -> str:
            return " " if _is_noise_fragment(match.group(2)) else f" {match.group(2)} "

        value = _BRACKET_RE.sub(replace, value)
    return value


def normalize_channel_name(value: str) -> NormalizedName:
    """Normalize reseller decorations without deleting semantic station identity."""

    raw = value.strip()
    text = unicodedata.normalize("NFKC", raw)
    text = text.replace("🇵🇱", " ")
    text = _COUNTRY_PREFIX_RE.sub("", text)
    text = _COUNTRY_SUFFIX_RE.sub("", text)
    text = _drop_noise_brackets(text)
    text = _QUALITY_PHRASES_RE.sub(" ", text)
    text = unidecode(text).lower()
    text = text.replace("&", " and ")
    # Keep the meaning of CANAL+ and similar brands instead of treating '+' as punctuation.
    text = re.sub(r"(?<=\w)\+(?=\s|$)", " plus ", text)
    text = _SEPARATOR_RE.sub(" ", text)
    text = _NON_WORD_RE.sub(" ", text)
    parts = [part for part in _SPACE_RE.split(text.strip()) if part]
    parts = [part for part in parts if part not in _NOISE_TOKENS]
    normalized = " ".join(parts)
    numbers = tuple(part for part in parts if part.isdigit())
    semantic = tuple(part for part in parts if part in _SEMANTIC_TOKENS)
    return NormalizedName(raw, normalized, tuple(parts), numbers, semantic)


def compact_signature(value: str) -> str:
    return normalize_channel_name(value).normalized.replace(" ", "")


def slugify_channel(value: str) -> str:
    normalized = normalize_channel_name(value).normalized
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "unknown-channel"


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    text = unidecode(text).lower()
    text = re.sub(r"\b(?:odc(?:inek)?|sezon|s)\.?\s*\d+\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return _SPACE_RE.sub(" ", text).strip()
