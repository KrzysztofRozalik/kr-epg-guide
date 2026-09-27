from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator


class PlaylistKind(StrEnum):
    NONE = "none"
    M3U = "m3u"
    XTREAM = "xtream"
    STALKER = "stalker"


class Channel(BaseModel):
    """A channel as exposed by a provider or an XMLTV source."""

    source_id: str
    provider_id: str
    name: str
    tvg_id: str | None = None
    group: str | None = None
    logo: str | None = None
    stream_url: str | None = Field(default=None, repr=False)
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, str] = Field(default_factory=dict)
    canonical_id: str | None = None
    canonical_name: str | None = None
    match_score: float | None = None
    match_method: str | None = None

    @field_validator("name")
    @classmethod
    def name_cannot_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("channel name cannot be empty")
        return value


class CanonicalChannel(BaseModel):
    id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    category: str | None = None
    country: str = "PL"
    logo: str | None = None
    active: bool = True
    predecessor_ids: list[str] = Field(default_factory=list)


class Credits(BaseModel):
    directors: list[str] = Field(default_factory=list)
    producers: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    writers: list[str] = Field(default_factory=list)
    presenters: list[str] = Field(default_factory=list)
    commentators: list[str] = Field(default_factory=list)
    guests: list[str] = Field(default_factory=list)

    def merge(self, other: Credits) -> Credits:
        def unique(*groups: list[str]) -> list[str]:
            return list(
                dict.fromkeys(item.strip() for group in groups for item in group if item.strip())
            )

        return Credits(
            directors=unique(self.directors, other.directors),
            producers=unique(self.producers, other.producers),
            actors=unique(self.actors, other.actors),
            writers=unique(self.writers, other.writers),
            presenters=unique(self.presenters, other.presenters),
            commentators=unique(self.commentators, other.commentators),
            guests=unique(self.guests, other.guests),
        )


class Programme(BaseModel):
    channel_id: str
    start: datetime
    stop: datetime
    title: str
    original_title: str | None = None
    subtitle: str | None = None
    description: str | None = None
    categories: list[str] = Field(default_factory=list)
    credits: Credits = Field(default_factory=Credits)
    year: int | None = None
    country: list[str] = Field(default_factory=list)
    production_companies: list[str] = Field(default_factory=list)
    episode_num: str | None = None
    episode_num_system: str = "onscreen"
    duration_minutes: int | None = Field(default=None, ge=1)
    icon: str | None = None
    url: str | None = None
    age_rating: str | None = None
    star_rating: str | None = None
    reviews: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    language: str = "pl"
    original_language: str | None = None
    is_live: bool = False
    is_premiere: bool = False
    is_new: bool = False
    is_repeat: bool = False
    is_placeholder: bool = False
    previously_shown_at: datetime | None = None
    source_id: str
    source_priority: int = 0
    confidence: float = 1.0
    source_updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("start", "stop", "previously_shown_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            raise ValueError("programme datetimes must be timezone-aware")
        return value

    @model_validator(mode="after")
    def stop_after_start(self) -> Programme:
        if self.stop <= self.start:
            raise ValueError("programme stop must be after start")
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("programme title cannot be empty")
        return self


class Guide(BaseModel):
    source_id: str
    channels: list[Channel] = Field(default_factory=list)
    programmes: list[Programme] = Field(default_factory=list)
    rejected_programme_count: int = 0
    placeholder_programme_count: int = 0
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MatchResult(BaseModel):
    canonical_id: str | None
    canonical_name: str | None
    score: float = 0.0
    method: str
    runner_up_score: float = 0.0
    ambiguous: bool = False


class BuildStats(BaseModel):
    profile: str
    started_at: datetime
    finished_at: datetime
    mode: str
    source_count: int
    playlist_channel_count: int
    matched_channel_count: int
    unmatched_channel_count: int
    programme_count: int
    real_programme_count: int = 0
    placeholder_programme_count: int = 0
    channels_with_real_epg: int = 0
    placeholder_only_channel_count: int = 0
    empty_channel_count: int = 0
    live_override_count: int
    output_bytes: int
    warnings: list[str] = Field(default_factory=list)


class FeedEntry(BaseModel):
    source_id: str
    title: str
    body: str = ""
    url: str | None = None
    published_at: datetime | None = None


class DetectedEvent(BaseModel):
    source_id: str
    channel_ids: list[str]
    start: datetime
    stop: datetime
    title: str
    description: str | None = None
    confidence: float
    evidence_url: str | None = None
    is_live: bool = True
