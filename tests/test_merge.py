from datetime import UTC, datetime, timedelta

from kr_live_epg.merge import merge_programmes
from kr_live_epg.models import Credits, Programme


def _programme(
    title: str, start: datetime, stop: datetime, priority: int, source: str
) -> Programme:
    return Programme(
        channel_id="polsat.pl",
        start=start,
        stop=stop,
        title=title,
        source_id=source,
        source_priority=priority,
    )


def test_live_override_removes_stale_overlapping_slots() -> None:
    start = datetime(2026, 9, 26, 18, tzinfo=UTC)
    old_one = _programme("Kabaret", start, start + timedelta(hours=1), 50, "guide")
    old_two = _programme(
        "Film", start + timedelta(hours=1), start + timedelta(hours=3), 50, "guide"
    )
    live = _programme(
        "Finał mistrzostw Europy w siatkówce",
        start,
        start + timedelta(hours=3),
        1000,
        "sentinel:official",
    )
    merged = merge_programmes([old_one, old_two, live])
    assert [item.title for item in merged] == [live.title]


def test_equivalent_sources_enrich_description_and_credits() -> None:
    start = datetime(2026, 9, 26, 18, tzinfo=UTC)
    rich = _programme("Film", start, start + timedelta(hours=2), 40, "rich")
    rich.description = "Pełny opis"
    rich.credits = Credits(actors=["Anna Nowak"])
    authoritative = _programme("Film", start, start + timedelta(hours=2), 80, "official")
    merged = merge_programmes([rich, authoritative])
    assert len(merged) == 1
    assert merged[0].source_id == "official"
    assert merged[0].description == "Pełny opis"
    assert merged[0].credits.actors == ["Anna Nowak"]


def test_real_listing_always_beats_higher_priority_placeholder() -> None:
    start = datetime(2026, 9, 26, 18, tzinfo=UTC)
    placeholder = _programme(
        "Kanał eventowy transmisje na żywo", start, start + timedelta(hours=3), 100, "filler"
    )
    placeholder.is_placeholder = True
    real = _programme("Finał siatkówki", start, start + timedelta(hours=3), 10, "official")
    assert [item.title for item in merge_programmes([placeholder, real])] == [real.title]
