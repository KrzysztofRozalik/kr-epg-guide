from datetime import UTC, datetime

from kr_live_epg.config import SentinelConfig, SentinelFeedConfig, SentinelRuleConfig
from kr_live_epg.sentinel import LiveSentinel, events_to_programmes


class FakeHttp:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def get_bytes(self, *args, **kwargs) -> bytes:
        return self.payload


def test_official_last_minute_event_becomes_high_priority_programme() -> None:
    payload = b"""<?xml version="1.0"?><rss version="2.0"><channel><item>
      <title>Final siatkowki - transmisja dzisiaj o 20:30</title>
      <description>Transmisja na otwartym kanale.</description>
      <link>https://official.example/event</link>
    </item></channel></rss>"""
    config = SentinelConfig(
        enabled=True,
        feeds=[
            SentinelFeedConfig(id="official", url="https://official.example/rss", official=True)
        ],
        rules=[
            SentinelRuleConfig(
                id="volleyball",
                pattern=r"(?P<title>Final siatkowki)",
                channel_ids=["polsat.pl"],
                required_terms=["transmisja"],
            )
        ],
    )
    now = datetime(2026, 9, 26, 10, tzinfo=UTC)
    events = LiveSentinel(config, FakeHttp(payload)).collect(now=now)  # type: ignore[arg-type]
    assert len(events) == 1
    programmes = events_to_programmes(events)
    assert programmes[0].source_priority == 1000
    assert programmes[0].is_live
    assert programmes[0].channel_id == "polsat.pl"


def test_authorised_html_event_page_can_supply_vod_fallback() -> None:
    payload = """<html><body><article>
      <h2>Gala KSW</h2>
      <p>Oficjalna transmisja dzisiaj o 21:00 na VOD.</p>
      <a href="/ksw">Szczegóły</a>
    </article></body></html>""".encode()
    config = SentinelConfig(
        enabled=True,
        feeds=[
            SentinelFeedConfig(
                id="events",
                url="https://official.example/events",
                type="html",
                item_xpath="//article",
                title_xpath=".//h2//text()",
                official=True,
            )
        ],
        rules=[
            SentinelRuleConfig(
                id="ksw",
                pattern=r"(?P<title>Gala KSW)",
                channel_ids=["vod-201.pl"],
                required_terms=["transmisja"],
            )
        ],
    )
    now = datetime(2026, 9, 26, 10, tzinfo=UTC)
    events = LiveSentinel(config, FakeHttp(payload)).collect(now=now)  # type: ignore[arg-type]
    assert len(events) == 1
    assert events[0].channel_ids == ["vod-201.pl"]
    assert events[0].evidence_url == "https://official.example/ksw"


def test_official_iso_dated_event_can_be_announced_two_weeks_ahead() -> None:
    payload = b"""<html><body><section id="events"><article>
      <h2>XTB KSW 122</h2><p>2026-10-10 19:00:00</p>
    </article></section></body></html>"""
    config = SentinelConfig(
        enabled=True,
        near_window_hours=336,
        feeds=[
            SentinelFeedConfig(
                id="ksw-official",
                url="https://www.kswmma.com/",
                type="html",
                item_xpath="//article",
                official=True,
            )
        ],
        rules=[
            SentinelRuleConfig(
                id="ksw-gala",
                pattern=r"(?P<title>XTB\s+KSW\s+\d+)",
                channel_ids=["ksw.pl"],
                required_terms=[],
                default_duration_minutes=300,
            )
        ],
    )
    now = datetime(2026, 9, 27, 17, tzinfo=UTC)
    events = LiveSentinel(config, FakeHttp(payload)).collect(now=now)  # type: ignore[arg-type]
    assert len(events) == 1
    assert events[0].title == "XTB KSW 122"
    assert events[0].start.isoformat() == "2026-10-10T19:00:00+02:00"
    assert events[0].stop.isoformat() == "2026-10-11T00:00:00+02:00"
