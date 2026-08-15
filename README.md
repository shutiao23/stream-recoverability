# Stream Recoverability

Reproducible experiments for reconstructing daily stream observations under
structured monitoring outages.

![Study area and monitoring stations](figures/study_area.png)

This repository contains the data pipeline, models, evaluation code, and
analysis workflow for a three-station Upper Jinsha River case study. It asks
when missing stream temperature, discharge, and water-level observations can
be recovered; which remaining information sources make recovery possible; and
how reconstruction quality changes as gaps become longer or more stations
fail.

The primary task is **offline imputation**, where observations on both sides of
a gap may be used. A separate **online recovery** protocol is strictly causal
and never uses future observations.

> **Evidence status:** smoke, truncated, and partial runs are implementation
> checks. A smoke manifest may be complete for its four-scenario grid, but it
> is never scientific evidence. Formal evidence requires
> `training_profile: formal`, the complete intended suite and seed contract,
> and `formal_design_complete: true` in the relevant manifest.

## What is included

- Leakage-controlled data auditing, unit conversion, daily alignment,
  chronological splitting, and train-only scaling.
- Deterministic point, block, multiblock, station-outage, network-outage,
  asynchronous, and event-conditioned masks.
- Conventional interpolation, smoothing, regression, tree-based, recurrent,
  attention-based, and multisource quantile models.
- Event-level accuracy, extremes, timing, boundary, uncertainty, and
  hydrological diagnostics.
- Recoverability frontiers, information-compensation analysis, exact Shapley
  allocation, mutual information, transfer entropy, and network-resilience
  analysis.
- Resumable experiment execution, deterministic sharding, manifest-based
  completeness checks, and publication figure/table generation.

## Study design

| Item | Design |
| --- | --- |
| Monitoring stations | Batang (`B1`), Shigu (`S2`), and Panzhihua (`P3`) |
| River system | Upper Jinsha River, China |
| Temporal resolution | Daily |
| Study period | 1 January 2006 to 31 December 2020 |
| Training period | 2006–2015 |
| Validation period | 2016–2017 |
| Test period | 2018–2020 |
| Primary target | Stream temperature (`T`) |
| Secondary targets | Discharge (`F`) and water level (`L`) |
| Auxiliary variables | Air temperature (`Ta`), precipitation (`P`), wind speed (`W`), relative humidity (`RH`), and sunshine duration (`DH`) |
| Formal training seeds | `11`, `22`, `33`, `44`, `55` |
| Formal mask seeds | `101`–`120` |
| External validation | Unavailable; leave-one-station-out experiments are internal and exploratory |

The fixed study definition is recorded in
[`study_manifest.yaml`](study_manifest.yaml). Variable definitions and units
are documented in
[`metadata/data_dictionary.csv`](metadata/data_dictionary.csv), and station
details are in
[`metadata/station_metadata.csv`](metadata/station_metadata.csv).

## Installation

Python 3.10 or newer is required. Run all commands from the repository root.

```bash
git clone https://github.com/shutiao23/stream-recoverability.git
cd stream-recoverability

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The main dependencies are NumPy, pandas, SciPy, scikit-learn, statsmodels,
PyTorch, XGBoost, PyArrow, Matplotlib, and Seaborn. They are declared in
[`pyproject.toml`](pyproject.toml).

Verify the installation with:

```bash
pytest
```

## Quick start

The repository includes prepared tables, so a smoke experiment can be run
directly. The paths below keep demonstration artifacts separate from the
included results:

```bash
python scripts/08_run_experiments.py \
  --suite smoke \
  --models climatology linear \
  --output-dir results/demo-smoke \
  --mask-dir masks/demo-smoke
```

This creates a small, deterministic end-to-end run covering one point-gap,
one single-block, one multiblock, and one station-outage condition. It is a
software check, not a scientific benchmark.

For the simpler standalone fixed-mask baseline workflow:

```bash
python scripts/03_generate_masks.py --output masks/demo
python scripts/04_run_baselines.py \
  --masks masks/demo/test \
  --models climatology linear pchip \
  --output-dir results/demo-baselines
```

`03_generate_masks.py` builds the compact validation/test libraries used by
the standalone baseline, deep-baseline, and online scripts. The unified
M1–M10 runner in `08_run_experiments.py` manages its own scenario masks.
The standalone script's optional YAML schema is different from the unified
outage definitions in `configs/scenarios/`; those files are not directly
interchangeable.

To regenerate the included audit, processed datasets, and EDA artifacts in
their standard locations, run:

```bash
python scripts/01_audit_data.py
python scripts/02_prepare_data.py
python scripts/07_run_eda.py
```

These three commands intentionally write into `results/data_audit/`,
`data/processed/`, `results/eda/`, and `figures/`. Every script also accepts
path overrides when an isolated rebuild is preferable.

## Workflow

```text
raw station tables + metadata
              |
              v
       audit and preparation
              |
              v
 processed long/wide tables + train-only scaler
              |
              v
     deterministic artificial outages
              |
              v
 traditional, deep, proposed, and online models
              |
              v
      daily predictions + event metrics
              |
              v
 frontier, compensation, uncertainty, and resilience analyses
              |
              v
       publication figures, tables, and manifests
```

The numbered scripts expose each stage:

| Script | Purpose |
| --- | --- |
| `01_audit_data.py` | Audit dates, source-missing codes, constant runs, extremes, and rating-curve diagnostics. |
| `02_prepare_data.py` | Create aligned long/wide Parquet tables, fixed chronological splits, and a train-only scaler. |
| `03_generate_masks.py` | Create standalone validation and test mask libraries. |
| `04_run_baselines.py` | Evaluate traditional offline baselines on a fixed mask library. |
| `05_train_deep_baselines.py` | Train the project-specific BRITS-style and SAITS-style baselines. |
| `06_train_proposed.py` | Run a synthetic smoke test of the proposed model; it does not train the real-data model. |
| `07_run_eda.py` | Produce descriptive tables, event labels, QC plots, and study-area inputs. |
| `08_run_experiments.py` | Run resumable `smoke`, `core`, or `full` M1–M10 experiments; real proposed-model training happens here. |
| `09_analyze_results.py` | Compute statistical comparisons, frontiers, calibration, resilience, and scientific-preservation diagnostics. |
| `10_run_online.py` | Run the separate, strictly causal online protocol. |
| `11_make_figures.py` | Generate available publication figures and tables and freeze their input manifest. |
| `12_run_science_experiments.py` | Run dense-gap, network-resilience, information-compensation, or information-metric studies. |
| `13_aggregate_formal_results.py` | Validate and combine complete formal experiment outputs. |

Use `python scripts/<script>.py --help` for all arguments and output-path
overrides.

## Experiment suites

The unified runner exposes three M1–M10 suite sizes:

| Suite | Scope | Conditions | Executable scenarios | Intended use |
| --- | --- | ---: | ---: | --- |
| `smoke` | One condition from each of M1–M4 | 4 | 4 | Fast integration check |
| `core` | M1–M4 | 156 | 3,120 | Main structured-gap design |
| `full` | M1–M10 | 300 | 5,943 | Complete fixed experiment grid |

The full grid adds secondary-target gaps, multi-station outages,
event-conditioned gaps, window sensitivity, length extrapolation, and
internal leave-one-station-out transfer. Dedicated science suites add:

- `dense`: single gaps spanning the predeclared 1–365 day grid for
  recoverability-frontier estimation;
- `resilience`: the complete failure powerset of the three-station network;
- `compensation`: the S0 reference plus all 15 non-empty subsets of information
  groups A–D on identical hidden cells;
- `information`: training-only k-nearest-neighbour mutual information and
  bidirectional transfer entropy. These are descriptive information measures,
  not causal estimates.

## Models

The unified offline runner supports:

- **Temporal references:** training climatology, linear interpolation, PCHIP,
  and Kalman smoothing.
- **Regression and tree models:** air-only, air-plus-hydrology, donor-station
  regression, random forest, XGBoost, rating-curve, and independent-flow
  baselines.
- **Deep baselines:** compact project-specific BRITS-style and SAITS-style
  implementations. They are not runs of the authors' official packages.
- **Proposed model:** a missing-aware multisource imputer that produces ordered
  temperature quantiles from four explicit information groups:
  local temporal context (A), same-station hydraulics (B), other-station
  observations (C), and local meteorology/calendar information (D). Its
  cross-station component uses masked attention, not a graph neural network.

The online protocol separately compares training climatology,
last-observation persistence, and a forward-only causal GRU.

## Running larger experiments

A complete full-suite invocation is:

```bash
python scripts/08_run_experiments.py \
  --suite full \
  --models climatology linear pchip kalman air_only air_hydro \
           donor_regression random_forest xgboost rating_curve \
           independent_flow brits saits proposed
```

This run is computationally expensive. Execution is resumable by default and
can be divided deterministically with `--shard-index` and `--shard-count`.
Training budgets and model settings are controlled by
[`configs/experiments.yaml`](configs/experiments.yaml).

The dedicated science entry points are:

```bash
python scripts/12_run_science_experiments.py dense --models climatology linear
python scripts/12_run_science_experiments.py resilience --models climatology linear
python scripts/12_run_science_experiments.py information
```

Information-compensation runs require compatible proposed-model checkpoints.
Inspect their contract before launching the run:

```bash
python scripts/12_run_science_experiments.py compensation --help
```

To analyse outputs from the unified runner, pass its paths explicitly because
the analysis script defaults to the standalone baseline outputs:

```bash
python scripts/09_analyze_results.py \
  --event-metrics results/experiments/event_metrics.parquet \
  --daily-predictions results/experiments/daily_predictions.parquet \
  --run-manifest results/experiments/run_manifest.json \
  --output-dir results/analysis
```

Run the causal protocol independently:

```bash
python scripts/10_run_online.py \
  --smoke \
  --output-dir results/online-smoke
```

## Outputs and reproducibility

Depending on the entry point, the workflow writes:

- `daily_predictions.parquet` or `predictions.parquet`: predictions at
  quality-eligible, artificially hidden cells;
- `event_metrics.parquet`: event-level accuracy, boundary, extreme,
  hydrological, and uncertainty metrics;
- `run_manifest.json`: suite configuration, expected/completed units, seed
  coverage, training profile, and completeness status;
- per-scenario status files: execution contracts, input identities, completed
  runs, and structured skip reasons;
- `results/analysis/`: statistical, frontier, compensation, resilience, and
  scientific-preservation tables;
- `figures/` and `paper/tables/`: EDA, QC, and publication outputs;
- `checkpoints/`: trained-model state and training histories.

The pipeline protects the evaluation boundary by fitting scalers,
climatologies, normalisers, event thresholds, and model parameters on the
training period only. Artificial masks can target only finite,
quality-eligible observations and are removed from every model input path.
Sequence windows never cross train/validation/test boundaries, and the online
protocol explicitly forbids future values, backward interpolation, and
smoothing.

Formal aggregation is intentionally strict: missing seed coverage, incomplete
scenario grids, stale checkpoints, conflicting keys, or invalid partial
coalitions prevent a run from being marked complete.

## Repository layout

```text
stream-recoverability/
├── configs/                    experiment and outage definitions
├── data/raw/                   supplied daily station CSV files
├── data/processed/             aligned datasets, splits, scaler, event labels
├── figures/                    study-area, EDA, QC, and publication figures
├── masks/                      deterministic artificial-mask libraries
├── metadata/                   station, variable, QC, and provenance metadata
├── paper/                      manuscript, detailed methods, and references
├── results/                    audit, EDA, experiment, analysis, and online outputs
├── scripts/                    numbered executable workflow
├── src/stream_recoverability/  reusable package implementation
├── tests/                      unit and integration tests
├── pyproject.toml              package metadata and dependencies
└── study_manifest.yaml         fixed scientific design
```

## Data provenance and limitations

The supplied CSV files do not contain provider-level per-value quality flags,
station names, source identifiers, or complete provenance metadata. The
repository therefore records independently reconciled variable, station, and
source information instead of silently assuming it.

Important limitations include:

- `observed_unflagged` means that a finite published value is eligible for this
  analysis; it does not mean the value was individually certified by the data
  provider;
- the retained B1 water-level series contains an approximately 8.48 m datum
  shift at the start of 2019;
- the retained S2 series has a documented 2013–2019 ordering discrepancy with
  an external monthly provenance check;
- no comparable external daily stream-temperature panel was established, so
  the project makes no expanded-network or external-validation claim;
- M10 leave-one-station-out results describe internal transfer among these
  three stations only.

Read the full provenance record in
[`metadata/source_documentation/README.md`](metadata/source_documentation/README.md)
and the generated audit in
[`results/data_audit/data_quality_report.md`](results/data_audit/data_quality_report.md)
before interpreting results or reusing the data.

## Further documentation

- [Detailed methods](paper/methods.md)
- [Manuscript](paper/manuscript.md)
- [Study manifest](study_manifest.yaml)
- [Data dictionary](metadata/data_dictionary.csv)
- [Source and provenance notes](metadata/source_documentation/README.md)
- [Bibliography](paper/references.bib)
