from __future__ import annotations

from .models import Programme


def _sentence(label: str, values: list[str], *, limit: int | None = None) -> str | None:
    clean = list(dict.fromkeys(value.strip() for value in values if value.strip()))
    if limit is not None:
        clean = clean[:limit]
    return f"{label}: {', '.join(clean)}." if clean else None


def visible_description(programme: Programme) -> str | None:
    """Render key XMLTV metadata for players whose details screen is limited."""
    facts: list[str] = []
    if (
        programme.original_title
        and programme.original_title.casefold() != programme.title.casefold()
    ):
        facts.append(f"Tytuł oryginalny: {programme.original_title}.")

    production = list(programme.country)
    if programme.year:
        production.append(str(programme.year))
    if value := _sentence("Produkcja", production):
        facts.append(value)

    companies = list(dict.fromkeys([*programme.production_companies, *programme.credits.producers]))
    if value := _sentence("Studio/producent", companies, limit=5):
        facts.append(value)
    if value := _sentence("Gatunek", programme.categories):
        facts.append(value)
    if value := _sentence("Reżyseria", programme.credits.directors):
        facts.append(value)
    if value := _sentence("Obsada", programme.credits.actors, limit=12):
        facts.append(value)
    if value := _sentence("Prowadzący", programme.credits.presenters, limit=6):
        facts.append(value)
    if value := _sentence("Goście", programme.credits.guests, limit=8):
        facts.append(value)
    if programme.episode_num:
        facts.append(f"Odcinek: {programme.episode_num}.")
    if programme.duration_minutes:
        facts.append(f"Czas trwania: {programme.duration_minutes} min.")

    broadcast_flags: list[str] = []
    if programme.is_live:
        broadcast_flags.append("na żywo")
    if programme.is_premiere:
        broadcast_flags.append("premiera")
    if programme.is_new:
        broadcast_flags.append("nowy odcinek")
    if programme.is_repeat:
        broadcast_flags.append("powtórka")
    if broadcast_flags:
        facts.append("Emisja: " + ", ".join(broadcast_flags) + ".")

    if not facts:
        return programme.description
    details = " ".join(facts)
    return "\n\n".join(part for part in [programme.description, details] if part and part.strip())


def format_visible_description(programme: Programme) -> Programme:
    """Return a convenient enriched copy for non-streaming callers and tests."""

    description = visible_description(programme)
    if description == programme.description:
        return programme
    return programme.model_copy(update={"description": description})
