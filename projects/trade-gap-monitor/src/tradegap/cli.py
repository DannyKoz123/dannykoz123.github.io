from pathlib import Path

import pandas as pd
import typer
from dotenv import load_dotenv

from . import comtrade, gaps, report
from .config import OUTPUT_DIR, ROOT, load_config

app = typer.Typer(help="Mirror-trade gap monitor.")
DEFAULT_CONFIG = ROOT / "config" / "demo1.toml"
RAW_PATH = OUTPUT_DIR / "raw.parquet"
WORLD_PATH = OUTPUT_DIR / "raw_world.parquet"


@app.command()
def fetch(config: Path = DEFAULT_CONFIG) -> None:
    """Download (or load from cache) the Comtrade rows the config needs."""
    load_dotenv(ROOT / ".env")
    cfg = load_config(config)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path, frame in [(RAW_PATH, comtrade.fetch_config(cfg)),
                        (WORLD_PATH, comtrade.fetch_world_mirror(cfg))]:
        frame.to_parquet(path)
        typer.echo(f"{len(frame)} rows -> {path}")


@app.command()
def analyze(config: Path = DEFAULT_CONFIG) -> None:
    """Compute surges and mirror gaps, then write the HTML report."""
    cfg = load_config(config)
    raw, raw_world = pd.read_parquet(RAW_PATH), pd.read_parquet(WORLD_PATH)
    names = gaps.country_names(pd.concat([raw, raw_world]))
    df, world = gaps.normalize(raw), gaps.normalize(raw_world)

    tables = {
        "surges": gaps.surge_table(df, cfg),
        "world_mirror": gaps.world_mirror(df, world, cfg),
        "to_target": gaps.exports_to_target(world, cfg),
        "mirror_gaps": gaps.mirror_gaps(df, cfg),
        "coverage": gaps.reporting_coverage(df, cfg),
    }
    for name, table in tables.items():
        table.to_csv(OUTPUT_DIR / f"{name}.csv", index=name == "coverage")

    out = OUTPUT_DIR / "demo1.html"
    report.write_report(tables, cfg, names, out)
    typer.echo(f"Report -> {out}")


@app.command()
def run(config: Path = DEFAULT_CONFIG) -> None:
    """fetch + analyze."""
    fetch(config)
    analyze(config)
