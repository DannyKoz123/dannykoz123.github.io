"""Minimal UN Comtrade client with an on-disk cache.

Russia stopped reporting detailed trade in 2022, so it is only ever used as a
partner here, never as a reporter.
"""

import hashlib
import itertools
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
KEYED_MAX_RECORDS = 100_000
# The keyed endpoint takes several periods per call; the preview takes one.
KEYED_MAX_PERIODS = 12
# Comtrade is slow per request (~1-2 min for large keyed queries), so a few run
# side by side. The keyless preview is rate limited harder; keep it serial.
KEYED_WORKERS = 3
TIMEOUT_SECONDS = 300
PREVIEW_MAX_RECORDS = 500


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
    limit = KEYED_MAX_RECORDS if api_key else PREVIEW_MAX_RECORDS
    request_params = {**params, "maxRecords": limit} if api_key else params
    for attempt in range(5):
        resp = client.get(url, params=request_params, headers=headers)
        if resp.status_code != 429:
            break
        wait = 2 ** (attempt + 1)
        print(f"  [rate limited by Comtrade, retrying in {wait}s]", end="", flush=True)
        time.sleep(wait)
    if resp.is_error:
        raise RuntimeError(f"Comtrade HTTP {resp.status_code} for {params}: {resp.text[:300]}")

    payload = resp.json()
    if payload.get("error"):
        raise RuntimeError(f"Comtrade error for {params}: {payload['error']}")
    df = pd.DataFrame(payload.get("data") or [])
    if len(df) >= limit:
        hint = "narrow the query" if api_key else "set COMTRADE_API_KEY in .env"
        raise RuntimeError(f"Response truncated at {limit} rows for {params}; {hint}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path)
    time.sleep(PAUSE_SECONDS)
    return df


def _fetch_all(queries: list[dict], label: str) -> pd.DataFrame:
    api_key = os.environ.get("COMTRADE_API_KEY") or None
    start = time.monotonic()
    done = 0

    def progress() -> None:
        print(f"\r{label}: {done}/{len(queries)} done "
              f"({time.monotonic() - start:.0f}s elapsed)   ", end="", flush=True)

    progress()
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client, \
            ThreadPoolExecutor(KEYED_WORKERS if api_key else 1) as pool:
        futures = [pool.submit(fetch, q, api_key, client) for q in queries]
        frames = []
        for future in as_completed(futures):
            frames.append(future.result())
            done += 1
            progress()
    print()
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _periods(cfg: Config) -> list[str]:
    """Period batches per call: all years with a key, one year without."""
    if not os.environ.get("COMTRADE_API_KEY"):
        return [str(y) for y in cfg.years]
    years = [str(y) for y in cfg.years]
    return [",".join(years[i:i + KEYED_MAX_PERIODS])
            for i in range(0, len(years), KEYED_MAX_PERIODS)]


def fetch_config(cfg: Config) -> pd.DataFrame:
    """Imports and exports reported by each intermediary, one call per
    intermediary and period batch. Suppliers' exports to intermediaries come
    from the world mirror instead."""
    reporters = {**cfg.suppliers, **cfg.intermediaries}
    all_codes = [*reporters.values(), *cfg.target.values()]
    queries = [
        {
            "reporterCode": code,
            "partnerCode": ",".join(str(c) for c in [*all_codes, WORLD] if c != code),
            "period": period,
            "cmdCode": ",".join(cfg.products),
            "flowCode": "M,X",
            **TOTALS,
        }
        for code, period in itertools.product(cfg.intermediaries.values(), _periods(cfg))
    ]
    return _fetch_all(queries, "intermediary flows")


def fetch_world_mirror(cfg: Config) -> pd.DataFrame:
    """Exports to each intermediary and the target, as reported by every country."""
    destinations = [*cfg.intermediaries.values(), *cfg.target.values()]
    queries = [
        {
            "partnerCode": dest,
            "period": period,
            "cmdCode": ",".join(cfg.products),
            "flowCode": "X",
            **TOTALS,
        }
        for dest, period in itertools.product(destinations, _periods(cfg))
    ]
    return _fetch_all(queries, "world mirror")
