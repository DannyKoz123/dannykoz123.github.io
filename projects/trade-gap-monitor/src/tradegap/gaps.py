"""Mirror-gap and surge calculations on normalized Comtrade rows."""

import numpy as np
import pandas as pd

from .config import Config


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


def mirror_gaps(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Compare supplier-reported exports with intermediary-reported imports.

    gap < 0 means the intermediary declares less than the supplier says it
    shipped: goods that "disappear" on arrival.
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


def surges(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Each flow's value relative to its pre-war baseline average."""
    keys = ["reporter", "partner", "flow", "hs"]
    base = (
        df[df["year"].isin(cfg.baseline_years)]
        .groupby(keys, as_index=False)["value"]
        .mean()
        .rename(columns={"value": "baseline"})
    )
    out = df.merge(base, on=keys, how="left")
    out["vs_baseline"] = out["value"] / out["baseline"]
    return out


def reexports_to_target(df: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Intermediary exports to the target, with their baseline multiple."""
    flows = df[
        (df["flow"] == "X")
        & df["reporter"].isin(cfg.intermediaries.values())
        & df["partner"].isin(cfg.target.values())
    ]
    return surges(flows, cfg)


def top_anomalies(gaps: pd.DataFrame, since: int = 2022, n: int = 20) -> pd.DataFrame:
    """Largest absolute post-invasion mirror gaps, in USD."""
    recent = gaps[(gaps["year"] >= since) & gaps["gap"].notna()]
    return recent.reindex(recent["gap"].abs().sort_values(ascending=False).index).head(n)
