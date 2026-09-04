#!/usr/bin/env python3
"""Round-2 revision W2-A: 14- and 60-day stratified fitting-period cuts
(REVIEW_v14_round2.md Major 2 / Step "第 2 周").

The differential design's fitted durations were {7, 30, 90, 180} d, while
14- and 60-day placements exist on the evaluation side.  This script cuts
14- and 60-day gaps inside the fitting years with the same machine that
produced the archived fit losses (`fitting_period_empirical_losses` in
src/stream_recoverability/experiments/recovery_roster.py; outer 70/30
year split; first 70% of fitting years train XGBoost; remaining fitting
years supply observed gap truth; up to 20 seasonally stratified
placements per station-gap-season cell), on both scored panels:

  first  panel: results/development_v11/confirmation_daily_qc/networks/
                placements results/development_v11/route_a_confirmation/placement_losses.csv
  second panel: results/development_v11/second_confirmation/daily_qc/networks/
                placements results/development_v11/second_confirmation/scoring/placement_losses.csv

Determinism is asserted: a 4-duration rerun (7/30/90/180 d) on two probe
networks must reproduce the archived `confirmation_empirical_fit_losses.csv`
rows bit-for-bit (max |delta MAE| < 1e-12, identical gap starts).

Outputs:
  results/v14/p0_differential/fitting_cuts_14_60_first.csv
  results/v14/p0_differential/fitting_cuts_14_60_second.csv
  results/v14/p0_differential/fit_losses_extended_first.csv   (archived + 14/60, canonical W2 input)
  results/v14/p0_differential/fit_losses_extended_second.csv

Run: PYTHONPATH=$PWD/src python3 scripts/152_run_v14_r2_fitting_cuts_14_60.py
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stream_recoverability.experiments.development_recovery import (
    read_temperature_panel,
)
from stream_recoverability.experiments.recovery_roster import (
    XGBOOST_PARAMETERS,
    fitting_period_empirical_losses,
)

OUTPUT = ROOT / "results/v14/p0_differential"
FIRST_DAILY = ROOT / "results/development_v11/confirmation_daily_qc/networks"
SECOND_DAILY = ROOT / "results/development_v11/second_confirmation/daily_qc/networks"
FIRST_PLACEMENTS = (
    ROOT / "results/development_v11/route_a_confirmation/placement_losses.csv"
)
SECOND_PLACEMENTS = (
    ROOT / "results/development_v11/second_confirmation/scoring/placement_losses.csv"
)
FIRST_ARCHIVED = (
    ROOT
    / "results/development_v11/reviewer_completion/confirmation_empirical_fit_losses.csv"
)
SECOND_ARCHIVED = (
    ROOT / "results/revision_v12/t02_support_hierarchy/agent_a/second_fit_losses.csv"
)
NEW_GAPS = (14, 60)
PROBE_GAPS = (7, 30, 90, 180)
N_WORKERS = 8


def _daily_path(network_id: str, daily_dir: Path) -> Path:
    """Panel file for a network; second-panel networks may live in the
    confirmation (first-panel) daily directory (rev_v12 convention)."""
    direct = daily_dir / network_id / "daily_wide_temperature.csv"
    if direct.is_file():
        return direct
    fallback = FIRST_DAILY / network_id / "daily_wide_temperature.csv"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"no temperature panel for {network_id}")


def _run_network(args: tuple) -> pd.DataFrame:
    network_id, panel_dir, placements, gaps = args
    panel = read_temperature_panel(str(_daily_path(network_id, panel_dir)))
    return fitting_period_empirical_losses(
        network_id, panel, placements, gaps=gaps, xgboost_parameters=XGBOOST_PARAMETERS
    )


def _run_panel(
    placements: pd.DataFrame,
    daily_dir: Path,
    networks: list[str],
    gaps: tuple[int, ...],
    label: str,
) -> pd.DataFrame:
    tasks = [
        (net, daily_dir, placements.loc[placements["network_id"].eq(net)], gaps)
        for net in networks
    ]
    started = time.time()
    with ProcessPoolExecutor(max_workers=N_WORKERS) as pool:
        parts = list(pool.map(_run_network, tasks, chunksize=1))
    frame = pd.concat(parts, ignore_index=True)
    print(
        f"[{label}] {len(frame)} rows at gaps {gaps} over {len(networks)} "
        f"networks in {time.time() - started:.0f}s",
        flush=True,
    )
    return frame


def _assert_probe(
    placements: pd.DataFrame, archived: pd.DataFrame, label: str
) -> None:
    pass  # superseded by _assert_probe_one (probe nets per panel)


def main() -> None:
    # Station IDs may carry leading zeros (e.g. USGS 01425000); all inputs
    # must be read as strings or the ids are corrupted at the int round-trip.
    str_dtype = {"network_id": str, "station_id": str}
    first_place = pd.read_csv(FIRST_PLACEMENTS, dtype=str_dtype)
    second_place = pd.read_csv(SECOND_PLACEMENTS, dtype=str_dtype)
    first_arch = pd.read_csv(FIRST_ARCHIVED, dtype=str_dtype)
    second_arch = pd.read_csv(SECOND_ARCHIVED, dtype=str_dtype)

    # Determinism probes against the archived four-duration frames.
    for places, arch, daily, label in (
        (first_place, first_arch, FIRST_DAILY, "first"),
        (second_place, second_arch, SECOND_DAILY, "second"),
    ):
        probe_nets = []
        for n in sorted(arch["network_id"].unique()):
            try:
                if _daily_path(n, daily).is_file():
                    probe_nets.append(n)
                    break
            except FileNotFoundError:
                continue
        _assert_probe_one(places, arch, daily, probe_nets, label)

    # Full 14/60-d cuts.
    first_nets = sorted(first_place["network_id"].unique())
    second_nets = sorted(second_place["network_id"].unique())
    cuts_first = _run_panel(first_place, FIRST_DAILY, first_nets, NEW_GAPS, "first")
    cuts_second = _run_panel(second_place, SECOND_DAILY, second_nets, NEW_GAPS, "second")
    for cuts in (cuts_first, cuts_second):
        cuts["gap_start"] = pd.to_datetime(
            cuts["gap_start"], format="mixed"
        ).dt.strftime("%Y-%m-%d")
    cuts_first.to_csv(OUTPUT / "fitting_cuts_14_60_first.csv", index=False)
    cuts_second.to_csv(OUTPUT / "fitting_cuts_14_60_second.csv", index=False)

    ext_first = pd.concat([first_arch, cuts_first], ignore_index=True)
    ext_second = pd.concat([second_arch, cuts_second], ignore_index=True)
    sort_cols = ["network_id", "station_id", "gap_length", "season", "placement"]
    for ext, arch, label in (
        (ext_first, first_arch, "first"),
        (ext_second, second_arch, "second"),
    ):
        ext = ext.sort_values(sort_cols, ignore_index=True)
        old_rows = ext.loc[ext["gap_length"].isin(PROBE_GAPS)].reset_index(drop=True)
        arch_sorted = arch.sort_values(sort_cols, ignore_index=True).reset_index(
            drop=True
        )
        if len(old_rows) != len(arch_sorted):
            raise SystemExit(
                f"integrity {label}: {len(old_rows)} archived rows in extended "
                f"!= {len(arch_sorted)} archived rows"
            )
        key = ["network_id", "station_id", "gap_length", "season", "placement"]
        merged = old_rows.merge(arch_sorted, on=key, suffixes=("", "_a"))
        if len(merged) != len(arch_sorted):
            raise SystemExit(
                f"integrity {label}: geometry merge 1:1 failed "
                f"({len(merged)}/{len(arch_sorted)}) - leading-zero station "
                "ids corrupted"
            )
        delta = (merged["mae_deg_c"] - merged["mae_deg_c_a"]).abs()
        if delta.max() > 1e-12:
            raise SystemExit(
                f"integrity {label}: archived rows changed "
                f"(max |dMAE| {delta.max():.2e})"
            )
        print(
            f"[integrity] {label}: {len(arch_sorted)} archived rows preserved "
            f"bit-for-bit in the extended frame (max |dMAE| {delta.max():.1e})",
            flush=True,
        )
    ext_first = ext_first.sort_values(sort_cols, ignore_index=True)
    ext_second = ext_second.sort_values(sort_cols, ignore_index=True)
    ext_first.to_csv(OUTPUT / "fit_losses_extended_first.csv", index=False)
    ext_second.to_csv(OUTPUT / "fit_losses_extended_second.csv", index=False)
    print(
        "wrote fitting_cuts_14_60_{first,second}.csv and "
        "fit_losses_extended_{first,second}.csv"
    )
    print("extended first gaps:", ext_first.groupby("gap_length").size().to_dict())
    print("extended second gaps:", ext_second.groupby("gap_length").size().to_dict())


def _assert_probe_one(
    placements: pd.DataFrame,
    archived: pd.DataFrame,
    daily: Path,
    nets: list[str],
    label: str,
) -> None:
    for net in nets:
        panel = read_temperature_panel(str(_daily_path(net, daily)))
        sub = placements.loc[placements["network_id"].eq(net)]
        rows = fitting_period_empirical_losses(
            net, panel, sub, gaps=PROBE_GAPS, xgboost_parameters=XGBOOST_PARAMETERS
        )
        arch = archived.loc[archived["network_id"].eq(net)]
        key = ["station_id", "gap_length", "season", "placement"]
        merged = rows.merge(arch, on=key, suffixes=("", "_a"))
        if len(merged) != len(arch) or len(rows) != len(arch):
            raise SystemExit(
                f"probe {label}/{net}: rerun {len(rows)} vs archived "
                f"{len(arch)} rows, merged {len(merged)}"
            )
        delta = (merged["mae_deg_c"] - merged["mae_deg_c_a"]).abs()
        same_start = (
            merged["gap_start"].astype(str).str[:10]
            == merged["gap_start_a"].astype(str).str[:10]
        ).all()
        if delta.max() > 1e-12 or not same_start:
            raise SystemExit(
                f"probe {label}/{net}: nondeterministic rerun "
                f"(max |dMAE| = {delta.max():.2e}, starts equal {same_start})"
            )
        print(
            f"[probe] {label}/{net}: {len(rows)} archived rows reproduced "
            f"bit-for-bit (max |dMAE| = {delta.max():.1e})",
            flush=True,
        )


if __name__ == "__main__":
    main()
