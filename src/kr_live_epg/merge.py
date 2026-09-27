from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from datetime import datetime

from .models import Programme
from .normalize import normalize_title

_EQUIVALENCE_SECONDS = 4 * 60


def _precedence(programme: Programme) -> tuple[int, int, float, float]:
    return (
        int(not programme.is_placeholder),
        programme.source_priority,
        programme.confidence,
        programme.source_updated_at.timestamp(),
    )


def _enrich(preferred: Programme, other: Programme) -> Programme:
    """Keep schedule authority while filling empty descriptive fields."""

    update: dict[str, object] = {
        "original_title": preferred.original_title or other.original_title,
        "description": preferred.description or other.description,
        "subtitle": preferred.subtitle or other.subtitle,
        "categories": list(dict.fromkeys([*preferred.categories, *other.categories])),
        "credits": preferred.credits.merge(other.credits),
        "year": preferred.year or other.year,
        "country": list(dict.fromkeys([*preferred.country, *other.country])),
        "production_companies": list(
            dict.fromkeys([*preferred.production_companies, *other.production_companies])
        ),
        "episode_num": preferred.episode_num or other.episode_num,
        "episode_num_system": (
            preferred.episode_num_system if preferred.episode_num else other.episode_num_system
        ),
        "duration_minutes": preferred.duration_minutes or other.duration_minutes,
        "icon": preferred.icon or other.icon,
        "url": preferred.url or other.url,
        "age_rating": preferred.age_rating or other.age_rating,
        "star_rating": preferred.star_rating or other.star_rating,
        "reviews": list(dict.fromkeys([*preferred.reviews, *other.reviews])),
        "keywords": list(dict.fromkeys([*preferred.keywords, *other.keywords])),
        "original_language": preferred.original_language or other.original_language,
        "is_live": preferred.is_live or other.is_live,
        "is_premiere": preferred.is_premiere or other.is_premiere,
        "is_new": preferred.is_new or other.is_new,
        "is_repeat": preferred.is_repeat or other.is_repeat,
        "is_placeholder": preferred.is_placeholder and other.is_placeholder,
        "previously_shown_at": preferred.previously_shown_at or other.previously_shown_at,
    }
    for field, value in update.items():
        setattr(preferred, field, value)
    return preferred


def merge_programmes(programmes: list[Programme]) -> list[Programme]:
    """Deterministic priority merge; live/sentinel entries can replace stale slots."""

    by_channel: dict[str, list[Programme]] = defaultdict(list)
    for programme in programmes:
        by_channel[programme.channel_id].append(programme)

    result: list[Programme] = []
    for channel_programmes in by_channel.values():
        equivalents: list[Programme] = []
        slots: dict[tuple[str, int], list[int]] = defaultdict(list)
        for candidate in sorted(channel_programmes, key=lambda item: item.start):
            normalized = normalize_title(candidate.title)
            bucket = int(candidate.start.timestamp()) // _EQUIVALENCE_SECONDS
            nearby = list(
                dict.fromkeys(
                    index
                    for candidate_bucket in (bucket - 1, bucket, bucket + 1)
                    for index in slots.get((normalized, candidate_bucket), [])
                )
            )
            match_index = next(
                (
                    index
                    for index in nearby
                    if abs((equivalents[index].start - candidate.start).total_seconds())
                    <= _EQUIVALENCE_SECONDS
                ),
                None,
            )
            if match_index is None:
                equivalents.append(candidate)
                slots[(normalized, bucket)].append(len(equivalents) - 1)
                continue
            current = equivalents[match_index]
            if _precedence(candidate) > _precedence(current):
                equivalents[match_index] = _enrich(candidate, current)
            else:
                equivalents[match_index] = _enrich(current, candidate)
            winning_bucket = int(equivalents[match_index].start.timestamp()) // _EQUIVALENCE_SECONDS
            if match_index not in slots[(normalized, winning_bucket)]:
                slots[(normalized, winning_bucket)].append(match_index)

        accepted: list[Programme] = []
        accepted_starts: list[datetime] = []
        for candidate in sorted(equivalents, key=_precedence, reverse=True):
            position = bisect_left(accepted_starts, candidate.start)
            overlaps_previous = position > 0 and accepted[position - 1].stop > candidate.start
            overlaps_next = position < len(accepted) and candidate.stop > accepted[position].start
            if not overlaps_previous and not overlaps_next:
                accepted.insert(position, candidate)
                accepted_starts.insert(position, candidate.start)
            # A matching high-priority slot already won. Descriptive fields have
            # been merged above; conflicting titles must not coexist in XMLTV.
        result.extend(accepted)

    return sorted(result, key=lambda item: (item.channel_id, item.start, item.stop))
