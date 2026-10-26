"""Mirror-gap and surge calculations on normalized Comtrade rows."""

import numpy as np
import pandas as pd

from .config import Config

WORLD = 0
# Aggregate reporters that would double count individual members.
AGGREGATE_REPORTERS = {0, 97}
# Baselines below this are treated as "from ~0" rather than a multiple.
MIN_BASELINE = 50_000


def country_names(raw: pd.DataFrame) -> dict[int, str]:
    """M49 code -> ISO3 from the descriptions Comtrade returns."""
    names = {}
    for code_col, iso_col in [("reporterCode", "reporterISO"), ("partnerCode", "partnerISO")]:
        if iso_col in raw:
            pairs = raw[[code_col, iso_col]].dropna().drop_duplicates()
            names.update(dict(zip(pairs[code_col].astype(int), pairs[iso_col])))
    names[490] = "TWN"  # Comtrade's "Other Asia, nes"
    names[WORLD] = "World"
    return names


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Reduce raw Comtrade rows to one value per reporter/partner/flow/product/year.

    Imports are valued CIF and exports FOB where Comtrade provides them,
    falling back to the reporter's primary value.
    """
    df = raw[raw["flowCode"].isin(["M", "X"])].copy()
    cif = df.get("cifvalue", pd.Series(np.nan, index=df.index))
    fob = df.get("fobvalue", pd.Series(np.nan, index=df.index))
    preferred = np.where(df["flowCode"] == "M", cif, fob)
    preferred = pd.to_numeric(pd.Series(preferred, index=df.index), errors="coerce")
    df["value"] = preferred.fillna(df["primaryValue"]).astype(float)
    out = df.rename(
        columns={
            "reporterCode": "reporter",
            "partnerCode": "partner",
            "flowCode": "flow",
            "cmdCode": "hs",
            "refYear": "year",
        }
    )[["reporter", "partner", "flow", "hs", "year", "value"]]
    out["hs"] = out["hs"].astype(str)
    return out.groupby(["reporter", "partner", "flow", "hs", "year"], as_index=False)["value"].sum()


def reporting_coverage(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Which configured reporters returned any rows in each year."""
    codes = [*cfg.suppliers.values(), *cfg.intermediaries.values()]
    seen = df.groupby(["reporter", "year"]).size().unstack(fill_value=0) > 0
    return seen.reindex(index=codes, columns=cfg.years, fill_value=False)


def _yearly_total(flows: pd.DataFrame, key: str, df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Sum over products per key/year; a reporter that reported that year but
    has no row for the flow is recorded as 0, an unreported year stays NaN."""
    totals = flows.groupby([key, "year"])["value"].sum().unstack()
    totals = totals.reindex(columns=cfg.years)
    coverage = reporting_coverage(df, cfg)
    for code in totals.index:
        if code in coverage.index:
            reported = coverage.loc[code]
            totals.loc[code] = totals.loc[code].where(~reported, totals.loc[code].fillna(0))
    return totals


def mirror_gaps(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Compare supplier-reported exports with intermediary-reported imports.

    gap < 0 means the intermediary declares less than the supplier says it
    shipped. At the bilateral level this is dominated by importers recording
    country of origin while exporters record destination.
    """
    exports = df[df["flow"] == "X"].rename(
        columns={"reporter": "exporter", "partner": "importer", "value": "exp_value"}
    )
    imports = df[df["flow"] == "M"].rename(
        columns={"reporter": "importer", "partner": "exporter", "value": "imp_value"}
    )
    keys = ["exporter", "importer", "hs", "year"]
    merged = exports.drop(columns="flow").merge(imports.drop(columns="flow"), on=keys, how="outer")
    merged = merged[
        merged["exporter"].isin(cfg.suppliers.values())
        & merged["importer"].isin(cfg.intermediaries.values())
    ].copy()

    merged["imp_fob"] = merged["imp_value"] / cfg.cif_fob_factor
    merged["gap"] = merged["imp_fob"] - merged["exp_value"]
    merged["gap_ratio"] = merged["gap"] / merged["exp_value"]
    with np.errstate(divide="ignore", invalid="ignore"):
        merged["log_ratio"] = np.log(merged["imp_fob"] / merged["exp_value"])
    return merged.sort_values(keys).reset_index(drop=True)


def world_mirror(df: pd.DataFrame, world: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Per intermediary and year, across all integrated-circuit codes:

    - imp_fob: what it reports importing from the world (FOB-adjusted)
    - partner_exports: what every other country reports exporting to it
    - to_target: what it reports exporting to the target (Russia)

    Comparing totals cancels the origin-vs-consignment mismatch that distorts
    bilateral gaps. Countries that do not report push partner_exports down.
    """
    inter = list(cfg.intermediaries.values())
    target = list(cfg.target.values())

    imports = df[(df["flow"] == "M") & df["reporter"].isin(inter) & (df["partner"] == WORLD)]
    to_target = df[(df["flow"] == "X") & df["reporter"].isin(inter) & df["partner"].isin(target)]
    partner = world[
        (world["flow"] == "X")
        & world["partner"].isin(inter)
        & ~world["reporter"].isin(AGGREGATE_REPORTERS)
    ]

    imp = _yearly_total(imports, "reporter", df, cfg).stack(future_stack=True)
    tgt = _yearly_total(to_target, "reporter", df, cfg).stack(future_stack=True)
    exp = partner.groupby(["partner", "year"])["value"].sum()
    n_rep = partner.groupby(["partner", "year"])["reporter"].nunique()

    out = pd.DataFrame({
        "imp_fob": imp / cfg.cif_fob_factor,
        "partner_exports": exp.rename_axis(["reporter", "year"]),
        "partner_reporters": n_rep.rename_axis(["reporter", "year"]),
        "to_target": tgt,
    })
    out.index.names = ["intermediary", "year"]
    out = out.reset_index()
    out = out[out["intermediary"].isin(inter) & out["year"].isin(cfg.years)]
    out["gap"] = out["imp_fob"] - out["partner_exports"]
    out["gap_ratio"] = out["gap"] / out["partner_exports"]
    out["pass_through"] = out["to_target"] / out["imp_fob"]
    return out.sort_values(["intermediary", "year"]).reset_index(drop=True)


def surge_table(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Intermediary-reported exports to the target by year, with the peak
    post-baseline year as a multiple of the baseline average."""
    flows = df[
        (df["flow"] == "X")
        & df["reporter"].isin(cfg.intermediaries.values())
        & df["partner"].isin(cfg.target.values())
    ]
    totals = _yearly_total(flows, "reporter", df, cfg)
    totals = totals.reindex(list(cfg.intermediaries.values()))
    baseline = totals[cfg.baseline_years].mean(axis=1)
    later = [y for y in cfg.years if y not in cfg.baseline_years]
    peak = totals[later].max(axis=1)
    out = totals.copy()
    out["baseline"] = baseline
    out["peak"] = peak
    out["peak_year"] = totals[later].apply(
        lambda r: r.idxmax() if r.notna().any() else np.nan, axis=1
    )
    out["multiple"] = (peak / baseline).where(baseline >= MIN_BASELINE)
    out.index.name = "intermediary"
    out.columns.name = None
    return out.reset_index()


def exports_to_target(world: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Every country's reported exports to the target, summed over products."""
    flows = world[
        (world["flow"] == "X")
        & world["partner"].isin(cfg.target.values())
        & ~world["reporter"].isin(AGGREGATE_REPORTERS)
    ]
    return flows.groupby(["reporter", "year"], as_index=False)["value"].sum()


def top_anomalies(gaps: pd.DataFrame, since: int = 2022, n: int = 20) -> pd.DataFrame:
    """Largest absolute post-invasion mirror gaps, in USD."""
    recent = gaps[(gaps["year"] >= since) & gaps["gap"].notna()]
    return recent.reindex(recent["gap"].abs().sort_values(ascending=False).index).head(n)


def scan_ranking(surges: pd.DataFrame, world: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Rank intermediaries by how much they ship to the target in the latest
    two years, and whether that is growing relative to the years before."""
    recent = cfg.years[-2:]
    prior = [y for y in cfg.years if y not in cfg.baseline_years and y not in recent]
    out = surges[["intermediary", "baseline", *[y for y in cfg.years if y not in
                                                cfg.baseline_years]]].copy()
    out["recent_vs_prior"] = out[recent].mean(axis=1) / out[prior].mean(axis=1)
    latest = (
        world.dropna(subset=["pass_through"]).sort_values("year")
        .groupby("intermediary").last()[["year", "pass_through"]]
        .rename(columns={"year": "share_year", "pass_through": "share_to_target"})
    )
    out = out.merge(latest, left_on="intermediary", right_index=True, how="left")
    out["recent_max"] = out[recent].max(axis=1)
    return out.sort_values("recent_max", ascending=False).reset_index(drop=True)


def tier_breakdown(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Intermediary exports to the target by product tier and year."""
    flows = df[
        (df["flow"] == "X")
        & df["reporter"].isin(cfg.intermediaries.values())
        & df["partner"].isin(cfg.target.values())
    ].copy()
    flows["tier"] = flows["hs"].map(cfg.product_tier).fillna("other")
    out = flows.groupby(["reporter", "tier", "year"])["value"].sum().unstack()
    out = out.reindex(columns=cfg.years)
    out.columns.name = None
    return out.reset_index().rename(columns={"reporter": "intermediary"})


def product_check(raw: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Comtrade's own description and row count for each configured code."""
    desc = raw.dropna(subset=["cmdDesc"]).groupby("cmdCode")["cmdDesc"].first() \
        if "cmdDesc" in raw else pd.Series(dtype=str)
    rows = raw.groupby("cmdCode").size() if not raw.empty else pd.Series(dtype=int)
    return pd.DataFrame({
        "hs": list(cfg.products),
        "tier": [cfg.product_tier.get(hs, "") for hs in cfg.products],
        "config_name": list(cfg.products.values()),
        "comtrade_description": [desc.get(hs, "") for hs in cfg.products],
        "rows": [int(rows.get(hs, 0)) for hs in cfg.products],
    })
