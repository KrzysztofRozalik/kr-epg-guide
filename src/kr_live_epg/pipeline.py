from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .config import AppConfig, ProfileConfig
from .exceptions import SourceError
from .http import HttpClient
from .logos import LogoCache
from .m3u import load_m3u, render_m3u
from .matcher import ChannelMatcher
from .merge import merge_programmes
from .metadata import TmdbEnricher
from .models import BuildStats, CanonicalChannel, Channel, Guide, PlaylistKind, Programme
from .providers import StalkerProvider, XmltvProvider, XtreamProvider
from .registry import ChannelRegistry
from .sentinel import LiveSentinel, events_to_programmes
from .state import StateStore
from .storage import Publisher
from .writer import write_xmltv


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


class EpgPipeline:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.state = StateStore(config.state_path)
        self.publisher = Publisher(config.storage)

    def _fetch_programmes(
        self, http: HttpClient, registry: ChannelRegistry
    ) -> tuple[list[Programme], list[str], int]:
        sources = [source for source in self.config.guide_sources if source.enabled]
        cache_directory = Path(self.config.state_path).parent / "source-cache"
        warnings: list[str] = []
        programmes: list[Programme] = []
        successful_sources = 0
        for source in sources:
            try:
                provider = XmltvProvider(source, http, cache_directory=cache_directory)
                guide = provider.fetch()
                programmes.extend(self._canonicalize_guides([guide], registry))
                successful_sources += 1
                if guide.rejected_programme_count:
                    warnings.append(
                        f"{source.id}: odrzucono {guide.rejected_programme_count} "
                        "reklam i fałszywych wpisów EPG"
                    )
                if provider.used_stale_cache:
                    warnings.append(f"{source.id}: użyto ostatniej poprawnej kopii z cache")
            except Exception as exc:
                warnings.append(f"{source.id}: {type(exc).__name__}: {exc}")
        return programmes, warnings, successful_sources

    @staticmethod
    def _canonicalize_guides(guides: list[Guide], registry: ChannelRegistry) -> list[Programme]:
        all_programmes: list[Programme] = []
        for guide in guides:
            source_map: dict[str, str] = {}
            matcher = ChannelMatcher(registry, threshold=88, margin=5)
            programme_channel_ids = {programme.channel_id for programme in guide.programmes}
            for channel in guide.channels:
                # Empty catalogue aliases (notably numbered virtual event feeds)
                # must not collapse several real provider channels into one ID.
                if channel.provider_id not in programme_channel_ids:
                    match = matcher.match(channel)
                    canonical = registry.get(match.canonical_id) if match.canonical_id else None
                    if canonical and not canonical.logo and channel.logo:
                        canonical.logo = channel.logo
                    continue
                match = matcher.match(channel)
                if match.canonical_id:
                    canonical = registry.get(match.canonical_id)
                else:
                    canonical = registry.add_or_merge_dynamic(channel)
                    matcher = ChannelMatcher(registry, threshold=88, margin=5)
                if not canonical:
                    continue
                source_map[channel.provider_id] = canonical.id
                if channel.tvg_id:
                    source_map[channel.tvg_id] = canonical.id
                if not canonical.logo and channel.logo:
                    canonical.logo = channel.logo
            for programme in guide.programmes:
                canonical_id = source_map.get(programme.channel_id)
                if canonical_id is None:
                    synthetic = Channel(
                        source_id=guide.source_id,
                        provider_id=programme.channel_id,
                        tvg_id=programme.channel_id,
                        name=programme.channel_id,
                    )
                    match = matcher.match(synthetic)
                    canonical_id = match.canonical_id
                if canonical_id:
                    programme.channel_id = canonical_id
                    all_programmes.append(programme)
        return all_programmes

    @staticmethod
    def _playlist_channels(profile: ProfileConfig, http: HttpClient) -> list[Channel]:
        playlist = profile.playlist
        if playlist.type == PlaylistKind.M3U:
            channels = load_m3u(path=playlist.path, url=playlist.url, http=http)
            for channel in channels:
                channel.source_id = playlist.source_id
            return channels
        if playlist.type == PlaylistKind.XTREAM:
            return XtreamProvider(playlist, http).fetch_channels()
        if playlist.type == PlaylistKind.STALKER:
            return StalkerProvider(playlist, http).fetch_channels()
        return []

    def _match_playlist(
        self,
        profile_name: str,
        profile: ProfileConfig,
        channels: list[Channel],
        registry: ChannelRegistry,
    ) -> tuple[list[Channel], int]:
        matcher = ChannelMatcher(
            registry,
            threshold=profile.auto_match_threshold,
            margin=profile.auto_match_margin,
        )
        unmatched = 0
        for channel in channels:
            match = matcher.match(channel)
            canonical = registry.get(match.canonical_id) if match.canonical_id else None
            if canonical is None:
                cached_id = self.state.get_mapping(profile_name, channel.provider_id)
                cached = registry.get(cached_id) if cached_id else None
                if cached and ChannelMatcher._score(channel.name, cached.name) >= 75:
                    canonical = cached
                    match.score = 75
                    match.method = "persistent-provider-id"
            if canonical is None and profile.include_unmatched_channels:
                canonical = registry.add_or_merge_dynamic(channel)
                match.score = 70
                match.method = "dynamic-unmatched"
                matcher = ChannelMatcher(
                    registry,
                    threshold=profile.auto_match_threshold,
                    margin=profile.auto_match_margin,
                )
            if canonical is None:
                unmatched += 1
                continue
            if not canonical.logo and channel.logo:
                canonical.logo = channel.logo
            channel.canonical_id = canonical.id
            channel.canonical_name = canonical.name
            channel.match_score = match.score
            channel.match_method = match.method
            self.state.put_mapping(
                profile_name,
                channel.provider_id,
                channel.name,
                canonical.id,
                match.score,
                match.method,
            )
        return channels, unmatched

    def _build_profile(
        self,
        profile_name: str,
        profile: ProfileConfig,
        registry: ChannelRegistry,
        base_programmes: list[Programme],
        live_programmes: list[Programme],
        http: HttpClient,
        source_count: int,
        inherited_warnings: list[str],
        mode: str,
    ) -> BuildStats:
        started = datetime.now(UTC)
        warnings = list(inherited_warnings)
        try:
            provider_channels = self._playlist_channels(profile, http)
        except Exception as exc:
            provider_channels = []
            warnings.append(f"playlist: {type(exc).__name__}: {exc}")
            if profile.playlist.type != PlaylistKind.NONE:
                raise SourceError(warnings[-1]) from exc
        provider_channels, unmatched = self._match_playlist(
            profile_name, profile, provider_channels, registry
        )

        if profile.playlist.type == PlaylistKind.NONE:
            # Keep known empty stations in the XMLTV catalogue so TiViMate can
            # still auto-map them now and receive data as soon as a source does.
            selected_ids = {channel.id for channel in registry.active()}
            provider_channels = [
                Channel(
                    source_id="canonical",
                    provider_id=channel_id,
                    name=(
                        registry.get(channel_id).name if registry.get(channel_id) else channel_id
                    ),
                    tvg_id=channel_id,
                    canonical_id=channel_id,
                    canonical_name=(
                        registry.get(channel_id).name if registry.get(channel_id) else channel_id
                    ),
                )
                for channel_id in sorted(selected_ids)
            ]
        else:
            selected_ids = {
                item.canonical_id for item in provider_channels if item.canonical_id is not None
            }

        now = datetime.now(UTC)
        lower = now - timedelta(days=profile.past_days)
        upper = now + timedelta(days=profile.future_days)
        candidates = [
            item
            for item in [*base_programmes, *live_programmes]
            if item.channel_id in selected_ids and item.stop > lower and item.start < upper
        ]
        programmes = merge_programmes(candidates)
        programmes = TmdbEnricher(self.config.tmdb, http, self.state).enrich(programmes)

        actual_by_channel: dict[str, int] = {channel_id: 0 for channel_id in selected_ids}
        placeholder_by_channel: dict[str, int] = {channel_id: 0 for channel_id in selected_ids}
        for programme in programmes:
            target = placeholder_by_channel if programme.is_placeholder else actual_by_channel
            target[programme.channel_id] = target.get(programme.channel_id, 0) + 1

        canonical_channels: list[CanonicalChannel] = []
        for channel_id in sorted(selected_ids):
            if canonical := registry.get(channel_id):
                canonical_channels.append(canonical)
        output_directory = Path(self.config.storage.local_directory) / profile_name
        output_directory.mkdir(parents=True, exist_ok=True)
        logo_files = LogoCache(
            self.config.logos,
            http,
            self.publisher,
            profile_name=profile_name,
            output_directory=output_directory,
        ).materialize(canonical_channels)
        xml_path = output_directory / "epg.xml"
        gzip_path = output_directory / "epg.xml.gz"
        emit_aliases = profile.emit_provider_aliases
        files = [*logo_files]
        if profile.emit_uncompressed_xml:
            write_xmltv(
                xml_path,
                canonical_channels,
                programmes,
                provider_channels=provider_channels,
                emit_provider_aliases=emit_aliases,
                max_description_chars=profile.max_description_chars,
            )
            files.append(xml_path)
        else:
            xml_path.unlink(missing_ok=True)
        output_bytes = write_xmltv(
            gzip_path,
            canonical_channels,
            programmes,
            provider_channels=provider_channels,
            emit_provider_aliases=emit_aliases,
            max_description_chars=profile.max_description_chars,
        )
        files.append(gzip_path)

        if profile.playlist.type in {PlaylistKind.M3U, PlaylistKind.XTREAM}:
            playlist_path = output_directory / "playlist.m3u"
            xmltv_url = self.publisher.public_url(profile_name, "epg.xml.gz")
            if (
                xmltv_url
                and self.config.storage.type == "local"
                and profile.delivery_token
                and profile.delivery_token.get_secret_value()
            ):
                from urllib.parse import quote

                xmltv_url += "?token=" + quote(profile.delivery_token.get_secret_value(), safe="")
            _atomic_text(playlist_path, render_m3u(provider_channels, xmltv_url=xmltv_url))
            files.append(playlist_path)

        finished = datetime.now(UTC)
        matched = sum(item.canonical_id is not None for item in provider_channels)
        live_count = sum(item.source_id.startswith("sentinel:") for item in programmes)
        real_programme_count = sum(actual_by_channel.values())
        placeholder_programme_count = sum(placeholder_by_channel.values())
        channels_with_real_epg = sum(count > 0 for count in actual_by_channel.values())
        placeholder_only = sum(
            actual_by_channel[channel_id] == 0 and placeholder_by_channel[channel_id] > 0
            for channel_id in selected_ids
        )
        empty_channels = sum(
            actual_by_channel[channel_id] == 0 and placeholder_by_channel[channel_id] == 0
            for channel_id in selected_ids
        )
        stats = BuildStats(
            profile=profile_name,
            started_at=started,
            finished_at=finished,
            mode=mode,
            source_count=source_count,
            playlist_channel_count=len(provider_channels),
            matched_channel_count=matched,
            unmatched_channel_count=unmatched,
            programme_count=len(programmes),
            real_programme_count=real_programme_count,
            placeholder_programme_count=placeholder_programme_count,
            channels_with_real_epg=channels_with_real_epg,
            placeholder_only_channel_count=placeholder_only,
            empty_channel_count=empty_channels,
            live_override_count=live_count,
            output_bytes=output_bytes,
            warnings=warnings,
        )
        status_path = output_directory / "status.json"
        _atomic_text(
            status_path, json.dumps(stats.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
        files.append(status_path)
        coverage_path = output_directory / "coverage.json"
        coverage_channels = []
        for channel_id in sorted(selected_ids):
            canonical = registry.get(channel_id)
            real_count = actual_by_channel[channel_id]
            placeholder_count = placeholder_by_channel[channel_id]
            status = "real" if real_count else "placeholder-only" if placeholder_count else "empty"
            coverage_channels.append(
                {
                    "id": channel_id,
                    "name": canonical.name if canonical else channel_id,
                    "status": status,
                    "real_programmes": real_count,
                    "placeholder_programmes": placeholder_count,
                }
            )
        _atomic_text(
            coverage_path,
            json.dumps(
                {
                    "generated_at": finished.isoformat(),
                    "profile": profile_name,
                    "summary": {
                        "channels": len(selected_ids),
                        "with_real_epg": channels_with_real_epg,
                        "placeholder_only": placeholder_only,
                        "empty": empty_channels,
                    },
                    "channels": coverage_channels,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        files.append(coverage_path)
        self.publisher.publish(profile_name, files)
        return stats

    def run(self, *, profiles: list[str] | None = None, mode: str = "full") -> list[BuildStats]:
        requested = profiles or list(self.config.profiles)
        missing = [name for name in requested if name not in self.config.profiles]
        if missing:
            raise ValueError(f"Nieznane profile: {', '.join(missing)}")
        registry = ChannelRegistry.load(self.config.registry_path)
        with HttpClient(self.config.http) as http:
            base_programmes, warnings, source_count = self._fetch_programmes(http, registry)
            if not source_count:
                raise SourceError("Żadne źródło XMLTV nie dostarczyło poprawnych danych")
            live_programmes: list[Programme] = []
            if self.config.sentinel.enabled:
                try:
                    sentinel = LiveSentinel(
                        self.config.sentinel, http, timezone=self.config.timezone
                    )
                    events = sentinel.collect()
                    warnings.extend(f"sentinel feed: {error}" for error in sentinel.errors)
                    live_programmes = events_to_programmes(events)
                except Exception as exc:
                    warnings.append(f"sentinel: {type(exc).__name__}: {exc}")
            results = [
                self._build_profile(
                    name,
                    self.config.profiles[name],
                    registry,
                    base_programmes,
                    live_programmes,
                    http,
                    source_count,
                    warnings,
                    mode,
                )
                for name in requested
            ]
        self.state.prune()
        return results
