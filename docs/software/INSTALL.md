# Installation and quickstart

Package: `stream-recoverability` with the standalone `gapbench` library
Version: `1.2.0`
Python: 3.10 or newer (3.11 recommended)

This guide covers a clean code-only install. It does not install, license, or
redistribute observational data. Provider terms are documented in
`DATA_RIGHTS.md`.

## 1. Clean install

From the repository root:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[review,dev]"
```

The base package provides the analysis dependencies. `review` adds LightGBM,
`pypots`, `conditionalconformal`, `cvxpy`, `requests`, and `tabulate`; `dev` adds
`pytest`.

Install the standalone benchmark library separately:

```bash
python -m pip install -e gapbench
```

`gapbench` has only NumPy and pandas as runtime dependencies. The base
`pip install -e gapbench` intentionally omits pytest; it does not install the
test runner or run the tests. It does not import the research pipeline and
contains no restricted observations.

### Optional extras

| Extra | Purpose | Example |
| --- | --- | --- |
| `review` | LightGBM (D2), conformal and review-replay dependencies | `pip install -e ".[review]"` |
| `dev` | pytest for the repository tests | `pip install -e ".[dev]"` |
| `revision` | Shapely, pyproj, and numba revision utilities | `pip install -e ".[revision]"` |
| `reference` | pypots reference models | `pip install -e ".[reference]"` |
| `test` (inside `gapbench`) | pytest for the small library | `pip install -e "gapbench[test]"` |

For the full documented review surface:

```bash
python -m pip install -e ".[review,revision,dev]"
```

## 2. Thirty-minute quickstart

The synthetic quickstart needs only `gapbench` and runs in well under one second:

```bash
python gapbench/examples/quickstart.py
```

It creates a 20-year daily series with a 60-day outage and three shorter
outages, measures the best fully observed 30-day window, selects 18 years with
the CDF and Sxx rules while retaining all 16 complete years, fits the
finite-record reference trend, and decomposes the slope error. The expected
output is recorded in `gapbench/README.md`.

A 30-minute budget is enough to create the virtual environment, install the
dependencies, run the example, and read `gapbench/README.md`. The full research
pipeline is much larger and is not part of this quickstart.

For the small library's own tests, install its test extra first; the base
`pip install -e gapbench` intentionally omits pytest:

```bash
python -m pip install -e "gapbench[test]"
python -m pytest -q gapbench/tests
```

## 3. LightGBM and D2

LightGBM is intentionally in the `review` extra, not in the base install. Check
it with:

```bash
python -c "import lightgbm; print(lightgbm.__version__)"
```

The `gapbench` quickstart does not need LightGBM. The D2 LightGBM comparisons
and the associated review targets do; without LightGBM those comparisons cannot
run, while deterministic and non-D2 paths remain available. A missing LightGBM
import is an environment limitation, not evidence about D2 performance.

## 4. Docker

The Dockerfile installs `.[review,dev]`, includes `gapbench/`, verifies the
LightGBM import, and runs the gapbench quickstart by default:

```bash
docker build -t stream-recoverability:1.2.0 .
docker run --rm stream-recoverability:1.2.0
```

The container does not include restricted observations. It is a code and
synthetic-example smoke environment, not a complete reproduction of the
restricted-data study.

If Docker is unavailable or the daemon is not accessible to the current user,
record that the build was not run; do not treat a Dockerfile inspection as a
successful build.

## 5. Metadata checks

Confirm that the package, citation, and Zenodo deposit metadata versions agree:

```bash
python scripts/check_version_consistency.py
```

The command exits nonzero only for inconsistent version files. A warning that
the latest git tag `v1.0.0` is historical is expected until a `v1.2.0` tag and an
archival DOI exist. No GitHub release, Zenodo DOI, or reviewer access is
currently established; see `docs/software/RELEASE_CHECKLIST.md`.
