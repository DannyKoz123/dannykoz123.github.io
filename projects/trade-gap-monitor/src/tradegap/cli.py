from pathlib import Path

import pandas as pd
import typer
from dotenv import load_dotenv

from . import comtrade, gaps, report
from .config import OUTPUT_DIR, ROOT, load_config

app = typer.Typer(help="Mirror-trade gap monitor.")
DEFAULT_CONFIG = ROOT / "config" / "demo1.toml"
RAW_PATH = OUTPUT_DIR / "raw.parquet"


@app.command()
def fetch(config: Path = DEFAULT_CONFIG) -> None:
    """Download (or load from cache) the Comtrade rows the config needs."""
    load_dotenv(ROOT / ".env")
    raw = comtrade.fetch_config(load_config(config))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(RAW_PATH)
    typer.echo(f"{len(raw)} rows -> {RAW_PATH}")


@app.command()
def analyze(config: Path = DEFAULT_CONFIG) -> None:
    """Compute mirror gaps and re-export surges, then write the HTML report."""
    cfg = load_config(config)
    df = gaps.normalize(pd.read_parquet(RAW_PATH))
    mirror = gaps.mirror_gaps(df, cfg)
    reexports = gaps.reexports_to_target(df, cfg)
    anomalies = gaps.top_anomalies(mirror)

    mirror.to_csv(OUTPUT_DIR / "mirror_gaps.csv", index=False)
    reexports.to_csv(OUTPUT_DIR / "reexports.csv", index=False)
    out = OUTPUT_DIR / "demo1.html"
    report.write_report(mirror, reexports, anomalies, cfg, out)
    typer.echo(f"Report -> {out}")


@app.command()
def run(config: Path = DEFAULT_CONFIG) -> None:
    """fetch + analyze."""
    fetch(config)
    analyze(config)
