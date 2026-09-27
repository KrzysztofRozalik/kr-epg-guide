from __future__ import annotations

from rapidfuzz import fuzz

from .models import CanonicalChannel, Channel, MatchResult
from .normalize import compact_signature, normalize_channel_name
from .registry import ChannelRegistry


class ChannelMatcher:
    def __init__(
        self,
        registry: ChannelRegistry,
        *,
        threshold: float = 92.0,
        margin: float = 6.0,
    ) -> None:
        self.registry = registry
        self.threshold = threshold
        self.margin = margin

    def match(self, channel: Channel) -> MatchResult:
        # Stable canonical IDs and exact upstream IDs win before name heuristics.
        for raw_id in [channel.tvg_id, channel.provider_id]:
            if raw_id and self.registry.get(raw_id):
                canonical = self.registry.get(raw_id)
                return MatchResult(
                    canonical_id=canonical.id,
                    canonical_name=canonical.name,
                    score=100,
                    method="exact-id",
                )

        names = [channel.name, *channel.aliases]
        exact_candidates: set[str] = set()
        for name in [*names, channel.tvg_id or "", channel.provider_id]:
            normalized = normalize_channel_name(name).normalized
            exact_candidates.update(self.registry.alias_index.get(normalized, set()))
            exact_candidates.update(self.registry.compact_index.get(compact_signature(name), set()))
        if len(exact_candidates) == 1:
            canonical = self.registry.get(next(iter(exact_candidates)))
            return MatchResult(
                canonical_id=canonical.id,
                canonical_name=canonical.name,
                score=100,
                method="exact-normalized-name",
            )
        if len(exact_candidates) > 1:
            return MatchResult(
                canonical_id=None,
                canonical_name=None,
                score=100,
                method="ambiguous-exact-name",
                ambiguous=True,
            )

        ranked: list[tuple[float, CanonicalChannel]] = []
        for canonical in self.registry.active():
            score = max(
                self._score(source_name, alias)
                for source_name in names
                for alias in [canonical.name, *canonical.aliases]
            )
            ranked.append((score, canonical))
        ranked.sort(key=lambda item: item[0], reverse=True)
        if not ranked:
            return MatchResult(canonical_id=None, canonical_name=None, method="empty-registry")

        best_score, best = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        ambiguous = best_score - runner_up < self.margin
        if best_score < self.threshold or ambiguous:
            return MatchResult(
                canonical_id=None,
                canonical_name=None,
                score=round(best_score, 2),
                runner_up_score=round(runner_up, 2),
                method="fuzzy-rejected",
                ambiguous=ambiguous,
            )
        return MatchResult(
            canonical_id=best.id,
            canonical_name=best.name,
            score=round(best_score, 2),
            runner_up_score=round(runner_up, 2),
            method="fuzzy-high-confidence",
        )

    @staticmethod
    def _score(left: str, right: str) -> float:
        source = normalize_channel_name(left)
        target = normalize_channel_name(right)
        if not source.normalized or not target.normalized:
            return 0.0

        # Channel numbers are identity, not decoration. Never map Sport 1 to Sport 2.
        if source.numbers != target.numbers and (source.numbers or target.numbers):
            return 0.0

        compact_left = source.normalized.replace(" ", "")
        compact_right = target.normalized.replace(" ", "")
        if compact_left == compact_right:
            return 100.0

        ratio = fuzz.WRatio(source.normalized, target.normalized)
        token_score = fuzz.token_set_ratio(source.normalized, target.normalized)
        score = 0.65 * ratio + 0.35 * token_score

        semantic_delta = set(source.semantic_tokens) ^ set(target.semantic_tokens)
        score -= min(30.0, 10.0 * len(semantic_delta))
        return max(0.0, score)
