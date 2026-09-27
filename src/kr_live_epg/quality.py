from __future__ import annotations

import re
from enum import StrEnum

from unidecode import unidecode


class ProgrammeQuality(StrEnum):
    CONTENT = "content"
    PLACEHOLDER = "placeholder"
    SOURCE_AD = "source-ad"


def _fold(value: str | None) -> str:
    text = unidecode(value or "").casefold()
    return " ".join(text.split())


_SOURCE_AD_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"\bbrak zrodla\b",
        r"\bepg\s+dostarcza\b",
        r"\bkodiwpigulce(?:\.pl)?\b",
        r"\bserwis\s+kwp\b",
    )
)

_PLACEHOLDER_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^brak informacji[.! ]*$",
        r"^kanal eventowy(?:\s*[-:]?)?\s*transmisje na zywo[.! ]*$",
        r"^wydarzenia pay[- ]per[- ]view(?:\.|\s|$)",
        r"^przerwa techniczna[.! ]*$",
        r"^zakonczenie programu(?:\s*\(przerwa techniczna\))?[.! ]*$",
    )
)


def classify_programme(title: str, description: str | None = None) -> ProgrammeQuality:
    """Classify upstream filler without guessing missing schedule content.

    Source advertisements are discarded. Honest idle/event placeholders remain
    available as a last resort and always lose conflicts against real listings.
    """

    combined = _fold(f"{title} {description or ''}")
    if any(pattern.search(combined) for pattern in _SOURCE_AD_PATTERNS):
        return ProgrammeQuality.SOURCE_AD
    folded_title = _fold(title)
    if any(pattern.search(folded_title) for pattern in _PLACEHOLDER_PATTERNS):
        return ProgrammeQuality.PLACEHOLDER
    return ProgrammeQuality.CONTENT
