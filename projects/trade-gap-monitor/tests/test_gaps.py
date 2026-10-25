import math
from pathlib import Path

import httpx
import pandas as pd
import pytest

from tradegap import comtrade, gaps
from tradegap.config import ROOT, load_config

CFG = load_config(ROOT / "config" / "demo1.toml")
DEU, KGZ, RUS = 276, 417, 643


def row(reporter, partner, flow, year, value, hs="854231", cif=None, fob=None):
    return {
        "reporterCode": reporter, "partnerCode": partner, "flowCode": flow, "cmdCode": hs,
        "refYear": year, "primaryValue": value, "cifvalue": cif, "fobvalue": fob,
    }


def test_normalize_prefers_cif_for_imports_and_fob_for_exports():
    raw = pd.DataFrame([
        row(KGZ, DEU, "M", 2023, 999, cif=106),
        row(DEU, KGZ, "X", 2023, 999, fob=100),
        row(KGZ, RUS, "X", 2023, 50),
        row(KGZ, RUS, "RX", 2023, 7),
    ])
    df = gaps.normalize(raw)
    values = dict(zip(df["flow"], df["value"]))
    assert len(df) == 3
    assert values["M"] == 106
    assert df[(df["flow"] == "X") & (df["reporter"] == DEU)]["value"].item() == 100


def test_mirror_gap_adjusts_cif_and_flags_missing_imports():
    raw = pd.DataFrame([
        row(DEU, KGZ, "X", 2023, 1_000),
        row(KGZ, DEU, "M", 2023, 530),
        row(KGZ, RUS, "X", 2023, 5_000),  # not a supplier->intermediary pair
    ])
    out = gaps.mirror_gaps(gaps.normalize(raw), CFG)
    assert len(out) == 1
    rec = out.iloc[0]
    assert rec["imp_fob"] == pytest.approx(500)
    assert rec["gap"] == pytest.approx(-500)
    assert rec["gap_ratio"] == pytest.approx(-0.5)
    assert rec["log_ratio"] == pytest.approx(math.log(0.5))


def test_reexport_surge_vs_baseline():
    raw = pd.DataFrame(
        [row(KGZ, RUS, "X", y, 10) for y in (2019, 2020, 2021)]
        + [row(KGZ, RUS, "X", 2023, 80), row(KGZ, DEU, "X", 2023, 1)]
    )
    out = gaps.reexports_to_target(gaps.normalize(raw), CFG)
    assert set(out["partner"]) == {RUS}
    assert out[out["year"] == 2023]["vs_baseline"].item() == pytest.approx(8)


def test_fetch_uses_preview_without_key_and_caches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(comtrade, "CACHE_DIR", tmp_path)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"data": [row(KGZ, DEU, "M", 2023, 1)], "error": ""})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    params = {"reporterCode": KGZ, "period": "2023"}
    first = comtrade.fetch(params, None, client)
    second = comtrade.fetch(params, None, client)

    assert len(calls) == 1
    assert calls[0].url.path.startswith("/public/v1/preview")
    assert "Ocp-Apim-Subscription-Key" not in calls[0].headers
    assert first.equals(second)
