#!/usr/bin/env python3
"""P0-01: verify claim freeze against registry and manuscript regions."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READY = ROOT / "results" / "wrr_submission_ready"
MS = ROOT / "paper" / "wrr" / "wrr_manuscript.tex"

FORBIDDEN_IN_ABSTRACT_CONCLUSIONS = {
    "P0-07",
    "P0-07-POOL",
    "P0-07-TRANSPORT",
    "M1",
    "D2",
    "L1",
    "DEPLOY-CERT",
}


def _regions(tex: str) -> dict[str, str]:
    abstract = ""
    m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    if m:
        abstract = m.group(1)
    # Conclusions: from \section*{Conclusions} or \section{Conclusions} to next section/ack
    conc = ""
    m = re.search(
        r"\\section\*?\{Conclusions\}(.*?)(\\section|\\acknowledg|\\begin\{thebibliography\}|\\end\{document\})",
        tex,
        re.S | re.I,
    )
    if m:
        conc = m.group(1)
    return {"abstract": abstract, "conclusions": conc}


def main() -> int:
    import pandas as pd

    freeze = pd.read_csv(READY / "claim_status_freeze_20261013.csv")
    registry = pd.read_csv(READY / "claim_registry.csv")
    tex = MS.read_text(encoding="utf-8") if MS.is_file() else ""
    regions = _regions(tex)

    blocked = freeze.loc[~freeze["may_enter_abstract_or_conclusions"].astype(bool)]
    issues: list[dict[str, object]] = []

    # Registry must match freeze for key claims.
    for row in freeze.itertuples(index=False):
        match = registry.loc[registry["claim_id"].astype(str).eq(str(row.claim_id))]
        if match.empty:
            issues.append({"kind": "missing_registry", "claim_id": row.claim_id})
            continue
        status = str(match.iloc[0]["status"])
        if status != str(row.frozen_status) and str(row.claim_id) in FORBIDDEN_IN_ABSTRACT_CONCLUSIONS:
            issues.append(
                {
                    "kind": "status_mismatch",
                    "claim_id": row.claim_id,
                    "registry": status,
                    "freeze": row.frozen_status,
                }
            )

    # Heuristic: sealed confirmation numbers must not appear without pending label
    # once freeze is active. Soft check — report, do not rewrite TeX here.
    pending_markers = [
        "pending",
        "探索期",
        "retrospective holdout",
        "retrospective network holdout",
    ]
    for name, body in regions.items():
        if re.search(r"-7\.9|-4\.6|sealed USGS|transport panel", body):
            if not any(marker in body for marker in pending_markers):
                issues.append(
                    {
                        "kind": "manuscript_region_needs_pending_or_retrospective_label",
                        "region": name,
                        "snippet": body[:240].replace("\n", " "),
                    }
                )

    report = {
        "ok": len(issues) == 0,
        "n_freeze_rows": int(len(freeze)),
        "n_blocked_claims": int(len(blocked)),
        "issues": issues,
    }
    out = READY / "claim_status_freeze_audit.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
