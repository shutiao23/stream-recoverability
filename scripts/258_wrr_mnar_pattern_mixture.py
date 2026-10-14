#!/usr/bin/env python3
"""P1-01: pattern-mixture sensitivity of the screening contrast to hidden bias.

The designed-outage comparison treats the transplanted mask as ignorable: the
missing days are assumed exchangeable with the observed ones. That assumption is
not testable on the real records, so this script asks the decision-relevant
question instead: how large a bias in the *hidden* days would be needed to erase
the screening advantage?

AUDIT NOTE (F06 / 2026-10-13). The historical implementation below applies
``abs(signed_error + δ × true_peak_hidden_fraction)`` and does **not** modify
daily completions or re-seek the rolling peak. Outputs are retained only as an
exploratory approximation under
``amendments/mnar_pattern_mixture/`` and must not be written into conclusions.
Day-level recomputation lives in ``scripts/271_wrr_mnar_day_level.py``.

Writes results/wrr_submission_ready/amendments/mnar_pattern_mixture/.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "mnar_pattern_mixture"
RETENTION = 0.70
TOLERANCE_C = 0.5
BIASES = (-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0)


def load_populations() -> dict[str, tuple[pd.DataFrame, pd.DataFrame]]:
    from stream_recoverability.experiments.v17_fitness.frontier import screening_scores

    pops: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    dev = pd.read_parquet(ROOT / "results/v17_fitness/step4_ceiling/development_cases.parquet").reset_index(
        drop=True
    )
    dev_cert = pd.read_parquet(
        ROOT / "results/v17_fitness/step6_screen/development_certificates.parquet"
    ).reset_index(drop=True)
    pops["development"] = (dev, dev_cert)
    res = pd.read_parquet(
        ROOT / "results/v17_fitness/step10_confirmation/reserved_cases.parquet"
    ).reset_index(drop=True)
    res_cert = pd.read_parquet(
        ROOT / "results/v17_fitness/step10_confirmation/reserved_certificates.parquet"
    ).reset_index(drop=True)
    pops["reserved_retrospective"] = (res, res_cert)
    sealed = pd.read_parquet(READY / "p0_07_sealed_confirmation/sealed_cases.parquet").reset_index(drop=True)
    sealed_cert = pd.read_parquet(
        READY / "p0_07_sealed_confirmation/sealed_certificates.parquet"
    ).reset_index(drop=True)
    pops["sealed_usgs"] = (sealed, sealed_cert)
    return pops


def frame_for(cases: pd.DataFrame, certificates: pd.DataFrame) -> pd.DataFrame:
    """Per-case errors for both rules under the same reconstruction choice."""

    from stream_recoverability.experiments.v17_fitness.policies import gather

    cases = cases.reset_index(drop=True)
    certificates = certificates.reset_index(drop=True)
    choice = certificates["certificate_choice"]
    frame = pd.DataFrame(
        {
            "network_id": cases["network_id"].astype(str),
            "cert_bound": pd.to_numeric(certificates["certificate_bound"], errors="coerce"),
            "error": pd.Series(gather(cases, choice, prefix="err_")),
            "hidden_share": pd.to_numeric(cases["true_peak_hidden_fraction"], errors="coerce"),
        }
    )
    rng = np.random.default_rng(0)
    frame["length"] = pd.to_numeric(cases["longest_run"], errors="coerce") + rng.random(len(cases))
    return frame.dropna(subset=["cert_bound", "error", "hidden_share", "length"])


def rate_gap(frame: pd.DataFrame, delta: float) -> dict:
    biased = (frame["error"] + delta * frame["hidden_share"]).abs()
    k = max(1, int(round(RETENTION * len(frame))))
    cert_keep = frame["cert_bound"].nsmallest(k).index
    length_keep = frame["length"].nsmallest(k).index
    cert_rate = float((biased.loc[cert_keep] > TOLERANCE_C).mean())
    length_rate = float((biased.loc[length_keep] > TOLERANCE_C).mean())
    # Sign convention matches the rest of the paper: certificate minus length,
    # so a negative contrast means the screen has the lower consequential-error rate.
    return {"certificate_rate": cert_rate, "length_rate": length_rate, "contrast_points": (cert_rate - length_rate) * 100}


def clustered(frame: pd.DataFrame, delta: float, draws: int = 1000, seed: int = 0) -> dict:
    """Network-clustered bootstrap, vectorised over precomputed index blocks."""

    work = frame.reset_index(drop=True)
    codes, _ = pd.factorize(work["network_id"])
    order = np.argsort(codes, kind="mergesort")
    codes_sorted = codes[order]
    boundaries = np.searchsorted(codes_sorted, np.arange(codes.max() + 1), side="left")
    ends = np.append(boundaries[1:], len(codes_sorted))
    blocks = [order[start:end] for start, end in zip(boundaries, ends)]
    cert_bound = work["cert_bound"].to_numpy(dtype=float)
    error = work["error"].to_numpy(dtype=float)
    hidden = work["hidden_share"].to_numpy(dtype=float)
    length = work["length"].to_numpy(dtype=float)
    biased = np.abs(error + delta * hidden)

    rng = np.random.default_rng(seed)
    values = np.empty(draws, dtype=float)
    for draw in range(draws):
        picked = rng.integers(0, len(blocks), size=len(blocks))
        index = np.concatenate([blocks[i] for i in picked])
        k = max(1, int(round(RETENTION * len(index))))
        cert_keep = index[np.argpartition(cert_bound[index], k - 1)[:k]]
        length_keep = index[np.argpartition(length[index], k - 1)[:k]]
        cert_rate = float((biased[cert_keep] > TOLERANCE_C).mean())
        length_rate = float((biased[length_keep] > TOLERANCE_C).mean())
        values[draw] = (cert_rate - length_rate) * 100
    return {
        "low": float(np.nanpercentile(values, 2.5)),
        "high": float(np.nanpercentile(values, 97.5)),
        "draws": int(draws),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    payload: dict[str, object] = {
        "model": (
            "APPROXIMATION ONLY (F06): abs(signed_error + delta * true_peak_hidden_fraction); "
            "does not perturb daily fills or re-seek the hottest window. "
            "Not an MNAR identification bound. Use scripts/271_wrr_mnar_day_level.py."
        ),
        "claim_status": "executed_audit_failed",
        "may_enter_abstract_or_conclusions": False,
        "retention": RETENTION,
        "tolerance_c": TOLERANCE_C,
        "populations": {},
    }
    for name, (cases, certificates) in load_populations().items():
        frame = frame_for(cases, certificates)
        entries = []
        for delta in BIASES:
            result = rate_gap(frame, delta)
            result["delta_c"] = delta
            if delta in (-1.0, -0.5, 0.0, 0.5, 1.0):
                result["contrast_ci"] = clustered(frame, delta)
            entries.append(result)
            rows.append({"population": name, **result})
        zero = next(e for e in entries if e["delta_c"] == 0.0)
        flip = None
        for entry in entries:
            if entry["delta_c"] > 0 and entry["contrast_points"] >= 0:
                flip = entry["delta_c"]
                break
        payload["populations"][name] = {
            "n_cases": int(len(frame)),
            "n_networks": int(frame["network_id"].nunique()),
            "mean_hidden_share": float(frame["hidden_share"].mean()),
            "delta_zero_contrast_points": zero["contrast_points"],
            "first_positive_bias_that_erases_the_advantage_c": flip,
            "sign_convention": "certificate rate minus length rate; negative favours the screen",
            "curve": entries,
        }
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "bias_curve.csv", index=False)
    (OUT / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
