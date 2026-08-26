"""Shared JSON GET with retries. Used for public catalogs and daily downloads."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

USER_AGENT = "stream-recoverability-public-catalog/1.0"


def with_usgs_key(url: str) -> str:
    key = os.environ.get("USGS_API_KEY", "").strip()
    if not key or "api_key=" in url:
        return url
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}{urllib.parse.urlencode({'api_key': key})}"


def get_json(
    url: str,
    *,
    timeout: int = 90,
    retries: int = 7,
    base_pause_s: float = 0.8,
) -> dict[str, Any]:
    last_error: Exception | None = None
    target = with_usgs_key(url)
    for attempt in range(retries):
        request = urllib.request.Request(
            target,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            last_error = RuntimeError(f"HTTP {error.code} for {url}")
            if error.code not in {429, 500, 502, 503, 504}:
                raise last_error from error
            retry_after = error.headers.get("Retry-After") if error.headers else None
            if retry_after and retry_after.isdigit():
                time.sleep(min(float(retry_after), 180.0))
            else:
                time.sleep(base_pause_s * (2**attempt))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = RuntimeError(f"{type(error).__name__} for {url}: {error}")
            time.sleep(base_pause_s * (2**attempt))
    raise last_error or RuntimeError(f"failed GET {url}")


__all__ = ["USER_AGENT", "get_json", "with_usgs_key"]
