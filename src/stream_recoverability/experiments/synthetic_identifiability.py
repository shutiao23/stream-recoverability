"""E0: recover true information order on known synthetic river graphs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from stream_recoverability.analysis.heuristic_degeneration import (
    degeneration_bound,
    donor_count_inflation,
    in_sample_r2,
    jensen_acf_gap,
    year_block_cv_r2,
)
from stream_recoverability.analysis.recoverability_spectrum import (
    IncrementalValue,
    spectrum_from_var1,
)
from stream_recoverability.experiments.synthetic_river import (
    SyntheticRiver,
    catalog,
    high_donor_and_high_memory_river,
    nonstationary_release_river,
    simulate_var1,
)

DEFAULT_GAPS = (14, 30, 90)


def contemporaneous_donor_r2(
    river: SyntheticRiver,
    *,
    target: int | None = None,
    donors: Sequence[int] | None = None,
) -> float:
    """Exact contemporaneous donor R^2 from known Sigma."""

    focus = river.target if target is None else int(target)
    donor_index = list(river.donors if donors is None else donors)
    variance = float(river.sigma[focus, focus])
    if variance <= 0:
        return float("nan")
    if not donor_index:
        return 0.0
    sigma_dd = river.sigma[np.ix_(donor_index, donor_index)]
    sigma_td = river.sigma[focus, donor_index]
    try:
        explained = float(sigma_td @ np.linalg.solve(sigma_dd, sigma_td))
    except np.linalg.LinAlgError:
        explained = float(sigma_td @ np.linalg.pinv(sigma_dd) @ sigma_td)
    return float(np.clip(explained / variance, 0.0, 1.0))


def _true_contemporaneous_r2(river: SyntheticRiver) -> float:
    return contemporaneous_donor_r2(river)


def evaluate_river(
    river: SyntheticRiver,
    *,
    gap_lengths: Sequence[int] = DEFAULT_GAPS,
) -> pd.DataFrame:
    donor_r2 = _true_contemporaneous_r2(river)
    rows = []
    for gap in gap_lengths:
        spectrum = spectrum_from_var1(
            river.transition,
            river.sigma,
            target=river.target,
            donors=river.donors,
            gap_length=int(gap),
        )
        rows.append(
            {
                "river": river.name,
                "regime": river.regime,
                "gap_length": int(gap),
                "n_donors": len(river.donors),
                "true_donor_r2": donor_r2,
                "heuristic_forced_donor": donor_r2 >= 0.5,
                **spectrum.as_dict(),
                "notes": river.notes,
            }
        )
    return pd.DataFrame(rows)


def expected_sign(regime: str) -> str | None:
    return {
        "memory": "boundary_dominant",
        "donor": "donor_dominant",
        "endpoint": None,
        "mixed": None,
        "redundant_donors": "donor_dominant",
        "chain": None,
        "shifted": None,
    }.get(regime)


def identifiability_report(
    rivers: Mapping[str, SyntheticRiver] | None = None,
    *,
    gap_lengths: Sequence[int] = DEFAULT_GAPS,
) -> pd.DataFrame:
    inventory = catalog() if rivers is None else dict(rivers)
    frames = [evaluate_river(river, gap_lengths=gap_lengths) for river in inventory.values()]
    table = pd.concat(frames, ignore_index=True)
    table["expected_sign"] = table["regime"].map(expected_sign)
    table["sign_recovered"] = [
        expected is None or sign == expected
        for expected, sign in zip(table["expected_sign"], table["sign"], strict=True)
    ]
    return table


def heuristic_degeneration_exhibits() -> dict[str, pd.DataFrame | dict[str, float | bool]]:
    mixed = high_donor_and_high_memory_river()
    donor_r2 = _true_contemporaneous_r2(mixed)
    return {
        "forced_label_theorem": degeneration_bound(0.5),
        "mixed_river_donor_r2": {
            "true_donor_r2": donor_r2,
            "forced_donor_dominated": donor_r2 >= 0.5,
        },
        "jensen_ar1": pd.DataFrame(
            [
                jensen_acf_gap(phi, gap)
                for phi in (0.4, 0.7, 0.9)
                for gap in (30, 90, 180)
            ]
        ),
        "donor_count_inflation": donor_count_inflation(),
    }


def finite_sample_recovery(
    river: SyntheticRiver,
    *,
    n_time: int = 365 * 4,
    gap_length: int = 30,
    seed: int = 0,
) -> dict[str, float | str]:
    """Compare the exact operator with a series-estimated operator."""

    from stream_recoverability.analysis.conditional_observability import (
        empirical_information_set_conditionals,
    )
    from stream_recoverability.analysis.recoverability_spectrum import (
        spectrum_from_conditionals,
    )

    truth = spectrum_from_var1(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=gap_length,
    )
    series = simulate_var1(river, n_time, seed=seed)
    estimated = spectrum_from_conditionals(
        empirical_information_set_conditionals(
            series,
            target=river.target,
            donors=river.donors,
            gap_length=gap_length,
        )
    )
    return {
        "river": river.name,
        "true_tau": truth.tau,
        "estimated_tau": estimated.tau,
        "tau_error": estimated.tau - truth.tau,
        "true_sign": truth.sign,
        "estimated_sign": estimated.sign,
        "sign_match": truth.sign == estimated.sign,
    }


def uncertainty_coverage(
    river: SyntheticRiver,
    *,
    n_time: int = 365 * 8,
    n_years: int = 8,
    gap_length: int = 30,
    n_boot: int = 80,
    n_replicates: int = 12,
    seed: int = 1,
) -> dict[str, float]:
    """Monte Carlo coverage of the year-block bootstrap for \(\tau\)."""

    from stream_recoverability.analysis.recoverability_spectrum import (
        year_block_bootstrap_tau,
    )

    truth = spectrum_from_var1(
        river.transition,
        river.sigma,
        target=river.target,
        donors=river.donors,
        gap_length=gap_length,
    )
    years = np.repeat(np.arange(n_years), n_time // n_years + 1)[:n_time]
    covered = 0
    defined = 0
    rng = np.random.default_rng(seed)
    for replicate in range(n_replicates):
        series = simulate_var1(river, n_time, seed=int(rng.integers(0, 1_000_000)))
        interval = year_block_bootstrap_tau(
            series,
            years,
            target=river.target,
            donors=river.donors,
            gap_length=gap_length,
            n_boot=n_boot,
            seed=replicate,
        )
        if not np.isfinite(interval["tau_ci_lower"]):
            continue
        defined += 1
        if interval["tau_ci_lower"] <= truth.tau <= interval["tau_ci_upper"]:
            covered += 1
    return {
        "true_tau": truth.tau,
        "n_replicates": float(n_replicates),
        "n_defined_intervals": float(defined),
        "coverage": float("nan") if defined == 0 else covered / defined,
    }


def state_shift_mismatch() -> dict[str, IncrementalValue]:
    pre, post = nonstationary_release_river()
    return {
        "pre": spectrum_from_var1(
            pre.transition, pre.sigma, target=pre.target, donors=pre.donors, gap_length=90
        ),
        "post": spectrum_from_var1(
            post.transition,
            post.sigma,
            target=post.target,
            donors=post.donors,
            gap_length=90,
        ),
    }


def sampled_r2_comparison(
    river: SyntheticRiver,
    *,
    n_time: int = 365 * 8,
    n_years: int = 8,
    seed: int = 0,
) -> dict[str, float]:
    series = simulate_var1(river, n_time, seed=seed)
    target = series[:, river.target]
    donors = [series[:, index] for index in river.donors]
    years = np.repeat(np.arange(n_years), n_time // n_years + 1)[:n_time]
    return {
        "true_donor_r2": _true_contemporaneous_r2(river),
        "in_sample_r2": in_sample_r2(target, donors),
        "year_block_cv_r2": year_block_cv_r2(target, donors, years),
    }


def run_e0(*, include_coverage: bool = False) -> dict[str, pd.DataFrame | dict]:
    rivers = catalog()
    report = identifiability_report(rivers)
    exhibits = heuristic_degeneration_exhibits()
    sample = pd.DataFrame(
        [
            finite_sample_recovery(rivers["memory_dominant"]),
            finite_sample_recovery(rivers["donor_dominant"]),
            finite_sample_recovery(rivers["high_donor_and_high_memory"]),
        ]
    )
    shift = state_shift_mismatch()
    result: dict[str, pd.DataFrame | dict] = {
        "identifiability": report,
        "finite_sample": sample,
        "degeneration": exhibits,
        "state_shift": {
            "pre_tau": shift["pre"].tau,
            "post_tau": shift["post"].tau,
            "pre_sign": shift["pre"].sign,
            "post_sign": shift["post"].sign,
            "sign_changes": shift["pre"].sign != shift["post"].sign,
        },
        "r2_comparison": sampled_r2_comparison(rivers["high_donor_and_high_memory"]),
        "pass": {
            "memory_sign": bool(
                report.loc[
                    report["river"].eq("memory_dominant"), "sign_recovered"
                ].all()
            ),
            "donor_sign": bool(
                report.loc[report["river"].eq("donor_dominant"), "sign_recovered"].all()
            ),
            "heuristic_forced_on_mixed": bool(
                report.loc[
                    report["river"].eq("high_donor_and_high_memory"),
                    "heuristic_forced_donor",
                ].all()
            ),
            "jensen_nonzero": bool(
                (exhibits["jensen_ar1"]["jensen_gap"].abs() > 1e-6).any()
            ),
        },
    }
    if include_coverage:
        result["coverage"] = uncertainty_coverage(rivers["memory_dominant"])
    return result


__all__ = [
    "contemporaneous_donor_r2",
    "evaluate_river",
    "finite_sample_recovery",
    "heuristic_degeneration_exhibits",
    "identifiability_report",
    "run_e0",
    "sampled_r2_comparison",
    "state_shift_mismatch",
    "uncertainty_coverage",
]
