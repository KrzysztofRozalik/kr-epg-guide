from __future__ import annotations

from typing import Protocol

from ..models import Channel, Guide


class GuideProvider(Protocol):
    def fetch(self) -> Guide: ...


class PlaylistProvider(Protocol):
    def fetch_channels(self) -> list[Channel]: ...
