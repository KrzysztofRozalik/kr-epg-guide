from datetime import UTC, datetime, timedelta

from kr_live_epg.descriptions import format_visible_description
from kr_live_epg.models import Credits, Programme


def test_visible_description_contains_metadata_and_repeat_status() -> None:
    start = datetime.now(UTC)
    programme = Programme(
        channel_id="tvn-turbo.pl",
        start=start,
        stop=start + timedelta(hours=1),
        title="Zakup kontrolowany",
        original_title="Controlled Purchase",
        description="Sprawdzamy używany samochód przed zakupem.",
        categories=["Program motoryzacyjny"],
        credits=Credits(presenters=["Jan Testowy"]),
        country=["Polska"],
        year=2026,
        episode_num="S03E04",
        is_repeat=True,
        source_id="fixture",
    )

    result = format_visible_description(programme)

    assert "Tytuł oryginalny: Controlled Purchase." in (result.description or "")
    assert "Produkcja: Polska, 2026." in (result.description or "")
    assert "Gatunek: Program motoryzacyjny." in (result.description or "")
    assert "Prowadzący: Jan Testowy." in (result.description or "")
    assert "Odcinek: S03E04." in (result.description or "")
    assert "Emisja: powtórka." in (result.description or "")
