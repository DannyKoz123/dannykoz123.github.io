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


def test_scan_config_analysis_and_report_render(tmp_path: Path):
    from tradegap import report

    cfg = load_config(ROOT / "config" / "scan.toml")
    TUR, CHN = 792, 156
    rows = []
    for y in cfg.years:
        rows += [
            row(TUR, 0, "M", y, 10_000_000, hs="854231"),
            row(TUR, RUS, "X", y, 1_000_000 * (y - 2018), hs="854231"),
            row(TUR, RUS, "X", y, 2_000_000, hs="848210"),
            row(CHN, TUR, "X", y, 9_000_000, hs="854231"),
            row(KGZ, RUS, "X", y, 500_000, hs="854239"),
        ]
    df = gaps.normalize(pd.DataFrame(rows))
    world = gaps.normalize(pd.DataFrame([row(CHN, TUR, "X", y, 9_000_000) for y in cfg.years]))

    surges = gaps.surge_table(df, cfg)
    mirror = gaps.world_mirror(df, world, cfg)
    ranking = gaps.scan_ranking(surges, mirror, cfg)
    tiers = gaps.tier_breakdown(df, cfg)

    top = ranking.iloc[0]
    assert top["intermediary"] == TUR
    # chips (y - 2018) M plus 2M of bearings: 2024-25 avg 8.5M vs 2022-23 avg 6.5M
    assert top["recent_vs_prior"] == pytest.approx(8.5 / 6.5)
    assert top["share_year"] == 2025
    assert set(tiers[tiers["intermediary"] == TUR]["tier"]) == {"1", "3.B"}

    tables = {
        "ranking": ranking, "surges": surges, "tiers": tiers, "world_mirror": mirror,
        "to_target": gaps.exports_to_target(world, cfg),
        "mirror_gaps": gaps.mirror_gaps(df, cfg), "coverage": gaps.reporting_coverage(df, cfg),
    }
    out = tmp_path / "report.html"
    report.write_report(tables, cfg, gaps.country_names(pd.DataFrame(rows)), out)
    html = out.read_text()
    assert "Scan ranking" in html and "Which kinds of goods" in html


def test_combine_keeps_one_copy_of_shared_flows():
    own = gaps.normalize(pd.DataFrame([row(KGZ, RUS, "X", 2023, 100), row(KGZ, 0, "M", 2023, 5)]))
    world = gaps.normalize(pd.DataFrame([row(KGZ, RUS, "X", 2023, 100), row(DEU, KGZ, "X", 2023, 7)]))
    out = gaps.combine(own, world)
    assert len(out) == 3
    assert out[(out["reporter"] == KGZ) & (out["partner"] == RUS)]["value"].item() == 100


def test_fetch_retries_rate_limit_and_timeout(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(comtrade, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(comtrade.time, "sleep", lambda s: None)
    replies = iter(["timeout", 429, 200])

    def handler(request: httpx.Request) -> httpx.Response:
        reply = next(replies)
        if reply == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if reply == 429:
            return httpx.Response(429, json={"message": "Try again in 1 seconds."})
        return httpx.Response(200, json={"data": [row(KGZ, DEU, "M", 2023, 1)], "error": ""})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    df = comtrade.fetch({"reporterCode": KGZ, "period": "2023"}, "key", client)
    assert len(df) == 1


def test_drill_monthly_series_and_report(tmp_path: Path):
    from tradegap import drill

    cfg = load_config(ROOT / "config" / "scan.toml")
    HKG, UZB = 344, 860

    def mrow(reporter, partner, flow, period, value, hs="854231", qty=None):
        return {**row(reporter, partner, flow, int(str(period)[:4]), value, hs=hs),
                "period": str(period), "qty": qty}

    raw = pd.DataFrame([
        mrow(HKG, UZB, "X", 202301, 10e6, qty=1e6),
        mrow(HKG, UZB, "X", 202301, 5e6, hs="847150", qty=100),
        mrow(HKG, RUS, "X", 202301, 3e6),
        mrow(UZB, 0, "M", 202301, 1.06e6),
        mrow(UZB, RUS, "X", 202301, 0.2e6),
    ])
    df = drill.normalize_monthly(raw)
    names = {**gaps.country_names(raw), **cfg.countries}
    tables = drill.write_drill_report(df, HKG, UZB, cfg, names, tmp_path / "r.html")

    jan = tables["monthly"].loc[pd.Timestamp("2023-01-01")]
    assert jan["HKG reports shipping to UZB"] == pytest.approx(15e6)
    assert jan["UZB records imports from world"] == pytest.approx(1.06e6)
    assert jan["UZB reports exports to Russia"] == pytest.approx(0.2e6)
    chips = tables["products"].set_index("hs").loc["854231"]
    assert chips["unit_value"] == pytest.approx(10)
    assert chips["via_imports_world"] == pytest.approx(1e6)
    assert "Shipments vs what arrives" in (tmp_path / "r.html").read_text()


def test_hk_reexports_parses_and_caches(tmp_path: Path, monkeypatch):
    from tradegap import hkstat

    monkeypatch.setattr(hkstat, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(hkstat.time, "sleep", lambda s: None)
    record = {"period": "2023", "ttype": 3, "co": "US", "coDescEN": "USA", "cc": "UZ",
              "ccDescEN": "UZBEKISTAN", "code": "854231", "figure": "78000"}
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"header": {"status": {"name": "Success", "code": 0}},
                                         "dataSet": [record]})

    real_client = httpx.Client
    monkeypatch.setattr(hkstat.httpx, "Client",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    df = hkstat.fetch_reexports(["UZ"], ["854231"], 2023, 2023)
    assert len(calls) == 2  # domestic exports + re-exports
    assert df["usd"].iloc[0] == pytest.approx(10_000_000)  # HK$78M at 7.8
    hkstat.fetch_reexports(["UZ"], ["854231"], 2023, 2023)
    assert len(calls) == 2  # second run served from cache
