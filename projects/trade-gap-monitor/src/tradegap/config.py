import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "cache"
OUTPUT_DIR = ROOT / "output"


@dataclass(frozen=True)
class Config:
    name: str
    title: str
    years: list[int]
    baseline_years: list[int]
    cif_fob_factor: float
    suppliers: dict[str, int]
    intermediaries: dict[str, int]
    target: dict[str, int]
    products: dict[str, str]
    tiers: dict[str, list[str]] = field(default_factory=dict)

    @property
    def countries(self) -> dict[int, str]:
        """M49 code -> ISO3 label for every country in the config."""
        merged = {**self.suppliers, **self.intermediaries, **self.target}
        return {code: iso for iso, code in merged.items()}

    @property
    def product_tier(self) -> dict[str, str]:
        return {hs: tier for tier, codes in self.tiers.items() for hs in codes}

    @property
    def output_dir(self) -> Path:
        return OUTPUT_DIR / self.name


def load_config(path: Path) -> Config:
    raw = tomllib.loads(path.read_text())
    cfg = Config(
        name=path.stem,
        title=raw.get("title", "Trade Gap Monitor"),
        years=raw["years"],
        baseline_years=raw["baseline_years"],
        cif_fob_factor=raw["cif_fob_factor"],
        suppliers=raw["suppliers"],
        intermediaries=raw["intermediaries"],
        target=raw["target"],
        products=raw["products"],
        tiers=raw.get("tiers", {}),
    )
    overlap = set(cfg.suppliers.values()) & set(cfg.intermediaries.values())
    if overlap:
        raise ValueError(f"{path.name}: countries cannot be both supplier and intermediary: {overlap}")
    untiered = set(cfg.products) - set(cfg.product_tier) if cfg.tiers else set()
    if untiered:
        raise ValueError(f"{path.name}: products missing from [tiers]: {sorted(untiered)}")
    return cfg
