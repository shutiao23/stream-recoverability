"""Split analysis eligibility from provider QC and known-issue flags.

``quality_approved`` remains a legacy alias of ``analysis_eligible``. It is
not a provider quality approval. Unknown source quality must be written as
``provider_qc_status=unknown``.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

PROVIDER_QC_UNKNOWN = "unknown"
PROVIDER_QC_APPROVED = "approved"
PROVIDER_QC_MISSING = "missing"
KNOWN_ISSUE_B1_SHIFT = "b1_level_datum_shift"
KNOWN_ISSUE_S2_DISCREPANCY = "s2_source_year_order_discrepancy"
B1_LEVEL_SHIFT_START = pd.Timestamp("2019-01-01")
S2_SUSPECT_START = pd.Timestamp("2013-01-01")
S2_SUSPECT_END = pd.Timestamp("2019-12-31")
QC_COLUMNS = (
    "analysis_eligible",
    "provider_qc_status",
    "known_issue_flag",
    "known_issue_code",
    "quality_approved",
)


def _as_bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(bool)


def assign_observation_qc(natural_observed: pd.Series) -> pd.DataFrame:
    """Map source presence to the three-field QC contract."""

    observed = _as_bool(natural_observed)
    return pd.DataFrame(
        {
            "analysis_eligible": observed.to_numpy(dtype=bool),
            "provider_qc_status": np.where(observed, PROVIDER_QC_UNKNOWN, PROVIDER_QC_MISSING),
            "known_issue_flag": np.zeros(len(observed), dtype=bool),
            "known_issue_code": np.full(len(observed), "", dtype=object),
            "quality_approved": observed.to_numpy(dtype=bool),
        },
        index=observed.index,
    )


def known_issue_masks(
    dates: pd.Series,
    stations: pd.Series,
    variables: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Return Boolean masks for the two predeclared provenance issues."""

    normalized = pd.to_datetime(dates, errors="raise").dt.normalize()
    station = stations.astype(str)
    variable = variables.astype(str)
    b1_shift = (
        station.eq("B1") & variable.eq("L") & normalized.ge(B1_LEVEL_SHIFT_START)
    )
    s2_suspect = (
        station.eq("S2")
        & variable.isin(("T", "F", "L"))
        & normalized.between(S2_SUSPECT_START, S2_SUSPECT_END, inclusive="both")
    )
    return b1_shift, s2_suspect


def apply_known_issue_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """Flag B1 datum-shift and S2 year-order rows without changing values."""

    result = frame.copy()
    b1_shift, s2_suspect = known_issue_masks(
        result["date"], result["station_id"], result["variable"]
    )
    if "known_issue_flag" not in result:
        result["known_issue_flag"] = False
    if "known_issue_code" not in result:
        result["known_issue_code"] = ""
    result["known_issue_flag"] = _as_bool(result["known_issue_flag"]) | b1_shift | s2_suspect
    codes = result["known_issue_code"].astype("string").fillna("")
    codes = codes.mask(b1_shift, KNOWN_ISSUE_B1_SHIFT)
    codes = codes.mask(s2_suspect & ~b1_shift, KNOWN_ISSUE_S2_DISCREPANCY)
    result["known_issue_code"] = codes.astype(object)
    return result


def attach_qc_fields(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure the split QC fields exist and remain semantically honest."""

    if "natural_observed" not in frame.columns:
        raise KeyError("attach_qc_fields requires natural_observed")
    result = frame.copy()
    assigned = assign_observation_qc(result["natural_observed"])
    if "analysis_eligible" not in result:
        result["analysis_eligible"] = assigned["analysis_eligible"]
    else:
        result["analysis_eligible"] = _as_bool(result["analysis_eligible"])
    if "provider_qc_status" not in result:
        result["provider_qc_status"] = assigned["provider_qc_status"]
    result["provider_qc_status"] = (
        result["provider_qc_status"].astype("string").fillna(PROVIDER_QC_MISSING)
    )
    unknown_written_as_approved = result["provider_qc_status"].eq(PROVIDER_QC_APPROVED) & (
        result.get("qc_status", pd.Series("", index=result.index))
        .astype("string")
        .eq("observed_unflagged")
    )
    if bool(unknown_written_as_approved.any()):
        raise ValueError(
            "provider_qc_status=approved is forbidden for observed_unflagged rows"
        )
    if "quality_approved" not in result:
        result["quality_approved"] = result["analysis_eligible"]
    else:
        result["quality_approved"] = _as_bool(result["quality_approved"])
    result = apply_known_issue_flags(result)
    return result


def load_quality_codebook(path: str | Path | None = None) -> pd.DataFrame:
    """Read the project codebook and reject the old approved-unknown contract."""

    codebook_path = path or "metadata/quality_codebook.csv"
    codebook = pd.read_csv(codebook_path)
    required = {
        "qc_status",
        "meaning",
        "analysis_eligible",
        "provider_qc_status",
        "known_issue_flag",
    }
    missing = sorted(required.difference(codebook.columns))
    if missing:
        raise ValueError(f"quality codebook is missing columns: {missing}")
    unflagged = codebook.loc[codebook["qc_status"].astype(str).eq("observed_unflagged")]
    if unflagged.empty:
        raise ValueError("quality codebook must define observed_unflagged")
    if unflagged["provider_qc_status"].astype(str).eq(PROVIDER_QC_APPROVED).any():
        raise ValueError(
            "observed_unflagged must not have provider_qc_status=approved"
        )
    return codebook


def qc_counts(frame: Mapping[str, pd.Series] | pd.DataFrame) -> dict[str, int]:
    """Return reviewable counts for manifests and audits."""

    data = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
    empty = pd.Series(False, index=data.index)
    provider = (
        data["provider_qc_status"]
        if "provider_qc_status" in data
        else pd.Series(pd.NA, index=data.index, dtype="string")
    )
    return {
        "analysis_eligible_values": int(
            _as_bool(data["analysis_eligible"] if "analysis_eligible" in data else empty).sum()
        ),
        "provider_qc_unknown_values": int(provider.astype("string").eq(PROVIDER_QC_UNKNOWN).sum()),
        "provider_qc_approved_values": int(provider.astype("string").eq(PROVIDER_QC_APPROVED).sum()),
        "known_issue_values": int(
            _as_bool(data["known_issue_flag"] if "known_issue_flag" in data else empty).sum()
        ),
        "legacy_quality_approved_values": int(
            _as_bool(data["quality_approved"] if "quality_approved" in data else empty).sum()
        ),
    }


__all__ = [
    "B1_LEVEL_SHIFT_START",
    "KNOWN_ISSUE_B1_SHIFT",
    "KNOWN_ISSUE_S2_DISCREPANCY",
    "PROVIDER_QC_APPROVED",
    "PROVIDER_QC_MISSING",
    "PROVIDER_QC_UNKNOWN",
    "QC_COLUMNS",
    "S2_SUSPECT_END",
    "S2_SUSPECT_START",
    "apply_known_issue_flags",
    "assign_observation_qc",
    "attach_qc_fields",
    "known_issue_masks",
    "load_quality_codebook",
    "qc_counts",
]
