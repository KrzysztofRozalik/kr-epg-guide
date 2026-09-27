from __future__ import annotations

import calendar
import hashlib
import html
import re
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import feedparser
from icalendar import Calendar
from lxml import etree
from lxml import html as lxml_html

from .config import SentinelConfig, SentinelFeedConfig, SentinelRuleConfig
from .http import HttpClient
from .models import DetectedEvent, FeedEntry, Programme

_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(r"\b([0-3]?\d)[.\-/]([01]?\d)(?:[.\-/](20\d{2}))?\b")
_ISO_DATE_RE = re.compile(r"\b(20\d{2})-([01]\d)-([0-3]\d)\b")
_HOUR = r"(?:[01]?\d|2[0-3])"
_TIME_RE = re.compile(rf"\b(?:o\s+)?(?:godz(?:ina|\.)?\s*)?({_HOUR})[:.]([0-5]\d)\b", re.I)
_END_RE = re.compile(rf"(?:do|[-\u2013\u2014])\s*({_HOUR})[:.]([0-5]\d)\b", re.I)


def _plain(value: str) -> str:
    return " ".join(html.unescape(_TAG_RE.sub(" ", value or "")).split())


def _feed_datetime(entry: object) -> datetime | None:
    for attribute in ("published", "updated", "created"):
        value = getattr(entry, attribute, None)
        if value:
            try:
                parsed = parsedate_to_datetime(str(value))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
            except (TypeError, ValueError, OverflowError):
                pass
    for attribute in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attribute, None)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
    return None


def _as_datetime(value: object, timezone: ZoneInfo) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone) if value.tzinfo is None else value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone)
    return None


class LiveSentinel:
    """Conservative event detector: one official source or two independent feeds."""

    def __init__(
        self,
        config: SentinelConfig,
        http: HttpClient,
        *,
        timezone: str = "Europe/Warsaw",
    ) -> None:
        self.config = config
        self.http = http
        self.timezone = ZoneInfo(timezone)
        self.errors: list[str] = []

    def _rss_entries(self, feed: SentinelFeedConfig) -> list[FeedEntry]:
        parsed = feedparser.parse(self.http.get_bytes(feed.url, headers=feed.headers))
        entries: list[FeedEntry] = []
        for item in parsed.entries:
            title = _plain(str(getattr(item, "title", "")))
            body = _plain(str(getattr(item, "summary", "") or getattr(item, "description", "")))
            if not title and not body:
                continue
            entries.append(
                FeedEntry(
                    source_id=feed.id,
                    title=title,
                    body=body,
                    url=str(getattr(item, "link", "")) or None,
                    published_at=_feed_datetime(item),
                )
            )
        return entries

    @staticmethod
    def _xpath_text(node: etree._Element, xpath: str) -> str:
        values: list[str] = []
        for result in node.xpath(xpath):
            if isinstance(result, etree._Element):
                values.extend(result.itertext())
            else:
                values.append(str(result))
        return _plain(" ".join(values))

    def _html_entries(self, feed: SentinelFeedConfig) -> list[FeedEntry]:
        document = lxml_html.fromstring(self.http.get_bytes(feed.url, headers=feed.headers))
        entries: list[FeedEntry] = []
        for item in document.xpath(feed.item_xpath or "//body"):
            if not isinstance(item, etree._Element):
                continue
            title = self._xpath_text(item, feed.title_xpath)
            body = self._xpath_text(item, feed.body_xpath)
            links = item.xpath(feed.link_xpath)
            link = str(links[0]).strip() if links else ""
            if not title and not body:
                continue
            entries.append(
                FeedEntry(
                    source_id=feed.id,
                    title=title or body[:160],
                    body=body,
                    url=urljoin(feed.url, link) if link else feed.url,
                )
            )
        return entries

    def _time_from_text(
        self, text: str, published: datetime | None, now: datetime
    ) -> tuple[datetime, datetime] | None:
        time_match = _TIME_RE.search(text)
        if not time_match:
            return None
        iso_date_match = _ISO_DATE_RE.search(text)
        date_match = _DATE_RE.search(text)
        lowered = text.casefold()
        if iso_date_match:
            year, month, day = iso_date_match.groups()
            try:
                selected_date = date(int(year), int(month), int(day))
            except ValueError:
                return None
        elif date_match:
            day, month, year = date_match.groups()
            try:
                selected_date = date(
                    int(year or now.astimezone(self.timezone).year), int(month), int(day)
                )
            except ValueError:
                return None
        elif "jutro" in lowered:
            selected_date = now.astimezone(self.timezone).date() + timedelta(days=1)
        elif "dzisiaj" in lowered:
            selected_date = now.astimezone(self.timezone).date()
        elif published:
            selected_date = published.astimezone(self.timezone).date()
        else:
            return None
        start = datetime.combine(
            selected_date,
            time(int(time_match.group(1)), int(time_match.group(2))),
            tzinfo=self.timezone,
        )
        end_match = _END_RE.search(text[time_match.end() :])
        if end_match:
            stop = datetime.combine(
                selected_date,
                time(int(end_match.group(1)), int(end_match.group(2))),
                tzinfo=self.timezone,
            )
            if stop <= start:
                stop += timedelta(days=1)
        else:
            stop = start
        return start, stop

    def _from_rule(
        self,
        feed: SentinelFeedConfig,
        rule: SentinelRuleConfig,
        entry: FeedEntry,
        now: datetime,
        fixed_times: tuple[datetime, datetime] | None = None,
    ) -> DetectedEvent | None:
        text = f"{entry.title}\n{entry.body}".strip()
        match = re.search(rule.pattern, text, re.IGNORECASE)
        if not match:
            return None
        folded = text.casefold()
        if rule.required_terms and not all(
            term.casefold() in folded for term in rule.required_terms
        ):
            return None
        times = fixed_times or self._time_from_text(text, entry.published_at, now)
        if not times:
            return None
        start, stop = times
        if stop <= start:
            stop = start + timedelta(minutes=rule.default_duration_minutes)
        groups = match.groupdict()
        title = rule.title_template or groups.get("title") or entry.title
        confidence = 0.96 if feed.official else 0.74
        return DetectedEvent(
            source_id=feed.id,
            channel_ids=rule.channel_ids,
            start=start,
            stop=stop,
            title=" ".join(title.split()),
            description=(entry.body or entry.title)[:500],
            confidence=confidence,
            evidence_url=entry.url,
        )

    def _ics_events(
        self, feed: SentinelFeedConfig, rules: list[SentinelRuleConfig], now: datetime
    ) -> list[tuple[DetectedEvent, SentinelRuleConfig]]:
        calendar_data = Calendar.from_ical(self.http.get_bytes(feed.url, headers=feed.headers))
        result: list[tuple[DetectedEvent, SentinelRuleConfig]] = []
        for component in calendar_data.walk("VEVENT"):
            summary = _plain(str(component.get("SUMMARY", "")))
            body = _plain(str(component.get("DESCRIPTION", "")))
            start = _as_datetime(component.decoded("DTSTART"), self.timezone)
            stop = (
                _as_datetime(component.decoded("DTEND"), self.timezone)
                if component.get("DTEND")
                else None
            )
            if not start:
                continue
            entry = FeedEntry(
                source_id=feed.id,
                title=summary,
                body=body,
                url=str(component.get("URL", "")) or None,
                published_at=start,
            )
            for rule in rules:
                event = self._from_rule(feed, rule, entry, now, (start, stop or start))
                if event:
                    result.append((event, rule))
        return result

    def collect(self, *, now: datetime | None = None) -> list[DetectedEvent]:
        if not self.config.enabled:
            return []
        now = now or datetime.now(UTC)
        candidates: list[tuple[DetectedEvent, SentinelRuleConfig]] = []
        for feed in (item for item in self.config.feeds if item.enabled):
            try:
                if feed.type == "ics":
                    candidates.extend(self._ics_events(feed, self.config.rules, now))
                    continue
                entries = (
                    self._html_entries(feed) if feed.type == "html" else self._rss_entries(feed)
                )
                for entry in entries:
                    for rule in self.config.rules:
                        event = self._from_rule(feed, rule, entry, now)
                        if event:
                            candidates.append((event, rule))
            except Exception as exc:
                self.errors.append(f"{feed.id}: {type(exc).__name__}")

        grouped: dict[str, list[tuple[DetectedEvent, SentinelRuleConfig]]] = defaultdict(list)
        for event, rule in candidates:
            rounded_minute = event.start.minute - event.start.minute % 15
            rounded_start = event.start.replace(minute=rounded_minute, second=0, microsecond=0)
            signature = "|".join(
                [
                    ",".join(sorted(event.channel_ids)),
                    rounded_start.astimezone(UTC).strftime("%Y%m%d%H%M"),
                ]
            )
            grouped[hashlib.sha256(signature.encode()).hexdigest()].append((event, rule))

        result: list[DetectedEvent] = []
        lower = now - timedelta(hours=3)
        upper = now + timedelta(hours=self.config.near_window_hours)
        for group in grouped.values():
            event, rule = max(group, key=lambda item: item[0].confidence)
            distinct_sources = {item[0].source_id for item in group}
            if len(distinct_sources) >= 2 and event.confidence < 0.9:
                event = event.model_copy(
                    update={
                        "confidence": 0.9,
                        "source_id": "+".join(sorted(distinct_sources)),
                    }
                )
            if event.confidence >= rule.min_confidence and lower <= event.start <= upper:
                result.append(event)
        return sorted(result, key=lambda item: item.start)


def events_to_programmes(events: list[DetectedEvent]) -> list[Programme]:
    result: list[Programme] = []
    for event in events:
        for channel_id in event.channel_ids:
            result.append(
                Programme(
                    channel_id=channel_id,
                    start=event.start,
                    stop=event.stop,
                    title=event.title,
                    description=event.description,
                    categories=["Sport", "Na żywo"],
                    url=event.evidence_url,
                    is_live=event.is_live,
                    source_id=f"sentinel:{event.source_id}",
                    source_priority=1000,
                    confidence=event.confidence,
                )
            )
    return result
