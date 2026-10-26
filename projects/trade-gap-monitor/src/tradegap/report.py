"""Render a config's results as a single self-contained HTML page."""

import math
from pathlib import Path

import pandas as pd
import plotly.express as px
from plotly.offline import get_plotlyjs

from . import gaps as g
from .config import Config

TOP_SUPPLIERS = 8
# Tier rows below this in every post-baseline year are left out of the table.
MIN_TIER_USD = 1_000_000


def _usd_m(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v / 1e6:,.2f}"


def _pct(v) -> str:
    return "—" if pd.isna(v) else f"{v:+.0%}"


def _share(v) -> str:
    return "—" if pd.isna(v) else f"{v:.0%}"


def _chart(fig) -> str:
    fig.update_layout(margin={"l": 10, "r": 10, "t": 50, "b": 10}, legend_title_text="")
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


def _later_years(cfg: Config) -> list[int]:
    return [y for y in cfg.years if y not in cfg.baseline_years]


def _ranking_section(ranking: pd.DataFrame, cfg: Config, name) -> str:
    recent = cfg.years[-2:]
    prior = [y for y in _later_years(cfg) if y not in recent]
    view = pd.DataFrame({"country": ranking["intermediary"].map(name),
                         "baseline": ranking["baseline"].map(_usd_m)})
    for y in _later_years(cfg):
        view[y] = ranking[y].map(_usd_m)
    view[f"{recent[0]}–{recent[-1]} vs {prior[0]}–{prior[-1]}"] = [
        "—" if pd.isna(v) or math.isinf(v) else f"{v:,.1f}×" for v in ranking["recent_vs_prior"]
    ]
    view["latest share to Russia"] = [
        "—" if pd.isna(s) else f"{_share(s)} ({y:.0f})"
        for s, y in zip(ranking["share_to_target"], ranking["share_year"])
    ]
    return f"""
<h2>Scan ranking</h2>
<p>Each candidate's own reported exports to Russia of the selected goods, USD millions,
sorted by the larger of the last two years. The ratio column compares the average of the
last two years with the average of the post-invasion years before them: above 1× means
the route is still growing. “Latest share to Russia” is exports to Russia ÷ imports of
the same goods in the latest year with both. “—” means not reported.</p>
{view.to_html(index=False, classes="num")}"""


def _surge_section(surges: pd.DataFrame, cfg: Config, name) -> str:
    view = surges.copy()
    view["intermediary"] = view["intermediary"].map(name)
    for y in [*cfg.years, "baseline"]:
        view[y] = view[y].map(_usd_m)
    view["peak vs baseline"] = [
        f"{m:,.0f}×" if pd.notna(m) else ("from ~0" if pd.notna(p) and p > 0 else "—")
        for m, p in zip(surges["multiple"], surges["peak"])
    ]
    cols = ["intermediary", *cfg.years, "baseline", "peak vs baseline"]
    table = view[cols].to_html(index=False, escape=True, classes="num")

    long = surges.melt(id_vars="intermediary", value_vars=cfg.years, var_name="year",
                       value_name="usd").dropna()
    long["intermediary"] = long["intermediary"].map(name)
    long["USD millions"] = long["usd"] / 1e6
    fig = px.line(long, x="year", y="USD millions", color="intermediary", markers=True,
                  title="Exports to Russia, as reported by each intermediary")
    return f"""
<h2>1. Exports to Russia through the intermediaries</h2>
<p>USD millions. Baseline is the {cfg.baseline_years[0]}–{cfg.baseline_years[-1]} average.
Click a country in the legend to hide it.</p>
{table}
{_chart(fig)}"""


def _tier_section(tiers: pd.DataFrame, cfg: Config, name) -> str:
    later = _later_years(cfg)
    keep = tiers[tiers[later].max(axis=1) >= MIN_TIER_USD].copy()
    if keep.empty:
        return ""
    keep = keep.sort_values(["intermediary", "tier"])
    view = pd.DataFrame({"country": keep["intermediary"].map(name), "tier": keep["tier"]})
    for y in later:
        view[y] = keep[y].map(_usd_m)
    return f"""
<h2>1b. Which kinds of goods</h2>
<p>Exports to Russia by list tier, USD millions, for country–tier pairs above
${MIN_TIER_USD / 1e6:.0f}M in any post-baseline year. Tier 1–2: integrated circuits and core
electronics; 3.A: other electronics; 3.B: bearings, optics, aircraft and UAV parts;
4.A: production and test equipment; 4.B: CNC machine tools.</p>
{view.to_html(index=False, classes="num")}"""


def _world_section(world: pd.DataFrame, name) -> str:
    view = world.copy()
    view["intermediary"] = view["intermediary"].map(name)
    long = view.melt(id_vars=["intermediary", "year"], value_vars=["imp_fob", "partner_exports"],
                     var_name="series", value_name="usd").dropna()
    long["series"] = long["series"].map({
        "imp_fob": "Intermediary-reported imports (FOB-adjusted)",
        "partner_exports": "All partners' reported exports to it",
    })
    long["USD millions"] = long["usd"] / 1e6
    n = view["intermediary"].nunique()
    fig = px.bar(long, x="year", y="USD millions", color="series", barmode="group",
                 facet_col="intermediary", facet_col_wrap=4, facet_row_spacing=0.08,
                 title="World-total mirror: goods arriving vs goods sent",
                 height=260 * math.ceil(n / 4) + 120)
    fig.update_yaxes(matches=None, showticklabels=True, title_text="")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]))
    fig.update_layout(legend={"orientation": "h", "y": -0.08})

    table = pd.DataFrame({
        "intermediary": view["intermediary"],
        "year": view["year"],
        "imports (FOB)": view["imp_fob"].map(_usd_m),
        "partners' exports": view["partner_exports"].map(_usd_m),
        "reporting partners": view["partner_reporters"].map(
            lambda v: "—" if pd.isna(v) else f"{v:.0f}"),
        "gap": view["gap_ratio"].map(_pct),
        "to Russia": view["to_target"].map(_usd_m),
        "share passed to Russia": view["pass_through"].map(_share),
    }).to_html(index=False, classes="num")
    return f"""
<h2>2. World-total mirror</h2>
<p>Each intermediary's reported imports of the selected goods from the world, against the
sum of what every reporting country says it exported there, in USD millions (each panel
has its own scale). Comparing totals cancels the country-of-origin mismatch that distorts
bilateral pairs. A positive gap means more arrives than partners report sending, which
non-reporting partners can also cause. “Share passed to Russia” is exports to Russia ÷
imports.</p>
{_chart(fig)}
<details><summary>Table</summary>{table}</details>"""


def _target_section(to_target: pd.DataFrame, name) -> str:
    df = to_target.copy()
    totals = df.groupby("reporter")["value"].sum().sort_values(ascending=False)
    top = set(totals.index[:TOP_SUPPLIERS])
    df["country"] = [name(r) if r in top else "Other" for r in df["reporter"]]
    df = df.groupby(["year", "country"], as_index=False)["value"].sum()
    df["USD millions"] = df["value"] / 1e6
    order = [name(r) for r in totals.index[:TOP_SUPPLIERS]] + ["Other"]
    fig = px.bar(df, x="year", y="USD millions", color="country",
                 category_orders={"country": order},
                 title="Reported exports of the selected goods to Russia, by exporting country")
    return f"""
<h2>3. Who reports shipping these goods to Russia</h2>
<p>Russia no longer publishes detailed imports, so this is the partner side only.
Goods routed through countries that do not report are missing.</p>
{_chart(fig)}"""


def _bilateral_section(mirror: pd.DataFrame, cfg: Config, name) -> str:
    top = g.top_anomalies(mirror).copy()
    table = pd.DataFrame({
        "year": top["year"],
        "exporter": top["exporter"].map(name),
        "importer": top["importer"].map(name),
        "product": top["hs"].map(cfg.products).fillna(top["hs"]),
        "exporter says": top["exp_value"].map(_usd_m),
        "importer says (FOB)": top["imp_fob"].map(_usd_m),
        "gap": top["gap"].map(_usd_m),
        "gap %": top["gap_ratio"].map(_pct),
    }).to_html(index=False, classes="num")
    return f"""
<h2>4. Bilateral gaps (read with care)</h2>
<p>Largest supplier → intermediary gaps since 2022, USD millions. Importers record the
country where goods were made; exporters record where they shipped them. A chip made in
China but shipped from Hong Kong shows up as “from China” with no matching Chinese export,
so large positive gaps on producer countries are expected and are not, on their own, a signal.</p>
{table}"""


def _coverage_section(coverage: pd.DataFrame, name) -> str:
    view = coverage.map(lambda v: "✓" if v else "—")
    view.index = [name(c) for c in view.index]
    view.index.name = "reporter"
    view.columns.name = None
    return f"""
<h2>5. Data coverage</h2>
<p>Whether each configured country returned any data for the selected products and year.
Recent years are often incomplete; treat the latest year as provisional.</p>
{view.reset_index().to_html(index=False, classes="num")}"""


def write_report(tables: dict[str, pd.DataFrame], cfg: Config, names: dict[int, str],
                 path: Path) -> None:
    def name(code) -> str:
        return names.get(int(code), str(code))

    sections = [
        _ranking_section(tables["ranking"], cfg, name) if cfg.tiers else "",
        _surge_section(tables["surges"], cfg, name),
        _tier_section(tables["tiers"], cfg, name) if cfg.tiers else "",
        _world_section(tables["world_mirror"], name),
        _target_section(tables["to_target"], name),
        _bilateral_section(tables["mirror_gaps"], cfg, name),
        _coverage_section(tables["coverage"], name),
    ]
    body = "".join(sections)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Trade Gap Monitor</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script>{get_plotlyjs()}</script>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;color:#1d1d1f;background:#fff;
max-width:1040px;margin:2rem auto;padding:0 16px;line-height:1.5}}
h1{{font-size:1.6rem;margin-bottom:.2rem}} h2{{margin-top:2.5rem;font-size:1.2rem}}
p{{color:#444;max-width:75ch}} .lede{{color:#666}} summary{{cursor:pointer;color:#444}}
.tbl{{overflow-x:auto}} table{{border-collapse:collapse;font-size:.85rem;margin:1rem 0}}
td,th{{padding:5px 10px;border-bottom:1px solid #e5e5e5;white-space:nowrap}}
th{{text-align:left;background:#f6f6f6}} table.num td{{text-align:right}}
table.num td:first-child{{text-align:left}}
</style></head><body>
<h1>{cfg.title}</h1>
<p class="lede">Source: UN Comtrade, {len(cfg.products)} HS codes, {cfg.years[0]}–{cfg.years[-1]}.
Gaps and surges are leads, not evidence of wrongdoing.</p>
{body.replace("<table", '<div class="tbl"><table').replace("</table>", "</table></div>")}
</body></html>""")
