import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "cache"
OUTPUT_DIR = ROOT / "output"


@dataclass(frozen=True)
class Config:
    years: list[int]
    baseline_years: list[int]
    cif_fob_factor: float
    suppliers: dict[str, int]
    intermediaries: dict[str, int]
    target: dict[str, int]
    products: dict[str, str]

    @property
    def countries(self) -> dict[int, str]:
        """M49 code -> ISO3 label for every country in the config."""
        merged = {**self.suppliers, **self.intermediaries, **self.target}
        return {code: iso for iso, code in merged.items()}


def load_config(path: Path) -> Config:
    raw = tomllib.loads(path.read_text())
    return Config(
        years=raw["years"],
        baseline_years=raw["baseline_years"],
        cif_fob_factor=raw["cif_fob_factor"],
        suppliers=raw["suppliers"],
        intermediaries=raw["intermediaries"],
        target=raw["target"],
        products=raw["products"],
    )
