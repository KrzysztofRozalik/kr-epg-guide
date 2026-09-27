from __future__ import annotations

import random
import time
from collections.abc import Mapping
from typing import Any

import httpx

from .config import HttpConfig
from .exceptions import FetchError


class HttpClient:
    """Small bounded HTTP client with retries and a hard response-size limit."""

    def __init__(self, config: HttpConfig) -> None:
        self.config = config
        self._client = httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds),
            follow_redirects=True,
            headers={"User-Agent": config.user_agent, "Accept-Encoding": "gzip, deflate"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        attempts = self.config.retries + 1
        for attempt in range(attempts):
            try:
                with self._client.stream(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                    data=data,
                ) as response:
                    response.raise_for_status()
                    limit = self.config.max_download_mb * 1024 * 1024
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > limit:
                            raise FetchError(
                                f"Odpowiedź z {response.url.host} przekracza limit "
                                f"{self.config.max_download_mb} MB"
                            )
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    return httpx.Response(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=content,
                        request=response.request,
                        extensions=response.extensions,
                    )
            except FetchError:
                raise
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                retry_after = 0.0
                if isinstance(exc, httpx.HTTPStatusError):
                    value = exc.response.headers.get("Retry-After", "")
                    retry_after = float(value) if value.isdigit() else 0.0
                    if exc.response.status_code < 500 and exc.response.status_code != 429:
                        break
                delay = max(retry_after, (2**attempt) + random.uniform(0.05, 0.35))
                time.sleep(min(delay, 15.0))
        host = httpx.URL(url).host or "nieznany-host"
        raise FetchError(f"Nie udało się pobrać danych z {host}: {last_error}") from last_error

    def get_bytes(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
    ) -> bytes:
        return self.request("GET", url, params=params, headers=headers, cookies=cookies).content

    def get_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        cookies: Mapping[str, str] | None = None,
    ) -> Any:
        response = self.request("GET", url, params=params, headers=headers, cookies=cookies)
        try:
            return response.json()
        except ValueError as exc:
            host = response.request.url.host or "nieznany-host"
            raise FetchError(f"Serwer {host} zwrócił nieprawidłowy JSON") from exc
