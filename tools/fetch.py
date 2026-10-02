"""One shared way to GET JSON: an 8-second timeout, one retry on 429, and a 30-minute cache."""

import time

import requests

TIMEOUT_SECONDS = 8
CACHE_TTL_SECONDS = 30 * 60
RETRY_WAIT_SECONDS = 2

# (url + params) -> (time fetched, parsed JSON). In-memory, single process, like the sessions.
_cache: dict[str, tuple[float, dict]] = {}


def get_json(url: str, params: dict | None = None) -> dict:
    """GET a URL and return its JSON. Raises requests.RequestException on any failure."""
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    if key in _cache and time.time() - _cache[key][0] < CACHE_TTL_SECONDS:
        return _cache[key][1]

    response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
    if response.status_code == 429:
        # Arctic Shift rate-limits quickly. Wait once, try once more, then give up.
        time.sleep(RETRY_WAIT_SECONDS)
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()

    data = response.json()
    _cache[key] = (time.time(), data)
    return data
