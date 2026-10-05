from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import yaml

from .models import CanonicalChannel, Channel
from .normalize import compact_signature, normalize_channel_name, slugify_channel


class ChannelRegistry:
    def __init__(self, channels: list[CanonicalChannel]) -> None:
        self.channels: dict[str, CanonicalChannel] = {channel.id: channel for channel in channels}
        self._reindex()

    @classmethod
    def load(cls, custom_path: str | None = None) -> ChannelRegistry:
        path = (
            Path(custom_path)
            if custom_path
            else Path(str(files("kr_live_epg.resources").joinpath("channels_pl.yaml")))
        )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        channels = [CanonicalChannel.model_validate(item) for item in raw.get("channels", [])]
        return cls(channels)

    def _reindex(self) -> None:
        self.alias_index: dict[str, set[str]] = {}
        self.compact_index: dict[str, set[str]] = {}
        self.primary_index: dict[str, set[str]] = {}
        for channel in self.channels.values():
            primary = normalize_channel_name(channel.name).normalized
            if primary:
                self.primary_index.setdefault(primary, set()).add(channel.id)
            for alias in [channel.name, channel.id, *channel.aliases, *channel.predecessor_ids]:
                normalized = normalize_channel_name(alias).normalized
                if normalized:
                    self.alias_index.setdefault(normalized, set()).add(channel.id)
                    self.compact_index.setdefault(compact_signature(alias), set()).add(channel.id)

    def get(self, channel_id: str) -> CanonicalChannel | None:
        return self.channels.get(channel_id)

    def get_by_primary_name(self, name: str) -> CanonicalChannel | None:
        candidates = self.primary_index.get(normalize_channel_name(name).normalized, set())
        if len(candidates) != 1:
            return None
        return self.channels[next(iter(candidates))]

    def merge_source_metadata(
        self, canonical: CanonicalChannel, channel: Channel
    ) -> CanonicalChannel:
        """Keep provider display names so clients can auto-map decorated playlist names."""

        canonical.aliases = list(
            dict.fromkeys([*canonical.aliases, channel.name, *channel.aliases])
        )
        if not canonical.logo and channel.logo:
            canonical.logo = channel.logo
        self._reindex()
        return canonical

    def add_or_merge_dynamic(self, channel: Channel) -> CanonicalChannel:
        primary = self.get_by_primary_name(channel.name)
        if primary:
            return primary
        candidates: set[str] = set()
        for alias in [channel.name, channel.tvg_id or "", *channel.aliases]:
            normalized = normalize_channel_name(alias).normalized
            candidates.update(self.alias_index.get(normalized, set()))
            candidates.update(self.compact_index.get(compact_signature(alias), set()))
        if len(candidates) == 1:
            existing = self.channels[next(iter(candidates))]
            return self.merge_source_metadata(existing, channel)

        base_id = f"{slugify_channel(channel.name)}.pl"
        dynamic_id = base_id
        counter = 2
        while dynamic_id in self.channels:
            dynamic_id = f"{base_id.removesuffix('.pl')}-{counter}.pl"
            counter += 1
        created = CanonicalChannel(
            id=dynamic_id,
            name=channel.name.strip(),
            # Upstream XMLTV aliases are untrusted metadata. Keeping them here
            # made unrelated stations share display names in the public guide.
            aliases=[],
            category=channel.group,
            logo=channel.logo,
        )
        self.channels[dynamic_id] = created
        self._reindex()
        return created

    def add_isolated_dynamic(self, channel: Channel) -> CanonicalChannel:
        """Create/reuse a channel by primary name without trusting source aliases."""

        if existing := self.get_by_primary_name(channel.name):
            return existing
        base_id = f"{slugify_channel(channel.name)}.pl"
        dynamic_id = base_id
        counter = 2
        while dynamic_id in self.channels:
            dynamic_id = f"{base_id.removesuffix('.pl')}-{counter}.pl"
            counter += 1
        created = CanonicalChannel(
            id=dynamic_id,
            name=channel.name.strip(),
            aliases=[],
            category=channel.group,
            logo=channel.logo,
        )
        self.channels[dynamic_id] = created
        self._reindex()
        return created

    def active(self) -> list[CanonicalChannel]:
        return [channel for channel in self.channels.values() if channel.active]
