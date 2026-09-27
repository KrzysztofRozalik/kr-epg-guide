from __future__ import annotations

import re
from datetime import timedelta

from .config import TmdbConfig
from .http import HttpClient
from .models import Credits, Programme
from .normalize import normalize_title
from .state import StateStore

_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")


class TmdbEnricher:
    def __init__(self, config: TmdbConfig, http: HttpClient, state: StateStore) -> None:
        self.config = config
        self.http = http
        self.state = state
        self.requests = 0

    def _media_type(self, programme: Programme) -> str | None:
        categories = " ".join(programme.categories).casefold()
        duration = (programme.stop - programme.start).total_seconds() / 60
        if duration >= self.config.min_duration_minutes and any(
            term in categories for term in ("film", "movie", "kino")
        ):
            return "movie"
        if any(term in categories for term in ("wiadomo", "news", "pogoda")):
            return None
        if programme.episode_num or any(
            term in categories
            for term in (
                "serial",
                "series",
                "reality",
                "program",
                "magazyn",
                "dokument",
                "motoryz",
                "lifestyle",
                "talk show",
                "teleturniej",
            )
        ):
            return "tv"
        return None

    def _get(self, path: str, params: dict[str, object]) -> object:
        if not self.config.api_token:
            return {}
        self.requests += 1
        return self.http.get_json(
            f"https://api.themoviedb.org/3{path}",
            params=params,
            headers={
                "Authorization": f"Bearer {self.config.api_token.get_secret_value()}",
                "Accept": "application/json",
            },
        )

    def _lookup(self, title: str, year: int | None, media_type: str) -> dict[str, object] | None:
        clean_title = _YEAR_RE.sub("", title).strip(" -\u2013\u2014()[]")
        key = f"{media_type}|{normalize_title(clean_title)}|{year or ''}|{self.config.language}"
        cache_namespace = f"tmdb-{media_type}"
        cached = self.state.get_cache(cache_namespace, key)
        if isinstance(cached, dict):
            return cached
        if self.requests >= self.config.max_requests_per_run:
            return None
        params: dict[str, object] = {
            "query": clean_title,
            "language": self.config.language,
            "region": self.config.region,
            "include_adult": "false",
        }
        if year:
            params["year" if media_type == "movie" else "first_air_date_year"] = year
        search = self._get(f"/search/{media_type}", params)
        results = search.get("results", []) if isinstance(search, dict) else []
        if not results:
            return None
        normalized = normalize_title(clean_title)

        def result_title(item: dict[str, object]) -> str:
            return str(item.get("title") or item.get("name") or "")

        ranked = sorted(
            (item for item in results if isinstance(item, dict)),
            key=lambda item: (
                normalize_title(result_title(item)) == normalized,
                float(item.get("popularity") or 0),
            ),
            reverse=True,
        )
        best = ranked[0]
        if normalize_title(result_title(best)) != normalized:
            return None
        details = self._get(
            f"/{media_type}/{best['id']}",
            {"language": self.config.language, "append_to_response": "credits"},
        )
        if not isinstance(details, dict):
            return None
        self.state.put_cache(
            cache_namespace,
            key,
            details,
            ttl=timedelta(days=self.config.cache_days),
        )
        return details

    def _apply(
        self, programme: Programme, data: dict[str, object], media_type: str = "movie"
    ) -> Programme:
        credits_data = data.get("credits") if isinstance(data.get("credits"), dict) else {}
        cast = credits_data.get("cast", []) if isinstance(credits_data, dict) else []
        crew = credits_data.get("crew", []) if isinstance(credits_data, dict) else []
        actors = [
            str(item.get("name"))
            for item in cast[: self.config.max_cast]
            if isinstance(item, dict) and item.get("name")
        ]
        directors = [
            str(item.get("name"))
            for item in crew
            if isinstance(item, dict) and item.get("job") == "Director" and item.get("name")
        ]
        writers = [
            str(item.get("name"))
            for item in crew
            if isinstance(item, dict)
            and item.get("job") in {"Writer", "Screenplay"}
            and item.get("name")
        ]
        producers = [
            str(item.get("name"))
            for item in crew
            if isinstance(item, dict)
            and item.get("job") in {"Producer", "Executive Producer"}
            and item.get("name")
        ]
        creators = [
            str(item.get("name"))
            for item in data.get("created_by", [])
            if isinstance(item, dict) and item.get("name")
        ]
        writers = list(dict.fromkeys([*writers, *creators]))
        release = str(data.get("release_date") or data.get("first_air_date") or "")
        year = int(release[:4]) if release[:4].isdigit() else None
        raw_countries = data.get("production_countries", [])
        countries = (
            [
                str(item.get("name") or item.get("iso_3166_1"))
                for item in raw_countries
                if isinstance(item, dict) and (item.get("name") or item.get("iso_3166_1"))
            ]
            if isinstance(raw_countries, list)
            else []
        )
        if not countries and isinstance(data.get("origin_country"), list):
            countries = [str(item) for item in data["origin_country"] if item]
        companies = [
            str(item.get("name"))
            for item in data.get("production_companies", [])
            if isinstance(item, dict) and item.get("name")
        ]
        genres = [
            str(item.get("name"))
            for item in data.get("genres", [])
            if isinstance(item, dict) and item.get("name")
        ]
        rating = None
        if data.get("vote_average"):
            rating = (
                f"{float(data['vote_average']):.1f}/10 ({int(data.get('vote_count') or 0)} TMDb)"
            )
        poster = str(data.get("poster_path") or "")
        raw_runtimes = data.get("episode_run_time", [])
        runtime = data.get("runtime")
        if not runtime and isinstance(raw_runtimes, list) and raw_runtimes:
            runtime = raw_runtimes[0]
        merged_credits = programme.credits.merge(
            Credits(
                actors=actors,
                directors=directors,
                writers=writers,
                producers=producers,
            )
        )
        effective_year = programme.year or year
        effective_countries = programme.country or countries
        effective_companies = programme.production_companies or companies
        effective_categories = list(dict.fromkeys([*programme.categories, *genres]))
        description = programme.description or str(data.get("overview") or "") or None
        update = {
            "original_title": programme.original_title
            or str(data.get("original_title") or data.get("original_name") or "")
            or None,
            "description": description,
            "credits": merged_credits,
            "year": effective_year,
            "country": effective_countries,
            "production_companies": effective_companies,
            "categories": effective_categories,
            "duration_minutes": programme.duration_minutes or (int(runtime) if runtime else None),
            "original_language": programme.original_language
            or str(data.get("original_language") or "")
            or None,
            "star_rating": programme.star_rating or rating,
            "icon": programme.icon
            or (f"https://image.tmdb.org/t/p/w500{poster}" if poster else None),
            "url": programme.url or f"https://www.themoviedb.org/{media_type}/{data.get('id')}",
        }
        for field, value in update.items():
            setattr(programme, field, value)
        return programme

    def enrich(self, programmes: list[Programme]) -> list[Programme]:
        if not self.config.enabled:
            return programmes
        metadata: dict[tuple[str, int | None, str], dict[str, object] | None] = {}
        result: list[Programme] = []
        for programme in programmes:
            media_type = self._media_type(programme)
            if media_type is None:
                result.append(programme)
                continue
            key = (normalize_title(programme.title), programme.year, media_type)
            if key not in metadata:
                metadata[key] = self._lookup(programme.title, programme.year, media_type)
            data = metadata[key]
            result.append(self._apply(programme, data, media_type) if data else programme)
        return result
