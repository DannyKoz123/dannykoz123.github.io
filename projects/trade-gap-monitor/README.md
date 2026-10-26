# Trade Gap Monitor

Flags mirror-trade gaps and post-2022 surges in dual-use goods moving from
suppliers (China, Germany, US) through Central Asia and the Caucasus to Russia,
using UN Comtrade.

**Demo 1:** do integrated-circuit exports to Kyrgyzstan, Kazakhstan and Armenia
exceed what those countries report importing, and do their exports to Russia
jump against the 2019–2021 baseline? Countries, products and years live in
`config/demo1.toml`.

A gap is a lead, not evidence of wrongdoing. Freight costs, re-exports, timing
and classification differences all create gaps on their own.

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```sh
cd projects/trade-gap-monitor
uv sync
cp .env.example .env   # optional: add a free Comtrade API key
uv run pytest
```

Without a key the keyless preview endpoint is used (500 rows per call), which
is enough for Demo 1. Get a free key at <https://comtradedeveloper.un.org>.

## Run

Each config in `config/` writes to `output/<config name>/`.

```sh
uv run tradegap run                              # demo1: chips, 3 intermediaries
uv run tradegap run --config config/scan.toml    # scan: 50 CHPL codes, 12 candidates
uv run tradegap products --config config/scan.toml  # check each code's Comtrade description
```

`run` is `fetch` + `analyze`; either can be run separately. The scan needs a
Comtrade API key (about 230 requests, under the free 500/day). Interrupted
fetches resume from the cache in `data/cache/`.

Outputs: `report.html` (self-contained, opens offline) and one CSV per table.
Neither `output/` nor `data/cache/` is committed: the Comtrade licence
restricts redistributing raw data, so publish derived charts only.

## Method

- **Re-export surge (report section 1):** intermediary-reported exports to
  Russia vs the 2019–2021 average.
- **World-total mirror (section 2):** an intermediary's reported imports from
  the world vs the sum of every country's reported exports to it. Totals cancel
  the country-of-origin vs country-of-shipment mismatch that distorts
  bilateral pairs. Also shows the share of imports passed on to Russia.
- **Who ships to Russia (section 3):** every reporter's exports to Russia.
- **Bilateral gap (section 4):** importer-reported CIF value ÷ `cif_fob_factor` minus
  exporter-reported FOB value, per supplier → intermediary pair, product and
  year. Negative means goods "disappear" on arrival.
- Russia stopped publishing detailed trade data in 2022, so it appears only as
  a partner.

## Layout

```
config/*.toml          countries, HS codes and tiers, years
src/tradegap/
  comtrade.py          API client + parquet cache
  gaps.py              normalization, mirror gaps, surges, ranking
  report.py            static HTML report
  cli.py               `tradegap` command
tests/                 unit tests (no network)
```
