from datetime import UTC, datetime, timedelta

from kr_live_epg.config import TmdbConfig
from kr_live_epg.descriptions import format_visible_description
from kr_live_epg.metadata import TmdbEnricher
from kr_live_epg.models import Programme
from kr_live_epg.state import StateStore


def test_tmdb_movie_metadata_adds_production_facts_to_visible_description(tmp_path) -> None:
    programme = Programme(
        channel_id="film.test",
        start=datetime.now(UTC),
        stop=datetime.now(UTC) + timedelta(hours=2),
        title="Przykładowy film",
        categories=["Film"],
        source_id="fixture",
    )
    enricher = TmdbEnricher(
        TmdbConfig(enabled=False),
        None,  # type: ignore[arg-type]
        StateStore(tmp_path / "state.sqlite3"),
    )
    data = {
        "id": 42,
        "overview": "Opis fabuły.",
        "original_title": "Example Movie",
        "original_language": "en",
        "release_date": "2024-01-02",
        "runtime": 121,
        "production_countries": [{"name": "United States of America"}],
        "production_companies": [{"name": "Example Studio"}],
        "genres": [{"name": "Science Fiction"}],
        "credits": {
            "cast": [{"name": "Anna Nowak"}],
            "crew": [
                {"name": "Jan Kowalski", "job": "Director"},
                {"name": "Ewa Test", "job": "Producer"},
            ],
        },
    }

    enriched = format_visible_description(enricher._apply(programme, data))

    assert enriched.original_title == "Example Movie"
    assert enriched.year == 2024
    assert enriched.duration_minutes == 121
    assert enriched.production_companies == ["Example Studio"]
    assert "Science Fiction" in enriched.categories
    assert enriched.credits.producers == ["Ewa Test"]
    assert "Produkcja: United States of America, 2024." in (enriched.description or "")
    assert "Studio/producent: Example Studio, Ewa Test." in (enriched.description or "")
