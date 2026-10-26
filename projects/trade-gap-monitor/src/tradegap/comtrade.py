"""Minimal UN Comtrade client with an on-disk cache.

Russia stopped reporting detailed trade in 2022, so it is only ever used as a
partner here, never as a reporter.
"""

import hashlib
import itertools
import json
import os
import time
from pathlib import Path

import httpx
import pandas as pd

from .config import CACHE_DIR, Config

KEYED_URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"
PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
WORLD = 0
# Totals only: no second partner, customs regime or transport mode split.
TOTALS = {"partner2Code": WORLD, "customsCode": "C00", "motCode": 0, "includeDesc": "true"}
PAUSE_SECONDS = 2


def _cache_path(params: dict) -> Path:
    digest = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.parquet"


def fetch(params: dict, api_key: str | None, client: httpx.Client) -> pd.DataFrame:
    """Fetch one query, returning cached results when available."""
    path = _cache_path(params)
    if path.exists():
        return pd.read_parquet(path)

    url = KEYED_URL if api_key else PREVIEW_URL
    headers = {"Ocp-Apim-Subscription-Key": api_key} if api_key else {}
    for attempt in range(5):
        resp = client.get(url, params=params, headers=headers)
        if resp.status_code != 429:
            break
        time.sleep(2 ** (attempt + 1))
    if resp.is_error:
        raise RuntimeError(f"Comtrade HTTP {resp.status_code} for {params}: {resp.text[:300]}")

    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(f"Comtrade error for {params}: {payload['error']}")
    df = pd.DataFrame(payload.get("data") or [])
    if not api_key and len(df) >= 500:
        raise RuntimeError(f"Preview endpoint truncated at 500 rows for {params}; set an API key")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    time.sleep(PAUSE_SECONDS)
    return df


def _fetch_all(queries: list[dict]) -> pd.DataFrame:
    api_key = os.environ.get("COMTRADE_API_KEY") or None
    with httpx.Client(timeout=60) as client:
        frames = [fetch(q, api_key, client) for q in queries]
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_config(cfg: Config) -> pd.DataFrame:
    """Imports and exports reported by every supplier and intermediary.

    One call per reporter and year: the preview endpoint accepts a single
    period, and this keeps each response well under its 500-row cap.
    """
    reporters = {**cfg.suppliers, **cfg.intermediaries}
    all_codes = [*reporters.values(), *cfg.target.values()]
    queries = [
        {
            "reporterCode": code,
            "partnerCode": ",".join(str(c) for c in [*all_codes, WORLD] if c != code),
            "period": str(year),
            "cmdCode": ",".join(cfg.products),
            "flowCode": "M,X",
            **TOTALS,
        }
        for code, year in itertools.product(reporters.values(), cfg.years)
    ]
    return _fetch_all(queries)


def fetch_world_mirror(cfg: Config) -> pd.DataFrame:
    """Exports to each intermediary and the target, as reported by every country."""
    destinations = [*cfg.intermediaries.values(), *cfg.target.values()]
    queries = [
        {
            "partnerCode": dest,
            "period": str(year),
            "cmdCode": ",".join(cfg.products),
            "flowCode": "X",
            **TOTALS,
        }
        for dest, year in itertools.product(destinations, cfg.years)
    ]
    return _fetch_all(queries)
