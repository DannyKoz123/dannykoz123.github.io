import os
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer
from dotenv import load_dotenv

from . import comtrade, drill, gaps, hkstat, report
from .config import ROOT, Config, load_config

app = typer.Typer(help="Mirror-trade gap monitor.")
DEFAULT_CONFIG = ROOT / "config" / "demo1.toml"
# The keyless preview endpoint caps responses at 500 rows; more products than
# this overflow it for the larger queries.
MAX_PRODUCTS_WITHOUT_KEY = 4


def _paths(cfg: Config) -> tuple[Path, Path]:
    return cfg.output_dir / "raw.parquet", cfg.output_dir / "raw_world.parquet"


@app.command()
def fetch(config: Path = DEFAULT_CONFIG) -> None:
    """Download (or load from cache) the Comtrade rows the config needs.

    Interrupted runs resume from the cache.
    """
    load_dotenv(ROOT / ".env")
    cfg = load_config(config)
    if not os.environ.get("COMTRADE_API_KEY") and len(cfg.products) > MAX_PRODUCTS_WITHOUT_KEY:
        raise typer.BadParameter(
            f"{config.name} has {len(cfg.products)} products; set COMTRADE_API_KEY in .env"
        )
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    raw_path, world_path = _paths(cfg)
    for path, frame in [(raw_path, comtrade.fetch_config(cfg)),
                        (world_path, comtrade.fetch_world_mirror(cfg))]:
        frame.to_parquet(path)
        typer.echo(f"{len(frame)} rows -> {path}")


@app.command()
def products(config: Path = DEFAULT_CONFIG) -> None:
    """Show Comtrade's description of each configured code, to check the list."""
    cfg = load_config(config)
    raw_path, world_path = _paths(cfg)
    raw = pd.concat([pd.read_parquet(raw_path), pd.read_parquet(world_path)])
    check = gaps.product_check(raw, cfg)
    check.to_csv(cfg.output_dir / "products.csv", index=False)
    for r in check.itertuples():
        flag = "  NO DATA" if r.rows == 0 else ""
        typer.echo(f"{r.tier:>4}  {r.hs}  {r.config_name[:40]:<40}  "
                   f"{r.comtrade_description[:70]}{flag}")


@app.command()
def analyze(config: Path = DEFAULT_CONFIG) -> None:
    """Compute surges and mirror gaps, then write the HTML report."""
    cfg = load_config(config)
    raw_path, world_path = _paths(cfg)
    raw, raw_world = pd.read_parquet(raw_path), pd.read_parquet(world_path)
    names = gaps.country_names(pd.concat([raw, raw_world]))
    world = gaps.normalize(raw_world)
    df = gaps.combine(gaps.normalize(raw), world)

    surges = gaps.surge_table(df, cfg)
    world_mirror = gaps.world_mirror(df, world, cfg)
    tables = {
        "ranking": gaps.scan_ranking(surges, world_mirror, cfg),
        "surges": surges,
        "tiers": gaps.tier_breakdown(df, cfg),
        "world_mirror": world_mirror,
        "to_target": gaps.exports_to_target(world, cfg),
        "mirror_gaps": gaps.mirror_gaps(df, cfg),
        "coverage": gaps.reporting_coverage(df, cfg),
    }
    for name, table in tables.items():
        table.to_csv(cfg.output_dir / f"{name}.csv", index=name == "coverage")

    out = cfg.output_dir / "report.html"
    report.write_report(tables, cfg, names, out)
    typer.echo(f"Report -> {out}")


@app.command(name="drill")
def drill_cmd(
    origin: str = typer.Option(..., help="ISO3 of the shipping country, e.g. HKG"),
    via: str = typer.Option(..., help="ISO3 of the suspected route, e.g. UZB"),
    config: Path = DEFAULT_CONFIG,
    start: int = 2021,
    end: int = 2025,
) -> None:
    """Monthly drill-down on one route, e.g. --origin HKG --via UZB."""
    load_dotenv(ROOT / ".env")
    cfg = load_config(config)
    if not os.environ.get("COMTRADE_API_KEY"):
        raise typer.BadParameter("monthly drill-downs need COMTRADE_API_KEY in .env")
    codes = {**cfg.suppliers, **cfg.intermediaries, **cfg.target}
    missing = [c for c in (origin, via) if c not in codes]
    if missing:
        raise typer.BadParameter(f"not in {config.name}: {missing}")
    years = list(range(start, end + 1))
    raw = comtrade.fetch_drill(cfg, codes[origin], codes[via], years)
    out_dir = cfg.output_dir / f"drill_{origin}_{via}"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(out_dir / "raw.parquet")

    names = {**gaps.country_names(raw), **cfg.countries}
    tables = drill.write_drill_report(drill.normalize_monthly(raw), codes[origin], codes[via],
                                      cfg, names, out_dir / "report.html")
    for name, table in tables.items():
        table.to_csv(out_dir / f"{name}.csv")
    typer.echo(f"Report -> {out_dir / 'report.html'}")


@app.command(name="hk-reexports")
def hk_reexports(
    dest: Annotated[list[str] | None, typer.Option(help="Hong Kong API country code; repeatable")] = None,
    config: Path = DEFAULT_CONFIG,
    start: int = 2021,
    end: int = 2025,
) -> None:
    """Hong Kong re-exports vs domestic exports to each destination, by origin."""
    cfg = load_config(config)
    try:
        df = hkstat.fetch_reexports(dest or ["UZ", "RU"], list(cfg.products), start, end)
    except hkstat.UsageLimit as exc:
        typer.echo(f"{exc}. Finished requests are cached; rerun later.")
        raise typer.Exit(1) from exc
    out_dir = cfg.output_dir / "hk_reexports"
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "hk_reexports.csv", index=False)

    for (ttype, destination), part in df.groupby(["trade_type", "destination"]):
        table = part.pivot_table(index="origin", columns="year", values="usd", aggfunc="sum")
        table = table.sort_values(table.columns[-1] if len(table.columns) else "origin",
                                  ascending=False) / 1e6
        typer.echo(f"\n{ttype} to {destination}, USD millions, by origin:")
        typer.echo(table.head(12).round(1).to_string())
    typer.echo(f"\nCSV -> {out_dir / 'hk_reexports.csv'}")


@app.command()
def run(config: Path = DEFAULT_CONFIG) -> None:
    """fetch + analyze."""
    fetch(config)
    analyze(config)
