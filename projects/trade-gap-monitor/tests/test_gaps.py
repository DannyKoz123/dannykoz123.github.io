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


def test_world_mirror_compares_totals_and_pass_through():
    bilateral = pd.DataFrame([
        row(KGZ, 0, "M", 2023, 1_060, hs="854231"),
        row(KGZ, 0, "M", 2023, 1_060, hs="854239"),
        row(KGZ, RUS, "X", 2023, 1_500),
    ])
    world = pd.DataFrame([
        row(156, KGZ, "X", 2023, 1_200),
        row(344, KGZ, "X", 2023, 300),
        row(97, KGZ, "X", 2023, 9_999),  # EU aggregate: must be ignored
    ])
    out = gaps.world_mirror(gaps.normalize(bilateral), gaps.normalize(world), CFG)
    rec = out[(out["intermediary"] == KGZ) & (out["year"] == 2023)].iloc[0]
    assert rec["imp_fob"] == pytest.approx(2_000)
    assert rec["partner_exports"] == pytest.approx(1_500)
    assert rec["partner_reporters"] == 2
    assert rec["gap"] == pytest.approx(500)
    assert rec["pass_through"] == pytest.approx(0.75)


def test_surge_table_baseline_zero_when_reported_nan_when_not():
    raw = pd.DataFrame(
        [row(KGZ, RUS, "X", y, 100_000) for y in (2019, 2020)]
        + [row(KGZ, DEU, "X", 2021, 1)]  # KGZ reported in 2021, but nothing to RUS
        + [row(KGZ, RUS, "X", 2023, 1_000_000)]
    )
    out = gaps.surge_table(gaps.normalize(raw), CFG).set_index("intermediary").loc[KGZ]
    assert out[2021] == 0
    assert pd.isna(out[2022])  # KGZ returned no rows at all in 2022
    assert out["baseline"] == pytest.approx(200_000 / 3)
    assert out["peak_year"] == 2023
    assert out["multiple"] == pytest.approx(15)
