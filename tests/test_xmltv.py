import gzip
from datetime import UTC, datetime, timedelta

import pytest

from kr_live_epg.exceptions import SourceError
from kr_live_epg.models import CanonicalChannel, Credits, Programme
from kr_live_epg.providers.xmltv import parse_xmltv
from kr_live_epg.writer import validate_xmltv, write_xmltv


def test_parse_rich_xmltv() -> None:
    raw = """<?xml version="1.0" encoding="UTF-8"?>
    <tv>
      <channel id="movie.test"><display-name lang="pl">Film Test</display-name></channel>
      <programme start="20260926200000 +0200" stop="20260926220000 +0200" channel="movie.test">
        <title lang="pl">Przykładowy film</title><title lang="en">Example Movie</title>
        <desc lang="pl">Fabuła.</desc>
        <credits><director>Jan Kowalski</director><producer>Studio Test</producer>
          <actor>Anna Nowak</actor></credits>
        <date>2024</date><category lang="pl">Film</category><country>Polska</country>
        <episode-num system="onscreen">S01E02</episode-num><length units="minutes">120</length>
        <language>pl</language><orig-language>en</orig-language><keyword>przygoda</keyword>
        <previously-shown start="20250101120000 +0100" />
        <rating><value>12</value></rating><star-rating><value>8/10</value></star-rating>
        <review lang="pl">Dobra recenzja.</review>
      </programme>
    </tv>""".encode()
    guide = parse_xmltv(raw, source_id="fixture")
    programme = guide.programmes[0]
    assert programme.year == 2024
    assert programme.original_title == "Example Movie"
    assert programme.credits.directors == ["Jan Kowalski"]
    assert programme.credits.producers == ["Studio Test"]
    assert programme.credits.actors == ["Anna Nowak"]
    assert programme.country == ["Polska"]
    assert programme.duration_minutes == 120
    assert programme.original_language == "en"
    assert programme.keywords == ["przygoda"]
    assert programme.is_repeat is True
    assert programme.previously_shown_at is not None
    assert programme.reviews == ["Dobra recenzja."]


def test_write_and_validate_gzip(tmp_path) -> None:
    start = datetime(2026, 9, 26, 18, tzinfo=UTC)
    programme = Programme(
import gzip
from datetime import UTC, datetime, timedelta

import pytest
from lxml import etree

from kr_live_epg.exceptions import SourceError
from kr_live_epg.models import CanonicalChannel, Credits, Programme
from kr_live_epg.providers.xmltv import parse_xmltv
from kr_live_epg.writer import validate_xmltv, write_xmltv


def test_parse_rich_xmltv() -> None:
    raw = """<?xml version="1.0" encoding="UTF-8"?>
    <tv>
      <channel id="movie.test"><display-name lang="pl">Film Test</display-name></channel>
      <programme start="20260926200000 +0200" stop="20260926220000 +0200" channel="movie.test">
        <title lang="pl">Przykładowy film</title><title lang="en">Example Movie</title>
        <desc lang="pl">Fabuła.</desc>
        <credits><director>Jan Kowalski</director><producer>Studio Test</producer>
          <actor>Anna Nowak</actor></credits>
        <date>2024</date><category lang="pl">Film</category><country>Polska</country>
        <episode-num system="onscreen">S01E02</episode-num><length units="minutes">120</length>
        <language>pl</language><orig-language>en</orig-language><keyword>przygoda</keyword>
        <previously-shown start="20250101120000 +0100" />
        <rating><value>12</value></rating><star-rating><value>8/10</value></star-rating>
        <review lang="pl">Dobra recenzja.</review>
      </programme>
    </tv>""".encode()
    guide = parse_xmltv(raw, source_id="fixture")
    programme = guide.programmes[0]
    assert programme.year == 2024
    assert programme.original_title == "Example Movie"
    assert programme.credits.directors == ["Jan Kowalski"]
    assert programme.credits.producers == ["Studio Test"]
    assert programme.credits.actors == ["Anna Nowak"]
    assert programme.country == ["Polska"]
    assert programme.duration_minutes == 120
    assert programme.original_language == "en"
    assert programme.keywords == ["przygoda"]
    assert programme.is_repeat is True
    assert programme.previously_shown_at is not None
    assert programme.reviews == ["Dobra recenzja."]


def test_write_and_validate_gzip(tmp_path) -> None:
    start = datetime(2026, 9, 26, 18, tzinfo=UTC)
    programme = Programme(
        channel_id="film-test.pl",
        start=start,
        stop=start + timedelta(hours=2),
        title="Przykładowy film",
        description="Opis",
        credits=Credits(directors=["Jan Kowalski"], actors=["Anna Nowak"]),
        year=2024,
        categories=["Film"],
        source_id="fixture",
    )
    path = tmp_path / "epg.xml.gz"
    size = write_xmltv(
        path,
        [CanonicalChannel(id="film-test.pl", name="Film Test")],
        [programme],
    )
    assert size > 0
    validate_xmltv(path)
    second_path = tmp_path / "second.xml.gz"
    write_xmltv(
        second_path,
        [CanonicalChannel(id="film-test.pl", name="Film Test")],
        [programme],
    )
    assert path.read_bytes() == second_path.read_bytes()


def test_emits_tivimate_reseller_name_variants(tmp_path) -> None:
    path = tmp_path / "epg.xml.gz"
    write_xmltv(
        path,
        [CanonicalChannel(id="tvn.pl", name="TVN")],
        [],
    )
    root = etree.fromstring(gzip.decompress(path.read_bytes()))
    names = {item.text for item in root.findall("./channel/display-name")}
    assert "PL-VIP| TVN RAW" in names
    assert "PL| TVN FHD" in names
    assert "TVN HD PL" in names


def test_rejects_gzip_expansion_over_configured_limit() -> None:
    compressed = gzip.compress(b"A" * 1024)
    with pytest.raises(SourceError, match="przekracza limit"):
        parse_xmltv(compressed, source_id="bomb", max_uncompressed_bytes=100)


def test_discards_source_ad_and_marks_honest_placeholder() -> None:
    raw = b"""<tv>
      <channel id="fan"><display-name>FAN Klub</display-name></channel>
      <programme start="20260926200000 +0200" stop="20260926210000 +0200" channel="fan">
        <title>Brak zrodla. EPG dostarcza serwis http://kodiwpigulce.pl.</title>
      </programme>
      <programme start="20260926210000 +0200" stop="20260926220000 +0200" channel="fan">
        <title>Brak informacji</title>
      </programme>
    </tv>"""
    guide = parse_xmltv(raw, source_id="fixture")
    assert guide.rejected_programme_count == 1
    assert guide.placeholder_programme_count == 1
    assert len(guide.programmes) == 1
    assert guide.programmes[0].is_placeholder is True
        channel_id="film-test.pl",
        start=start,
        stop=start + timedelta(hours=2),
        title="Przykładowy film",
        description="Opis",
        credits=Credits(directors=["Jan Kowalski"], actors=["Anna Nowak"]),
        year=2024,
        categories=["Film"],
        source_id="fixture",
    )
    path = tmp_path / "epg.xml.gz"
    size = write_xmltv(
        path,
        [CanonicalChannel(id="film-test.pl", name="Film Test")],
        [programme],
    )
    assert size > 0
    validate_xmltv(path)
    second_path = tmp_path / "second.xml.gz"
    write_xmltv(
        second_path,
        [CanonicalChannel(id="film-test.pl", name="Film Test")],
        [programme],
    )
    assert path.read_bytes() == second_path.read_bytes()


def test_rejects_gzip_expansion_over_configured_limit() -> None:
    compressed = gzip.compress(b"A" * 1024)
    with pytest.raises(SourceError, match="przekracza limit"):
        parse_xmltv(compressed, source_id="bomb", max_uncompressed_bytes=100)


def test_discards_source_ad_and_marks_honest_placeholder() -> None:
    raw = b"""<tv>
      <channel id="fan"><display-name>FAN Klub</display-name></channel>
      <programme start="20260926200000 +0200" stop="20260926210000 +0200" channel="fan">
        <title>Brak zrodla. EPG dostarcza serwis http://kodiwpigulce.pl.</title>
      </programme>
      <programme start="20260926210000 +0200" stop="20260926220000 +0200" channel="fan">
        <title>Brak informacji</title>
      </programme>
    </tv>"""
    guide = parse_xmltv(raw, source_id="fixture")
    assert guide.rejected_programme_count == 1
    assert guide.placeholder_programme_count == 1
    assert len(guide.programmes) == 1
    assert guide.programmes[0].is_placeholder is True
