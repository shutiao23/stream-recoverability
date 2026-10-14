#!/usr/bin/env python3
"""P0-04: verify freeze sklearn lock, certificate load, and manifest hashes."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

READY = ROOT / "results" / "wrr_submission_ready"
OUT = READY / "amendments" / "p0_04_env_lock"
CERT = ROOT / "results" / "v17_fitness" / "step9_freeze" / "certificate.joblib"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    import sklearn
    import pandas as pd
    from stream_recoverability.experiments.wrr_submission_ready.run_identity import (
        preflight_current_study,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "sklearn_runtime": sklearn.__version__,
        "required_for_certificate": "1.2.2",
        "constraints_txt_scikit_learn": "1.7.2",
        "freeze_lock_file": "constraints-freeze-certificate.txt",
    }
    freeze = ROOT / "constraints-freeze-certificate.txt"
    report["freeze_lock_exists"] = freeze.is_file()
    report["freeze_lock_mentions_1_2_2"] = "1.2.2" in freeze.read_text() if freeze.is_file() else False

    load: dict = {"ok": False}
    try:
        import joblib

        obj = joblib.load(CERT)
        load = {
            "ok": True,
            "type": f"{type(obj).__module__}.{type(obj).__name__}",
            "n_features": len(getattr(obj, "features", []) or []),
            "heads": list(getattr(obj, "heads", []) or []),
            "certificate_sha256": sha256(CERT),
            "certificate_bytes": CERT.stat().st_size,
        }
        reserved = ROOT / "results/v17_fitness/step10_confirmation/reserved_cases.parquet"
        if reserved.is_file() and hasattr(obj, "predict"):
            import pandas as pd

            sample = pd.read_parquet(reserved).head(8)
            pred = obj.predict(sample)
            load["predict_smoke_n"] = int(len(sample))
            load["predict_smoke_ok"] = True
            load["predict_columns"] = list(getattr(pred, "columns", []))[:12]
    except Exception as exc:  # noqa: BLE001
        if load.get("ok"):
            load["predict_smoke_ok"] = False
            load["predict_smoke_error"] = f"{type(exc).__name__}: {exc}"
        else:
            load = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    report["certificate_load"] = load

    preflight = preflight_current_study()
    manifest_check = next(
        (c for c in preflight.get("checks") or [] if c.get("path") == "current_data_manifest.csv"),
        {},
    )
    report["preflight"] = {
        "ok": bool(preflight.get("ok")),
        "n_checks": len(preflight.get("checks") or []),
        "absent": manifest_check.get("n_files_absent"),
        "hash_mismatch": manifest_check.get("n_hash_mismatch"),
        "size_mismatch": manifest_check.get("n_size_mismatch"),
        "checked_inputs": manifest_check.get("n_input_rows_checked"),
        "required_files": preflight.get("checks"),
    }

    manifest = pd.read_csv(READY / "current_data_manifest.csv")
    absent = []
    mismatch = []
    for row in manifest.itertuples(index=False):
        path = ROOT / str(row.input_path)
        if not path.is_file():
            absent.append(row.network_id)
            continue
        digest = sha256(path)
        if digest != str(row.sha256):
            mismatch.append(str(row.network_id))
    report["manifest_on_disk"] = {
        "n": int(len(manifest)),
        "absent": absent[:20],
        "n_absent": len(absent),
        "hash_mismatch": mismatch[:20],
        "n_hash_mismatch": len(mismatch),
    }
    report["load_compatible_with_runtime"] = bool(load.get("ok")) and sklearn.__version__.startswith("1.2.2")
    report["constraints_txt_would_break_load"] = True
    report["two_environment_contract"] = (
        "Reviewer reconstruction of Certificate.predict must install "
        "constraints-freeze-certificate.txt (scikit-learn==1.2.2). "
        "Installing constraints.txt (1.7.2) is expected to fail pickle load. "
        "Cache redraw of figures does not require the joblib."
    )
    report["reviewer_input_bundle"] = {
        "path": "dist/wrr_study_inputs_v1.tar.gz",
        "exists": (ROOT / "dist" / "wrr_study_inputs_v1.tar.gz").is_file(),
        "builder": "scripts/262_wrr_reviewer_input_bundle.py",
        "lubw_note": "bundle is confidential review-only because LUBW reserves redistribution",
    }
    ok = (
        bool(load.get("ok"))
        and report["freeze_lock_mentions_1_2_2"]
        and report["manifest_on_disk"]["n_absent"] == 0
        and report["manifest_on_disk"]["n_hash_mismatch"] == 0
        and bool(preflight.get("ok"))
    )
    report["ok"] = ok
    (OUT / "summary.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"ok": ok, "sklearn": sklearn.__version__, "load": load.get("ok"), "absent": len(absent)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
