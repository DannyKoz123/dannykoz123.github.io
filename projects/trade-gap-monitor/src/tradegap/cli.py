import os
from pathlib import Path

import pandas as pd
import typer
from dotenv import load_dotenv

from . import comtrade, gaps, report
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


@app.command()
def run(config: Path = DEFAULT_CONFIG) -> None:
    """fetch + analyze."""
    fetch(config)
    analyze(config)
