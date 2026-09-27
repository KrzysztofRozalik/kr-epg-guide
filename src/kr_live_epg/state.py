from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


class StateStore:
    """Durable mappings and bounded API caches; one connection per operation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS channel_mapping (
                    profile TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    canonical_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    method TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (profile, provider_id)
                );
                CREATE TABLE IF NOT EXISTS cache (
                    namespace TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY (namespace, cache_key)
                );
                CREATE TABLE IF NOT EXISTS sentinel_seen (
                    fingerprint TEXT PRIMARY KEY,
                    seen_at TEXT NOT NULL
                );
                """
            )

    def get_mapping(self, profile: str, provider_id: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT canonical_id FROM channel_mapping WHERE profile=? AND provider_id=?",
                (profile, provider_id),
            ).fetchone()
        return str(row["canonical_id"]) if row else None

    def put_mapping(
        self,
        profile: str,
        provider_id: str,
        source_name: str,
        canonical_id: str,
        score: float,
        method: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO channel_mapping
                    (profile, provider_id, source_name, canonical_id, score, method, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile, provider_id) DO UPDATE SET
                    source_name=excluded.source_name,
                    canonical_id=excluded.canonical_id,
                    score=excluded.score,
                    method=excluded.method,
                    updated_at=excluded.updated_at
                """,
                (
                    profile,
                    provider_id,
                    source_name,
                    canonical_id,
                    score,
                    method,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def get_cache(self, namespace: str, key: str) -> Any | None:
        now = datetime.now(UTC).isoformat()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT value_json FROM cache
                WHERE namespace=? AND cache_key=? AND expires_at>?
                """,
                (namespace, key, now),
            ).fetchone()
        return json.loads(row["value_json"]) if row else None

    def put_cache(
        self,
        namespace: str,
        key: str,
        value: Any,
        *,
        ttl: timedelta,
    ) -> None:
        expires_at = datetime.now(UTC) + ttl
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO cache(namespace, cache_key, value_json, expires_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(namespace, cache_key) DO UPDATE SET
                    value_json=excluded.value_json,
                    expires_at=excluded.expires_at
                """,
                (namespace, key, json.dumps(value, ensure_ascii=False), expires_at.isoformat()),
            )

    def mark_seen(self, fingerprint: str) -> bool:
        """Return True only on the first observation of a sentinel item."""

        with self._connection() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO sentinel_seen(fingerprint, seen_at) VALUES (?, ?)",
                (fingerprint, datetime.now(UTC).isoformat()),
            )
        return cursor.rowcount == 1

    def prune(self) -> None:
        now = datetime.now(UTC)
        old = now - timedelta(days=30)
        with self._connection() as connection:
            connection.execute("DELETE FROM cache WHERE expires_at<=?", (now.isoformat(),))
            connection.execute("DELETE FROM sentinel_seen WHERE seen_at<?", (old.isoformat(),))
