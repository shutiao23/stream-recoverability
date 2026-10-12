"""Step 2 diagnostic: remaining headroom of strong simple methods on the trusted panel.

This recomputes existing frozen-replay strategies on river complete calendar
years. It does not retrain recoverers. The 846-case opened confirmation subset
is tagged retrospective and is not a new unseen test.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from stream_recoverability.experiments.wrr_revision.paths import (
    RESULTS_ROOT,
    STEP2_HEADROOM,
)

STRATEGIES = (
    "all_default",
    "seasonal_le30",
    "always_donor_gated",
    "always_switch_gated",
    "frozen_rule",
)
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_SEED = 20260907


def _load_replay(folder: str, panel: str) -> pd.DataFrame:
    path = RESULTS_ROOT / folder / "station_year_replay.csv"
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path, dtype={"station_id": str, "network_id": str})
    frame["year"] = frame["year"].astype(int)
    frame["replay_panel"] = panel
    return frame


def load_existing_replay() -> pd.DataFrame:
    parts = [
        _load_replay("step6_frozen_replay", "development"),
        _load_replay("step8_frozen_replay", "confirmation"),
    ]
    parts = [frame for frame in parts if not frame.empty]
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


def attach_roster(replay: pd.DataFrame, roster: pd.DataFrame) -> pd.DataFrame:
    keys = ["network_id", "station_id", "year"]
    keep = keys + [
        "waterbody_family",
        "waterbody_class",
        "full_calendar_year",
        "year_ended",
        "eligible_annual_truth",
        "evidence_use",
        "opened_in_review_20260907",
        "v16_role",
        "n_donors_any",
        "exclusion_reason",
    ]
    keep = [col for col in keep if col in roster.columns]
    merged = replay.merge(roster[keep], on=keys, how="left")
    merged["eligible_annual_truth"] = merged["eligible_annual_truth"].fillna(False).astype(bool)
    return merged


def oracle_gated_donor(benefit: pd.Series) -> pd.Series:
    """Undeployable oracle on {default, gated donor-only}: keep the better of B and 0.

    When the stored benefit is zero because the gate rejected, the counterfactual
    adopt-anyway benefit is not in the existing table, so this understates the
    unrestricted adopt/default oracle.
    """

    values = pd.to_numeric(benefit, errors="coerce")
    return values.clip(lower=0.0)


def subset_frames(merged: pd.DataFrame) -> dict[str, pd.DataFrame]:
    valid = merged.dropna(subset=["always_donor_gated_hottest_30", "frozen_rule_hottest_30"])
    return {
        "development_all_existing": valid.loc[valid["replay_panel"].eq("development")],
        "confirmation_all_existing": valid.loc[valid["replay_panel"].eq("confirmation")],
        "development_river_complete_years": valid.loc[
            valid["replay_panel"].eq("development") & valid["eligible_annual_truth"]
        ],
        "retrospective_confirmation_river_complete_years": valid.loc[
            valid["replay_panel"].eq("confirmation") & valid["eligible_annual_truth"]
        ],
        "retrospective_confirmation_opened_846_like": valid.loc[
            valid["replay_panel"].eq("confirmation")
            & valid["opened_in_review_20260907"]
        ],
    }


def _network_means(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return frame.groupby("network_id")[columns].mean()


def summarise_subset(name: str, frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    comparisons: list[dict[str, object]] = []
    if frame.empty:
        return pd.DataFrame(), pd.DataFrame()
    work = frame.copy()
    work["oracle_gated_donor_hottest_30"] = oracle_gated_donor(work["always_donor_gated_hottest_30"])
    work["headroom_oracle_minus_donor"] = (
        work["oracle_gated_donor_hottest_30"] - work["always_donor_gated_hottest_30"]
    )
    columns = [f"{name}_hottest_30" for name in STRATEGIES] + [
        "oracle_gated_donor_hottest_30",
        "headroom_oracle_minus_donor",
    ]
    adopt_cols = {
        "all_default": "all_default_adopt_rate",
        "seasonal_le30": "seasonal_le30_adopt_rate",
        "always_donor_gated": "always_donor_gated_adopt_rate",
        "always_switch_gated": "always_switch_gated_adopt_rate",
        "frozen_rule": "frozen_rule_adopt_rate",
    }
    net = _network_means(work, columns)
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.integers(0, len(net), (BOOTSTRAP_REPLICATES, len(net))) if len(net) else None
    labels = list(STRATEGIES) + ["oracle_gated_donor", "headroom_oracle_minus_donor"]
    for label, col in zip(labels, columns):
        case_mean = float(work[col].mean())
        network_mean = float(net[col].mean()) if len(net) else float("nan")
        if draws is None:
            ci = (float("nan"), float("nan"))
        else:
            ci = tuple(np.quantile(net[col].to_numpy()[draws].mean(axis=1), [0.025, 0.975]))
        harm = work[col].lt(-1e-10) if label != "headroom_oracle_minus_donor" else pd.Series(False, index=work.index)
        adopt_col = adopt_cols.get(label)
        rows.append(
            {
                "subset": name,
                "strategy": label,
                "n_cases": int(len(work)),
                "n_networks": int(work["network_id"].nunique()),
                "n_stations": int(work["station_id"].nunique()),
                "n_station_years": int(work[["network_id", "station_id", "year"]].drop_duplicates().shape[0]),
                "case_mean_hottest_30": case_mean,
                "network_mean_hottest_30": network_mean,
                "network_ci_low": float(ci[0]),
                "network_ci_high": float(ci[1]),
                "harm_rate": float(harm.mean()) if label != "headroom_oracle_minus_donor" else float("nan"),
                "severe_harm_below_minus1C": (
                    int(work[col].lt(-1.0).sum())
                    if label not in {"headroom_oracle_minus_donor", "oracle_gated_donor"}
                    else float("nan")
                ),
                "mean_adopt_rate": float(work[adopt_col].mean()) if adopt_col and adopt_col in work.columns else float("nan"),
            }
        )
    donor = "always_donor_gated_hottest_30"
    for comparator in ("frozen_rule", "always_switch_gated", "seasonal_le30", "oracle_gated_donor"):
        left = "frozen_rule_hottest_30" if comparator == "frozen_rule" else f"{comparator}_hottest_30"
        if comparator == "oracle_gated_donor":
            left = "oracle_gated_donor_hottest_30"
            diff = net[left] - net[donor]
            case_diff = work[left] - work[donor]
            label = "oracle_gated_donor_minus_always_donor"
        else:
            diff = net["frozen_rule_hottest_30"] - net[donor] if comparator == "frozen_rule" else net[left] - net[donor]
            case_diff = (
                work["frozen_rule_hottest_30"] - work[donor]
                if comparator == "frozen_rule"
                else work[left] - work[donor]
            )
            label = f"{comparator}_minus_always_donor"
        if draws is None:
            ci = (float("nan"), float("nan"))
        else:
            ci = tuple(np.quantile(diff.to_numpy()[draws].mean(axis=1), [0.025, 0.975]))
        comparisons.append(
            {
                "subset": name,
                "contrast": label,
                "case_mean_difference": float(case_diff.mean()),
                "network_mean_difference": float(diff.mean()),
                "network_ci_low": float(ci[0]),
                "network_ci_high": float(ci[1]),
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(comparisons)


def run_headroom(roster: pd.DataFrame) -> dict[str, pd.DataFrame | dict]:
    replay = load_existing_replay()
    if replay.empty or roster.empty:
        return {
            "joined": pd.DataFrame(),
            "means": pd.DataFrame(),
            "comparisons": pd.DataFrame(),
            "summary": {"status": "missing_replay_or_roster"},
        }
    joined = attach_roster(replay, roster)
    mean_parts = []
    comparison_parts = []
    subset_counts = {}
    for name, frame in subset_frames(joined).items():
        subset_counts[name] = {
            "n_cases": int(len(frame)),
            "n_networks": int(frame["network_id"].nunique()) if not frame.empty else 0,
            "n_station_years": int(frame[["network_id", "station_id", "year"]].drop_duplicates().shape[0])
            if not frame.empty
            else 0,
        }
        means, comparisons = summarise_subset(name, frame)
        if not means.empty:
            mean_parts.append(means)
        if not comparisons.empty:
            comparison_parts.append(comparisons)
    means = pd.concat(mean_parts, ignore_index=True) if mean_parts else pd.DataFrame()
    comparisons = pd.concat(comparison_parts, ignore_index=True) if comparison_parts else pd.DataFrame()
    summary = {
        "status": "diagnostic_on_existing_replay",
        "not_a_new_confirmation": True,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "seed": BOOTSTRAP_SEED,
        "oracle_definition": "max(gated_donor_benefit, 0); undeployable; understates unrestricted adopt/default when gates reject",
        "subsets": subset_counts,
        "smooth_climatology_not_in_existing_replay": True,
        "historically_chosen_best_fixed_is_duration_switch_in_freeze": True,
    }
    return {
        "joined": joined,
        "means": means,
        "comparisons": comparisons,
        "summary": summary,
    }


def write_headroom(bundle: dict[str, pd.DataFrame | dict], directory: Path = STEP2_HEADROOM) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    means = bundle["means"]
    comparisons = bundle["comparisons"]
    summary = bundle["summary"]
    assert isinstance(means, pd.DataFrame)
    assert isinstance(comparisons, pd.DataFrame)
    assert isinstance(summary, dict)
    means.to_csv(directory / "simple_method_means.csv", index=False)
    comparisons.to_csv(directory / "paired_vs_donor.csv", index=False)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2))
    (directory / "REPORT.md").write_text(_headroom_report(summary, means, comparisons))
    return directory


def _headroom_report(summary: dict, means: pd.DataFrame, comparisons: pd.DataFrame) -> str:
    lines = [
        "# Step 2 — strong simple methods on the trusted river complete-year panel",
        "",
        "Existing frozen replay, no retraining. Opened confirmation years are retrospective.",
        "Oracle = max(gated donor-only benefit, 0) and is not deployable.",
        "",
        json.dumps(summary.get("subsets", {}), indent=2),
        "",
        "## Network-equal means",
        "",
        means.to_string(index=False) if not means.empty else "(none)",
        "",
        "## Paired contrasts versus gated donor-only",
        "",
        comparisons.to_string(index=False) if not comparisons.empty else "(none)",
        "",
    ]
    return "\n".join(lines)
