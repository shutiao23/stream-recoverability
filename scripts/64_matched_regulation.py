#!/usr/bin/env python3
"""T5 topology-matched regulation on downloaded public rivers via GAGES-II join.

Uses the already-published regulation-panel station table (STAID, MAJ_NDAMS_2009,
AGGECOREGION, DRAIN_SQKM). Does not open last-check temperatures. Does not claim
T5 passed. SEPlains is recorded as a T6 candidate slice, not a confirmed zone.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

GAGES = ROOT / "results/regulation_panel_v1_legacy_transport/station_metrics.csv"
V1 = ROOT / "results/framework/public_rivers"
V2 = ROOT / "results/framework/public_rivers_v2"
OUTPUT = V2
COMPARISON = V2 / "operator_vs_univariate_network.csv"


def _site_ids_from_wide(path: Path) -> list[str]:
    header = pd.read_csv(path, nrows=0)
    return [str(item) for item in header.columns if item and item != "Unnamed: 0"]


def network_gages_rows() -> pd.DataFrame:
    gages = pd.read_csv(GAGES, dtype={"station_id": str})
    gages["station_id"] = gages["station_id"].astype(str).str.zfill(8)
    lookup = gages.set_index("station_id")
    rows = []
    for folder in (V1, V2):
        for path in sorted(folder.glob("*_daily_wide.csv")):
            if "willamette_mainstem" in path.name:
                continue
            network_id = path.name.replace("_daily_wide.csv", "")
            site_ids = _site_ids_from_wide(path)
            matched = []
            for site_id in site_ids:
                key = str(site_id).zfill(8)
                if key in lookup.index:
                    matched.append(lookup.loc[key])
            if not matched:
                rows.append(
                    {
                        "network_id": network_id,
                        "n_sites": len(site_ids),
                        "n_gages_matched": 0,
                        "regulated": False,
                        "matchable": False,
                    }
                )
                continue
            piece = pd.DataFrame(matched)
            maj = pd.to_numeric(piece.get("MAJ_NDAMS_2009"), errors="coerce")
            drain = pd.to_numeric(piece.get("DRAIN_SQKM"), errors="coerce")
            eco = piece["AGGECOREGION"].mode().iloc[0] if "AGGECOREGION" in piece else ""
            rows.append(
                {
                    "network_id": network_id,
                    "n_sites": len(site_ids),
                    "n_gages_matched": int(len(piece)),
                    "frac_major_dam": float(maj.ge(1).mean()) if len(maj) else float("nan"),
                    "regulated": bool(maj.ge(1).mean() >= 0.5) if len(maj) else False,
                    "mean_drain_sqkm": float(drain.mean()) if len(drain) else float("nan"),
                    "aggecoregion": str(eco),
                    "seplains": str(eco) == "SEPlains",
                    "matchable": True,
                }
            )
    return pd.DataFrame(rows)


def matched_contrast(frame: pd.DataFrame) -> dict[str, object]:
    """Match regulated vs not on n_sites and climate; compare recoverability if present."""

    usable = frame.loc[frame["matchable"].fillna(False)].copy()
    if usable.empty or "recoverability_r" not in usable.columns:
        return {
            "n_matched_pairs": 0,
            "mean_delta_r_regulated_minus_unregulated": float("nan"),
            "passed": False,
        }
    treated = usable.loc[usable["regulated"]].copy()
    control = usable.loc[~usable["regulated"]].copy()
    pairs = []
    used_control: set[str] = set()
    for row in treated.itertuples(index=False):
        candidates = control.loc[
            ~control["network_id"].isin(used_control)
            & control["n_sites"].eq(row.n_sites)
            & control["aggecoregion"].eq(row.aggecoregion)
        ]
        if candidates.empty:
            candidates = control.loc[
                ~control["network_id"].isin(used_control)
                & (control["n_sites"] - row.n_sites).abs().le(1)
            ]
        if candidates.empty or "recoverability_r" not in candidates.columns:
            continue
        drain = pd.to_numeric(candidates["mean_drain_sqkm"], errors="coerce")
        target = float(row.mean_drain_sqkm) if np.isfinite(row.mean_drain_sqkm) else float(drain.median())
        order = (drain - target).abs()
        partner = candidates.iloc[int(order.argsort().iloc[0])]
        used_control.add(str(partner.network_id))
        pairs.append(
            {
                "regulated_id": row.network_id,
                "control_id": partner.network_id,
                "delta_r": float(row.recoverability_r) - float(partner.recoverability_r),
                "aggecoregion": row.aggecoregion,
            }
        )
    if not pairs:
        return {"n_matched_pairs": 0, "mean_delta_r_regulated_minus_unregulated": float("nan"), "passed": False}
    table = pd.DataFrame(pairs)
    return {
        "n_matched_pairs": int(len(table)),
        "mean_delta_r_regulated_minus_unregulated": float(table["delta_r"].mean()),
        "pairs": table.to_dict(orient="records"),
        "passed": False,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    networks = network_gages_rows()
    if COMPARISON.is_file():
        scores = pd.read_csv(COMPARISON)
        if "network_id" in scores.columns:
            networks = networks.merge(scores, on="network_id", how="left")
    networks.to_csv(OUTPUT / "matched_regulation_networks.csv", index=False)
    contrast = matched_contrast(networks)
    seplains = (
        networks.loc[networks["seplains"].fillna(False)]
        if "seplains" in networks.columns
        else pd.DataFrame()
    )
    manifest = {
        "what_this_is": (
            "GAGES-II 2009 major-dam join onto downloaded public-river station IDs, "
            "with a coarse n_sites/climate/drainage match."
        ),
        "what_this_is_not": (
            "Not T5 passed. Not operations data. Not a causal dam effect. "
            "Not BFI until that GAGES-II table is loaded. Not last-check."
        ),
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "t5_passed": False,
        "t6_passed": False,
        "n_networks": int(len(networks)),
        "n_gages_matched_networks": int(networks["matchable"].fillna(False).sum()) if not networks.empty else 0,
        "n_regulated": int(networks["regulated"].fillna(False).sum()) if not networks.empty else 0,
        "n_seplains": int(len(seplains)),
        "matched_contrast": {
            key: contrast[key]
            for key in contrast
            if key != "pairs"
        },
        "seplains_is_candidate_failure_zone": bool(len(seplains) > 0),
        "bfi_joined": False,
        "last_check_temperatures_opened": False,
    }
    if contrast.get("pairs"):
        pd.DataFrame(contrast["pairs"]).to_csv(OUTPUT / "matched_regulation_pairs.csv", index=False)
    (OUTPUT / "matched_regulation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
