#!/usr/bin/env python3
"""P0-03 deliverable: full-denominator retention / success / abstain / failure table."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "p0_03_retention_denominator"
RETENTION = 0.7
TOLERANCE = 0.5


def _panel_table(name: str, cases_path: Path, cert_path: Path) -> dict:
    import numpy as np
    import pandas as pd

    cases = pd.read_parquet(cases_path)
    certs = pd.read_parquet(cert_path)
    n = len(cases)
    cert_err = pd.to_numeric(certs["certificate_abs_error"], errors="coerce").to_numpy(dtype=float)
    policy_err = pd.to_numeric(cases["abserr_policy"], errors="coerce").to_numpy(dtype=float)
    bound = pd.to_numeric(certs["certificate_bound"], errors="coerce").to_numpy(dtype=float)
    choice = certs["certificate_choice"].astype(str).to_numpy()

    k = max(1, int(round(RETENTION * n)))
    order = np.argsort(np.where(np.isfinite(bound), bound, np.inf), kind="mergesort")
    selected = order[:k]
    sel_err = cert_err[selected]
    sel_policy = policy_err[selected]

    success = np.isfinite(sel_err)
    fail_recon = ~np.isfinite(sel_err)
    consequential = success & (sel_err > TOLERANCE)
    ok = success & (sel_err <= TOLERANCE)

    # Old (buggy) denominator after dropna
    both_finite = np.isfinite(cert_err) & np.isfinite(policy_err)
    n_old = int(both_finite.sum())
    old_retention_share = (RETENTION * n_old / n) if n else float("nan")

    return {
        "panel": name,
        "n_candidate_cases": n,
        "n_cert_error_finite": int(np.isfinite(cert_err).sum()),
        "n_cert_reconstruction_failures": int((~np.isfinite(cert_err)).sum()),
        "n_donor_ridge_choices": int((choice == "donor_ridge").sum()),
        "n_donor_ridge_nan_error": int(((choice == "donor_ridge") & ~np.isfinite(cert_err)).sum()),
        "target_retention": RETENTION,
        "k_selected_full_denominator": k,
        "selected_success_recon": int(success.sum()),
        "selected_recon_failure": int(fail_recon.sum()),
        "selected_consequential_error": int(consequential.sum()),
        "selected_ok_within_tolerance": int(ok.sum()),
        "failure_rate_full_denom_selected": float((fail_recon | consequential).mean()),
        "actual_retention_if_dropna_first": float(old_retention_share),
        "old_dropna_n": n_old,
        "policy_selected_failure_rate": float(
            ((~np.isfinite(sel_policy)) | (sel_policy > TOLERANCE)).mean()
        ),
    }


def main() -> int:
    import pandas as pd

    OUT.mkdir(parents=True, exist_ok=True)
    panels = [
        (
            "sealed_usgs",
            READY / "p0_07_sealed_confirmation" / "sealed_cases.parquet",
            READY / "p0_07_sealed_confirmation" / "sealed_certificates.parquet",
        ),
        (
            "transport_extended",
            READY / "p0_07b_multi_agency_transport" / "transport_cases.parquet",
            READY / "p0_07b_multi_agency_transport" / "transport_certificates.parquet",
        ),
    ]
    rows = []
    for name, cases_path, cert_path in panels:
        if cases_path.is_file() and cert_path.is_file():
            rows.append(_panel_table(name, cases_path, cert_path))

    # Primary transport subset if manifest roles available
    manifest_path = READY / "multi_agency_inputs_manifest.csv"
    if manifest_path.is_file() and rows:
        import numpy as np

        manifest = pd.read_csv(manifest_path)
        if "panel_role" in manifest.columns and "network_id" in manifest.columns:
            cases = pd.read_parquet(panels[1][1])
            certs = pd.read_parquet(panels[1][2])
            roles = manifest.set_index("network_id")["panel_role"].astype(str)
            primary = cases["network_id"].map(roles).eq("primary_new_agency")
            if primary.any():
                tmp_cases = OUT / "_primary_cases.parquet"
                tmp_certs = OUT / "_primary_certs.parquet"
                cases.loc[primary].reset_index(drop=True).to_parquet(tmp_cases)
                certs.loc[primary.to_numpy()].reset_index(drop=True).to_parquet(tmp_certs)
                rows.append(_panel_table("transport_primary", tmp_cases, tmp_certs))
                tmp_cases.unlink(missing_ok=True)
                tmp_certs.unlink(missing_ok=True)

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "retention_denominator_table.csv", index=False)
    summary = {
        "tolerance_C": TOLERANCE,
        "retention_target": RETENTION,
        "rule": (
            "k = round(0.7 * n_full). Non-finite selected certificate errors count as "
            "failures, not silent drops. Actual retention after historical dropna is "
            "reported for diagnosis only."
        ),
        "panels": rows,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(table.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
