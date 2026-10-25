"""Render the demo as a single static HTML page."""

from pathlib import Path

import pandas as pd
import plotly.express as px

from .config import Config


def _label(df: pd.DataFrame, cfg: Config, cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in cols:
        df[col] = df[col].map(cfg.countries).fillna(df[col].astype(str))
    df["product"] = df["hs"].map(cfg.products).fillna(df["hs"])
    return df


def write_report(gaps: pd.DataFrame, reexports: pd.DataFrame, anomalies: pd.DataFrame,
                 cfg: Config, path: Path) -> None:
    gaps = _label(gaps, cfg, ["exporter", "importer"])
    reexports = _label(reexports, cfg, ["reporter", "partner"])
    anomalies = _label(anomalies, cfg, ["exporter", "importer"])

    gap_by_year = gaps.groupby(["year", "exporter", "importer"], as_index=False)["gap"].sum()
    gap_by_year["route"] = gap_by_year["exporter"] + " → " + gap_by_year["importer"]
    fig_gap = px.bar(
        gap_by_year, x="year", y="gap", color="route", barmode="group",
        title="Mirror gap: importer-reported (FOB-adjusted) minus exporter-reported, USD",
    )

    fig_rx = px.line(
        reexports.groupby(["year", "reporter"], as_index=False)["value"].sum(),
        x="year", y="value", color="reporter", markers=True,
        title="Integrated-circuit exports to Russia reported by intermediaries, USD",
    )

    table = anomalies[["year", "exporter", "importer", "product", "exp_value", "imp_fob", "gap",
                       "gap_ratio"]].to_html(index=False, float_format=lambda v: f"{v:,.0f}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Trade Gap Monitor: Demo 1</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 16px}}
table{{border-collapse:collapse;font-size:.85rem}}td,th{{padding:4px 8px;border-bottom:1px solid #ddd}}</style>
</head><body>
<h1>Trade Gap Monitor: integrated circuits via Central Asia and the Caucasus</h1>
<p>Source: UN Comtrade. Gaps are leads, not evidence of wrongdoing.</p>
{fig_gap.to_html(full_html=False, include_plotlyjs="cdn")}
{fig_rx.to_html(full_html=False, include_plotlyjs=False)}
<h2>Largest post-2022 gaps</h2>
{table}
</body></html>""")
