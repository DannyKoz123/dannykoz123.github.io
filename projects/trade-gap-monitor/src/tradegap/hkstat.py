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
    if status["code"] != 0:
        raise RuntimeError(f"Hong Kong API {status['name']}: {status.get('message')} for {params}")
    records = payload.get("dataSet", [])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records))
    return records


def fetch_reexports(destinations: list[str], codes: list[str], start: int, end: int) -> pd.DataFrame:
    """Annual domestic exports and re-exports to each destination, by origin and
    HS-6 code. Values are converted from HK$ '000 to USD."""
    rows = []
    # The site sets a session cookie and redirects before answering.
    with httpx.Client(timeout=180, follow_redirects=True) as client:
        for ttype, label in TRADE_TYPES.items():
            for i in range(0, len(codes), MAX_CODES):
                params = {
                    "sv": "VCy", "freq": "A", "period": f"{start},{end}", "ttype": ttype,
                    "ccclass": "C", "cc": ",".join(destinations),
                    "codeclass": "HKHS6", "code": ",".join(codes[i:i + MAX_CODES]),
                }
                # Origin only applies to re-exports; domestic exports are Hong Kong-made.
                if ttype == REEXPORTS:
                    params.update({"coclass": "C", "co": "ALL"})
                print(f"Hong Kong {label}, codes {i + 1}-{i + MAX_CODES}...")
                rows += fetch(params, client)
                time.sleep(2)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["usd"] = pd.to_numeric(df["figure"], errors="coerce") * 1000 / HKD_PER_USD
    df["trade_type"] = df["ttype"].astype(int).map(TRADE_TYPES)
    if "coDescEN" not in df:
        df["coDescEN"] = None
    df["coDescEN"] = df["coDescEN"].fillna("HONG KONG (domestic exports)")
    return df.rename(columns={"coDescEN": "origin", "ccDescEN": "destination",
                              "period": "year"})
