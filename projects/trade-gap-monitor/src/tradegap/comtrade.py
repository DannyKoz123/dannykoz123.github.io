"""Minimal UN Comtrade client with an on-disk cache.

Russia stopped reporting detailed trade in 2022, so it is only ever used as a
partner here, never as a reporter.
"""

import hashlib
import itertools
import json
import os
import re
import time
from pathlib import Path

import httpx
import pandas as pd

from .config import CACHE_DIR, Config

# {freq} is A (annual) or M (monthly).
KEYED_URL = "https://comtradeapi.un.org/data/v1/get/C/{freq}/HS"
PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/{freq}/HS"
WORLD = 0
# Totals only: no second partner, customs regime or transport mode split.
TOTALS = {"partner2Code": WORLD, "customsCode": "C00", "motCode": 0, "includeDesc": "true"}
PAUSE_SECONDS = 2
KEYED_MAX_RECORDS = 100_000
PREVIEW_MAX_RECORDS = 500
# Comtrade answers large queries slowly and throttles concurrent ones, so
# requests run one at a time, one year each, and are retried when it balks.
TIMEOUT_SECONDS = 300
MAX_ATTEMPTS = 8


def _cache_path(params: dict, freq: str) -> Path:
    # Annual queries keep their original keys so existing caches stay valid.
    keyed = params if freq == "A" else {**params, "freqCode": freq}
    digest = hashlib.sha1(json.dumps(keyed, sort_keys=True).encode()).hexdigest()[:16]
    return CACHE_DIR / f"{digest}.parquet"


def fetch(params: dict, api_key: str | None, client: httpx.Client,
          freq: str = "A") -> pd.DataFrame:
    """Fetch one query, returning cached results when available."""
    path = _cache_path(params, freq)
    if path.exists():
        return pd.read_parquet(path)

    url = (KEYED_URL if api_key else PREVIEW_URL).format(freq=freq)
    headers = {"Ocp-Apim-Subscription-Key": api_key} if api_key else {}
    limit = KEYED_MAX_RECORDS if api_key else PREVIEW_MAX_RECORDS
    request_params = {**params, "maxRecords": limit} if api_key else params
    resp = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            resp = client.get(url, params=request_params, headers=headers)
        except httpx.TransportError as exc:  # timeouts, dropped connections
            wait, reason = 15 * attempt, type(exc).__name__
        else:
            if resp.status_code == 429:
                hinted = re.search(r"Try again in (\d+) second", resp.text)
                wait = int(hinted.group(1)) + 1 if hinted else 2 ** attempt
                reason = "rate limited"
            elif resp.status_code >= 500:
                wait, reason = 15 * attempt, f"HTTP {resp.status_code}"
            else:
                break
        if attempt == MAX_ATTEMPTS:
            raise RuntimeError(f"Comtrade kept failing ({reason}) for {params}")
        print(f"  [{reason}, retrying in {wait}s]", end="", flush=True)
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


def _fetch_all(queries: list[dict], label: str, freq: str = "A") -> pd.DataFrame:
    """Run queries one at a time. A query that still fails after retries is
    skipped and reported at the end; rerunning fetches only the missing ones."""
    api_key = os.environ.get("COMTRADE_API_KEY") or None
    start = time.monotonic()
    frames, failures = [], []
    with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
        for i, q in enumerate(queries, 1):
            print(f"\r{label}: fetching {i}/{len(queries)} "
                  f"({time.monotonic() - start:.0f}s elapsed)   ", end="", flush=True)
            try:
                frames.append(fetch(q, api_key, client, freq))
            except RuntimeError as exc:
                failures.append(str(exc))
    print(f"\r{label}: {len(queries) - len(failures)}/{len(queries)} done "
          f"in {time.monotonic() - start:.0f}s   ")
    if failures:
        raise RuntimeError(
            f"{len(failures)} {label} requests failed; rerun the same command to retry them "
            f"(finished ones are cached). First error: {failures[0]}"
        )
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _periods(cfg: Config) -> list[str]:
    """One year per call: multi-year keyed queries can exceed Comtrade's
    response time, and the preview endpoint accepts only one period."""
    return [str(y) for y in cfg.years]


def fetch_config(cfg: Config) -> pd.DataFrame:
    """Imports and exports reported by each intermediary, one call per
    intermediary and year. Suppliers' exports to intermediaries come
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


def fetch_drill(cfg: Config, origin: int, via: int, years: list[int]) -> pd.DataFrame:
    """Monthly flows for one origin -> via route: what the origin reports
    shipping to the via country, the other intermediaries and the target, and
    what the via country reports importing and exporting. One call per side
    and year (12 monthly periods)."""
    others = [c for c in [*cfg.intermediaries.values(), *cfg.target.values()] if c != via]
    sides = [
        {"reporterCode": origin, "partnerCode": ",".join(map(str, [via, *others])),
         "flowCode": "X"},
        {"reporterCode": via,
         "partnerCode": ",".join(map(str, [WORLD, origin, *others])), "flowCode": "M,X"},
    ]
    queries = [
        {**side, "period": ",".join(f"{y}{m:02d}" for m in range(1, 13)),
         "cmdCode": ",".join(cfg.products), **TOTALS}
        for side, y in itertools.product(sides, years)
    ]
    return _fetch_all(queries, "monthly drill", freq="M")
