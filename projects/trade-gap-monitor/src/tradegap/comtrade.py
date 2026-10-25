"""Minimal UN Comtrade client with an on-disk cache.

Russia stopped reporting detailed trade in 2022, so it is only ever used as a
partner here, never as a reporter.
"""

import hashlib
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
    for attempt in range(4):
        resp = client.get(url, params=params, headers=headers)
        if resp.status_code != 429:
            break
        time.sleep(2 ** (attempt + 1))
    resp.raise_for_status()

    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(f"Comtrade error for {params}: {payload['error']}")
    df = pd.DataFrame(payload.get("data") or [])
    if not api_key and len(df) >= 500:
        raise RuntimeError(f"Preview endpoint truncated at 500 rows for {params}; set an API key")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    return df


def fetch_config(cfg: Config) -> pd.DataFrame:
    """Pull imports and exports for every non-target country in the config.

    One call per reporter keeps each response well under the 500-row preview cap.
    """
    api_key = os.environ.get("COMTRADE_API_KEY") or None
    reporters = {**cfg.suppliers, **cfg.intermediaries}
    all_codes = [*reporters.values(), *cfg.target.values()]
    frames = []
    with httpx.Client(timeout=60) as client:
        for code in reporters.values():
            partners = [c for c in all_codes if c != code] + [WORLD]
            params = {
                "reporterCode": code,
                "partnerCode": ",".join(map(str, partners)),
                "period": ",".join(map(str, cfg.years)),
                "cmdCode": ",".join(cfg.products),
                "flowCode": "M,X",
                # Totals only: no second partner, customs regime or transport mode split.
                "partner2Code": WORLD,
                "customsCode": "C00",
                "motCode": 0,
            }
            frames.append(fetch(params, api_key, client))
            time.sleep(1)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
