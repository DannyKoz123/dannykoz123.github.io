"""Hong Kong Census and Statistics Department trade API (Trade-IDDS).

Hong Kong records re-exports separately from domestic exports and keeps the
country of origin, which Comtrade does not expose. Spec:
https://tradeidds.censtatd.gov.hk/PageID/ApiSpec
"""

import hashlib
import json
import time

import httpx
import pandas as pd

from .config import CACHE_DIR

API_URL = "https://tradeidds.censtatd.gov.hk/api/get"
TRADE_TYPES = {2: "domestic exports", 3: "re-exports"}
REEXPORTS = 3
HKD_PER_USD = 7.8  # linked exchange rate band 7.75-7.85
MAX_CODES = 20  # API limit per request
STATUS_USAGE_LIMIT = 2


class UsageLimit(RuntimeError):
    pass


def fetch(params: dict, client: httpx.Client) -> list[dict]:
    """One API call, cached on disk. Raises UsageLimit when Hong Kong throttles."""
    digest = hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
    path = CACHE_DIR / f"hk_{digest}.json"
    if path.exists():
        return json.loads(path.read_text())

    resp = client.get(API_URL, params={"lang": "EN", **params})
    resp.raise_for_status()
    payload = resp.json()
    status = payload["header"]["status"]
    if status["code"] == STATUS_USAGE_LIMIT:
        raise UsageLimit("Hong Kong's API usage limit reached; try again later")
    if status["code"] != 0 and "No record found" in (status.get("message") or []):
        status = {"code": 0}  # an empty result, reported as a failure
        payload["dataSet"] = []
    if status["code"] != 0:
        raise RuntimeError(f"Hong Kong API {status['name']}: {status.get('message')} for {params}")
    records = payload.get("dataSet", [])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records))
    return records


def _query(client: httpx.Client, label: str, params: dict) -> list[dict]:
    print(f"Hong Kong {label}...")
    records = fetch(params, client)
    time.sleep(2)
    return records


def fetch_reexports(destinations: list[str], codes: list[str], start: int, end: int) -> pd.DataFrame:
    """Hong Kong exports to each destination in two views, USD:

    - by_origin: re-exports of all goods by country of origin
    - by_product: domestic exports and re-exports by HS-6 code

    The API does not combine origin with commodity for re-exports, and has no
    origin for domestic exports, so the two cannot be crossed.
    """
    period = {"sv": "VCy", "freq": "A", "period": f"{start},{end}"}
    dest = {"ccclass": "C", "cc": ",".join(destinations)}
    rows = []
    # The site sets a session cookie and redirects before answering.
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        for r in _query(client, "re-exports by origin",
                        {**period, **dest, "ttype": REEXPORTS, "coclass": "C", "co": "ALL"}):
            rows.append({**r, "view": "by_origin"})
        for ttype, label in TRADE_TYPES.items():
            for i in range(0, len(codes), MAX_CODES):
                params = {**period, **dest, "ttype": ttype, "codeclass": "HKHS6",
                          "code": ",".join(codes[i:i + MAX_CODES])}
                for r in _query(client, f"{label} by product, codes {i + 1}-{i + MAX_CODES}",
                                params):
                    rows.append({**r, "view": "by_product"})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["usd"] = pd.to_numeric(df["figure"], errors="coerce") * 1000 / HKD_PER_USD
    df["trade_type"] = df["ttype"].astype(int).map(TRADE_TYPES)
    return df.rename(columns={"coDescEN": "origin", "ccDescEN": "destination",
                              "codeDescEN": "product", "period": "year"})
