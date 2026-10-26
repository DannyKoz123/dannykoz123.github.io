"""Monthly drill-down on one origin -> via route (e.g. Hong Kong -> Uzbekistan)."""

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px

from .config import Config
from .report import _chart, _usd_m, write_page

WORLD = 0
# Dates drawn on the monthly charts.
EVENTS = {
    "2022-02-24": "Invasion",
    "2023-12-22": "US EO 14114 (secondary sanctions on banks)",
}


def normalize_monthly(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per reporter/partner/flow/product/month, with value and quantity."""
    if raw.empty:
        return pd.DataFrame(columns=["reporter", "partner", "flow", "hs", "month", "value", "qty"])
    df = raw[raw["flowCode"].isin(["M", "X"])].copy()
    cif = pd.to_numeric(df.get("cifvalue"), errors="coerce")
    fob = pd.to_numeric(df.get("fobvalue"), errors="coerce")
    preferred = pd.Series(np.where(df["flowCode"] == "M", cif, fob), index=df.index)
    df["value"] = pd.to_numeric(preferred, errors="coerce").fillna(df["primaryValue"]).astype(float)
    df["qty"] = pd.to_numeric(df.get("qty"), errors="coerce")
    df["month"] = pd.to_datetime(df["period"].astype(str), format="%Y%m")
    out = df.rename(columns={"reporterCode": "reporter", "partnerCode": "partner",
                             "flowCode": "flow", "cmdCode": "hs"})
    out["hs"] = out["hs"].astype(str)
    keys = ["reporter", "partner", "flow", "hs", "month"]
    return out.groupby(keys, as_index=False)[["value", "qty"]].sum(min_count=1)


def monthly_series(df: pd.DataFrame, origin: int, via: int, cfg: Config,
                   name) -> pd.DataFrame:
    """Wide monthly table (USD) of the flows that tell the explanations apart."""
    target = set(cfg.target.values())
    series = {
        f"{name(origin)} reports shipping to {name(via)}":
            (df["reporter"] == origin) & (df["partner"] == via) & (df["flow"] == "X"),
        f"{name(via)} records imports from world":
            (df["reporter"] == via) & (df["partner"] == WORLD) & (df["flow"] == "M"),
        f"{name(via)} records imports from {name(origin)}":
            (df["reporter"] == via) & (df["partner"] == origin) & (df["flow"] == "M"),
        f"{name(via)} reports exports to Russia":
            (df["reporter"] == via) & df["partner"].isin(target) & (df["flow"] == "X"),
        f"{name(origin)} reports shipping to Russia":
            (df["reporter"] == origin) & df["partner"].isin(target) & (df["flow"] == "X"),
    }
    cols = {label: df[mask].groupby("month")["value"].sum() for label, mask in series.items()}
    return pd.DataFrame(cols).sort_index()


def origin_by_partner(df: pd.DataFrame, origin: int, name) -> pd.DataFrame:
    flows = df[(df["reporter"] == origin) & (df["flow"] == "X")]
    out = flows.groupby(["month", "partner"])["value"].sum().unstack()
    out.columns = [name(c) for c in out.columns]
    return out.sort_index()


def products_by_year(df: pd.DataFrame, origin: int, via: int, cfg: Config) -> pd.DataFrame:
    """Origin -> via shipments by product and year, with what the via country
    records importing of the same product from anywhere."""
    df = df.assign(year=df["month"].dt.year)
    sent = df[(df["reporter"] == origin) & (df["partner"] == via) & (df["flow"] == "X")]
    got = df[(df["reporter"] == via) & (df["partner"] == WORLD) & (df["flow"] == "M")]
    s = sent.groupby(["hs", "year"])[["value", "qty"]].sum(min_count=1)
    g = got.groupby(["hs", "year"])["value"].sum().rename("via_imports_world") / cfg.cif_fob_factor
    out = s.join(g, how="left").reset_index()
    out["unit_value"] = out["value"] / out["qty"]
    out["name"] = out["hs"].map(cfg.products)
    out["tier"] = out["hs"].map(cfg.product_tier)
    return out


def _with_events(fig):
    for date, label in EVENTS.items():
        fig.add_shape(type="line", x0=date, x1=date, y0=0, y1=1, yref="paper",
                      line={"dash": "dot", "color": "#888", "width": 1})
        fig.add_annotation(x=date, y=1, yref="paper", text=label, showarrow=False,
                           xanchor="left", yanchor="bottom", font={"size": 10, "color": "#666"})
    return fig


def _line(table: pd.DataFrame, title: str):
    long = (table / 1e6).reset_index().melt(id_vars="month", var_name="series",
                                            value_name="USD millions").dropna()
    fig = px.line(long, x="month", y="USD millions", color="series", markers=True, title=title)
    fig.update_layout(legend={"orientation": "h", "y": -0.2}, xaxis_title="")
    return _with_events(fig)


def write_drill_report(df: pd.DataFrame, origin: int, via: int, cfg: Config,
                       names: dict[int, str], path: Path) -> dict[str, pd.DataFrame]:
    def name(code) -> str:
        return names.get(int(code), str(code))

    series = monthly_series(df, origin, via, cfg, name)
    by_partner = origin_by_partner(df, origin, name)
    products = products_by_year(df, origin, via, cfg)

    top = (products.groupby("hs")["value"].sum().sort_values(ascending=False).head(10).index)
    view = products[products["hs"].isin(top)].sort_values(["hs", "year"])
    table = pd.DataFrame({
        "hs": view["hs"], "product": view["name"], "tier": view["tier"], "year": view["year"],
        f"{name(origin)} → {name(via)}": view["value"].map(_usd_m),
        "units": view["qty"].map(lambda v: "—" if pd.isna(v) else f"{v:,.0f}"),
        "USD / unit": view["unit_value"].map(lambda v: "—" if pd.isna(v) or np.isinf(v)
                                              else f"{v:,.2f}"),
        f"{name(via)} imports from world (FOB)": view["via_imports_world"].map(_usd_m),
    }).to_html(index=False, classes="num")

    has_via = series.filter(like=f"{name(via)} records").notna().any().any()
    body = f"""
<h2>1. Shipments vs what arrives</h2>
<p>Monthly, USD millions, all selected goods. If {name(via)} recorded what {name(origin)}
says it sent, the first two lines would track each other.{"" if has_via else
f" <strong>{name(via)} returned no monthly data</strong>, so only the {name(origin)} side "
"is shown; compare with the annual figures in the scan report."}</p>
{_chart(_line(series, f"{name(origin)} → {name(via)}: reported shipments and recorded arrivals"))}
<h2>2. Where else {name(origin)} was shipping</h2>
<p>{name(origin)}-reported exports of the selected goods by destination, monthly, USD millions.
A rise to {name(via)} that mirrors a fall to Russia would suggest substitution.</p>
{_chart(_line(by_partner, f"{name(origin)}-reported exports by destination"))}
<h2>3. Which goods</h2>
<p>The ten largest products on the route, by year. Unit values far from those on
{name(origin)}'s other routes suggest different goods, or misdeclared quantities.</p>
{table}"""
    write_page(path, f"Drill-down: {name(origin)} → {name(via)}",
               "Source: UN Comtrade monthly data. A lead, not evidence of wrongdoing.", body)
    return {"monthly": series, "by_partner": by_partner, "products": products}
