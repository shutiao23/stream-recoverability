#!/usr/bin/env python3
"""T5 topology-matched regulation on downloaded public rivers via GAGES-II join.

Uses the already-published regulation-panel station table (STAID, MAJ_NDAMS_2009,
AGGECOREGION, DRAIN_SQKM). Does not open last-check temperatures. Does not claim
T5 passed. SEPlains is recorded as a T6 candidate slice, not a confirmed zone.
"""

from __future__ import annotations

import hashlib
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
# Reuse the immutable GAGES-II archive already downloaded and identity-audited by
# the frozen regulation-panel run.  Keeping a second cache here made an offline
# T6 run silently report ``bfi_joined: false`` despite the source being on disk.
GAGES_CACHE = ROOT / "data/cache/regulation_panel_v1"
FREEZE = ROOT / "configs/regulation_panel_freeze_v1.yaml"
V1 = ROOT / "results/framework/public_rivers"
V2 = ROOT / "results/framework/public_rivers_v2"
OUTPUT = V2
COMPARISON = V2 / "operator_vs_univariate_network.csv"
GAGES_ARCHIVE = GAGES_CACHE / "basinchar_and_report_sept_2011.zip"


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


def join_network_bfi(networks: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Mean GAGES-II BFI_AVE per network. Failure to load is recorded, not invented."""

    from stream_recoverability.analysis.regulation_panel import load_freeze, load_gages_ii_bfi

    try:
        config = load_freeze(FREEZE)
        bfi = load_gages_ii_bfi(config, GAGES_CACHE, offline=True)
    except Exception:
        networks = networks.copy()
        networks["mean_bfi"] = float("nan")
        networks["n_bfi_matched"] = 0
        return networks, False
    if bfi.empty or "BFI_AVE" not in bfi.columns:
        networks = networks.copy()
        networks["mean_bfi"] = float("nan")
        return networks, False
    bfi = bfi.copy()
    bfi["STAID"] = bfi["STAID"].astype(str).str.strip().str.zfill(8)
    lookup = bfi.set_index("STAID")["BFI_AVE"]
    means = []
    for folder in (V1, V2):
        for path in sorted(folder.glob("*_daily_wide.csv")):
            if "willamette_mainstem" in path.name:
                continue
            network_id = path.name.replace("_daily_wide.csv", "")
            values = []
            for site_id in _site_ids_from_wide(path):
                key = str(site_id).zfill(8)
                if key in lookup.index:
                    value = float(lookup.loc[key])
                    if np.isfinite(value):
                        values.append(value)
            means.append(
                {
                    "network_id": network_id,
                    "mean_bfi": float(np.nanmean(values)) if values else float("nan"),
                    "n_bfi_matched": int(len(values)),
                }
            )
    if not means:
        networks = networks.copy()
        networks["mean_bfi"] = float("nan")
        return networks, False
    extra = pd.DataFrame(means)
    merged = networks.merge(extra, on="network_id", how="left")
    return merged, bool(merged["n_bfi_matched"].fillna(0).gt(0).any())


def seplains_bfi_slice(frame: pd.DataFrame) -> dict[str, object]:
    """T6 candidate: SEPlains recoverability split by BFI. Not a passed zone."""

    if frame.empty or "seplains" not in frame.columns or "mean_bfi" not in frame.columns:
        return {"n_seplains_with_bfi": 0, "passed": False}
    piece = frame.loc[frame["seplains"].fillna(False)].copy()
    piece = piece.loc[np.isfinite(pd.to_numeric(piece["mean_bfi"], errors="coerce"))]
    if "recoverability_r" not in piece.columns or len(piece) < 4:
        return {"n_seplains_with_bfi": int(len(piece)), "passed": False}
    bfi = pd.to_numeric(piece["mean_bfi"], errors="coerce")
    high = piece.loc[bfi >= float(bfi.median()), "recoverability_r"]
    low = piece.loc[bfi < float(bfi.median()), "recoverability_r"]
    return {
        "n_seplains_with_bfi": int(len(piece)),
        "mean_r_high_bfi": float(pd.to_numeric(high, errors="coerce").mean()),
        "mean_r_low_bfi": float(pd.to_numeric(low, errors="coerce").mean()),
        "delta_r_high_minus_low_bfi": float(
            pd.to_numeric(high, errors="coerce").mean()
            - pd.to_numeric(low, errors="coerce").mean()
        ),
        "passed": False,
        "note": "Candidate T6 slice. Not a confirmed failure zone.",
    }


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
    networks, bfi_joined = join_network_bfi(networks)
    networks.to_csv(OUTPUT / "matched_regulation_networks.csv", index=False)
    contrast = matched_contrast(networks)
    seplains = (
        networks.loc[networks["seplains"].fillna(False)]
        if "seplains" in networks.columns
        else pd.DataFrame()
    )
    t6 = seplains_bfi_slice(networks)
    manifest = {
        "what_this_is": (
            "GAGES-II 2009 major-dam join onto downloaded public-river station IDs, "
            "with a coarse n_sites/climate/drainage match and BFI_AVE when the "
            "GAGES-II hydro table is available."
        ),
        "what_this_is_not": (
            "Not T5 passed. Not operations data. Not a causal dam or BFI effect. "
            "Not last-check."
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
        "seplains_bfi": t6,
        "bfi_joined": bool(bfi_joined),
        "n_bfi_matched_networks": int(
            networks.get("n_bfi_matched", pd.Series(dtype=float)).fillna(0).gt(0).sum()
        ),
        "n_bfi_station_matches": int(
            networks.get("n_bfi_matched", pd.Series(dtype=float)).fillna(0).sum()
        ),
        "bfi_source": (
            {
                "archive": GAGES_ARCHIVE.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(GAGES_ARCHIVE.read_bytes()).hexdigest(),
                "offline_reuse": True,
            }
            if GAGES_ARCHIVE.is_file()
            else None
        ),
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
