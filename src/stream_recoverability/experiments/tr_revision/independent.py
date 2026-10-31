"""Study metadata, measurement settings and scientific endpoint evaluation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
import xml.etree.ElementTree as ET

import requests
import numpy as np
import pandas as pd


METADATA_REQUESTS = frozenset(
    {"SiteList", "MeasurementList", "TimeRange", "SiteInfo", "CollectionList"}
)


def metadata_url(endpoint: str, request: str, **parameters) -> str:
    if request not in METADATA_REQUESTS or any(
        k.lower() in {"service", "request"} for k in parameters
    ):
        raise ValueError("Only explicit Hilltop metadata requests are allowed")
    # The public Horizons server does not decode '+' as a space consistently.
    query = urlencode(
        {"Service": "Hilltop", "Request": request, **parameters}, quote_via=quote
    )
    return endpoint.rstrip("?") + "?" + query


def parse_metadata(content: bytes) -> ET.Element:
    root = ET.fromstring(content)
    forbidden = {
        "Data",
        "E",
        "V",
        "Value",
        "MeasurementTimeseries",
        "MeasurementTVP",
        "observationData",
    }
    if any(e.tag.rsplit("}", 1)[-1] in forbidden for e in root.iter()):
        raise RuntimeError(
            "Observation-bearing response rejected by metadata-only client"
        )
    return root


def fetch_metadata(
    endpoint: str, cache: Path, request: str, **parameters
) -> ET.Element:
    url = metadata_url(endpoint, request, **parameters)
    key = quote(
        "__".join([request, *[str(v) for _, v in sorted(parameters.items())]]), safe=""
    )
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (key + ".xml")
    if path.exists():
        return parse_metadata(path.read_bytes())
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    root = parse_metadata(response.content)
    path.write_bytes(response.content)
    (cache / (key + ".request.json")).write_text(
        json.dumps(
            {
                "url": url,
                "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                "temperature_observations_requested": False,
            },
            indent=2,
        )
        + "\n"
    )
    return root


def complete_hot_years_in_span(start: str, end: str) -> int:
    """Calendar support only: no claim about actual values or their completeness."""
    try:
        a, b = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
    except (TypeError, ValueError):
        return 0
    return sum(
        a <= datetime(y, 7, 1).date() and b >= datetime(y + 1, 6, 30).date()
        for y in range(a.year - 1, b.year + 1)
    )


def _related(item: dict, relationship: str) -> str:
    value = (
        item.get("relationships", {})
        .get(relationship, {})
        .get("links", {})
        .get("related", {})
    )
    return value.get("href", "") if isinstance(value, dict) else value


def _api_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme != "https" or p.hostname != "api.osf.io":
        raise RuntimeError("Expected an HTTPS OSF API relationship")
    return url


def registration_identifier(identifier: str) -> str:
    identifier = identifier.strip().rstrip("/")
    if "://" in identifier:
        parsed = urlparse(identifier)
        if parsed.scheme != "https" or parsed.hostname not in {"osf.io", "www.osf.io"}:
            raise ValueError("Expected an OSF registration URL or identifier")
        identifier = parsed.path.strip("/")
    if not identifier.isalnum():
        raise ValueError("Expected an OSF registration URL or identifier")
    return identifier


def accepted_public_registration(document: dict, identifier: str) -> str:
    data = document.get("data", {})
    a = data.get("attributes", {})
    if data.get("id") != identifier or data.get("type") != "registrations":
        raise RuntimeError("Record is not the requested registration")
    if (
        not a.get("public")
        or a.get("withdrawn")
        or a.get("embargoed")
        or a.get("pending_registration_approval")
    ):
        raise RuntimeError("Registration is not public and accepted")
    if (
        a.get("archiving")
        or a.get("pending_withdrawal")
        or a.get("pending_embargo_approval")
    ):
        raise RuntimeError("Registration archive or approval is pending")
    stamp = a.get("date_registered")
    try:
        instant = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant > datetime.now(timezone.utc):
            raise ValueError("invalid registration time")
    except (TypeError, ValueError, AttributeError) as error:
        raise RuntimeError("Registration has no valid platform timestamp") from error
    return stamp


def evaluate_endpoints(
    frame: pd.DataFrame, *, draws=2000, seed=0
) -> tuple[dict, pd.DataFrame]:
    """Frozen E1--E4 from all eligible controlled cases, including unavailable rows.

    Mask replicates are never resampled independently. The E1 upper bound
    resamples whole connected groups, and empty bootstrap selections receive
    risk one, so dropping them cannot improve a certificate.
    """
    required = {
        "independence_group",
        "design_family",
        "D2",
        "risk_score",
        "eval_truth_h30",
        "h30__policy",
        "peak_overlap",
        "D2_q05",
        "D2_q95",
    }
    if required - set(frame):
        raise ValueError(f"Missing endpoint columns: {sorted(required - set(frame))}")
    c = frame.loc[frame.design_family.eq("crossed")].copy()
    if c.empty:
        return {
            "n_eligible": 0,
            "n_independent_groups": 0,
            "n_available": 0,
            "n_admitted": 0,
            "n_admitted_without_labels": 0,
            "retention": None,
            "joint_primary_passed": False,
            "E1": {
                "risk": None,
                "one_sided_95_group_bootstrap_upper": None,
                "passed": False,
            },
            "E2": {
                "n_evaluable_groups": 0,
                "fraction_above_10_percent": None,
                "passed": False,
            },
            "E3": {"coverage90": None, "passed": False},
            "E4": {"relative_mae_improvement": None, "passed": False},
            "status": "no_evaluable_controlled_cases",
        }, pd.DataFrame(
            columns=["independence_group", "n_eligible", "n_admitted", "n_bad", "risk"]
        )
    if c.independence_group.isna().any():
        raise ValueError("Explicit independent groups are required")
    finite_prediction = np.isfinite(c[["D2", "risk_score", "D2_q05", "D2_q95"]]).all(
        axis=1
    )
    valid_probability = c.risk_score.between(0, 1)
    available = finite_prediction & valid_probability & c.D2_q05.le(c.D2_q95)
    admitted = available & c.risk_score.le(0.1)
    labeled = np.isfinite(c.eval_truth_h30)
    bad = labeled & (c.D2 - c.eval_truth_h30).abs().gt(0.5)
    counts = (
        c.assign(
            admitted=admitted.astype(int),
            admitted_labeled=(admitted & labeled).astype(int),
            bad=(admitted & bad).astype(int),
        )
        .groupby("independence_group")
        .agg(
            n_eligible=("admitted", "size"),
            n_admitted=("admitted", "sum"),
            n_admitted_labeled=("admitted_labeled", "sum"),
            n_bad=("bad", "sum"),
        )
    )
    counts["risk"] = counts.n_bad / counts.n_admitted_labeled.replace(0, np.nan)
    counts["risk_evaluable"] = counts.n_admitted.ge(20) & counts.n_admitted_labeled.eq(
        counts.n_admitted
    )
    counts["above_10_percent"] = counts.risk.gt(0.1) & counts.risk_evaluable
    n_admitted = int(admitted.sum())
    unknown = int((admitted & ~labeled).sum())
    risk = float(bad[admitted & labeled].mean()) if (admitted & labeled).any() else None
    rng = np.random.default_rng(seed)
    index = rng.integers(0, len(counts), (draws, len(counts)))
    total = counts.n_admitted_labeled.to_numpy()[index].sum(axis=1)
    errors = counts.n_bad.to_numpy()[index].sum(axis=1)
    bootstrap_risk = np.divide(errors, total, out=np.ones(draws), where=total > 0)
    upper = float(np.quantile(bootstrap_risk, 0.95, method="higher"))
    evaluable = counts.risk_evaluable
    fraction = (
        float(counts.loc[evaluable, "above_10_percent"].mean())
        if evaluable.any()
        else None
    )
    e1 = bool(
        n_admitted
        and not unknown
        and risk is not None
        and risk <= 0.06
        and upper <= 0.08
    )
    e2 = bool(
        evaluable.any() and not unknown and fraction is not None and fraction <= 0.1
    )
    danger = c.peak_overlap.ge(0.5)
    interval_valid = danger & available & labeled
    coverage = (
        float(
            ((c.D2_q05 <= c.eval_truth_h30) & (c.eval_truth_h30 <= c.D2_q95))[
                interval_valid
            ].mean()
        )
        if interval_valid.any()
        else None
    )
    from .statistics import interval_score

    score90 = (
        float(
            interval_score(
                c.loc[interval_valid, "D2_q05"].to_numpy(),
                c.loc[interval_valid, "D2_q95"].to_numpy(),
                c.loc[interval_valid, "eval_truth_h30"].to_numpy(),
            ).mean()
        )
        if interval_valid.any()
        else None
    )
    width90 = (
        float((c.D2_q95 - c.D2_q05)[interval_valid].mean())
        if interval_valid.any()
        else None
    )
    paired = danger & available & labeled & np.isfinite(c.h30__policy)
    reference = (
        float((c.h30__policy - c.eval_truth_h30).abs()[paired].mean())
        if paired.any()
        else None
    )
    mae = (
        float((c.D2 - c.eval_truth_h30).abs()[paired].mean()) if paired.any() else None
    )
    improvement = (
        1 - mae / reference if reference is not None and reference > 0 else None
    )
    result = {
        "n_eligible": len(c),
        "n_independent_groups": len(counts),
        "n_available": int(available.sum()),
        "n_admitted": n_admitted,
        "n_admitted_without_labels": unknown,
        "retention": n_admitted / len(c),
        "E1": {
            "risk": risk,
            "one_sided_95_group_bootstrap_upper": upper,
            "passed": e1,
            "bootstrap_draws": draws,
            "empty_bootstrap_draws": int((total == 0).sum()),
        },
        "E2": {
            "n_evaluable_groups": int(evaluable.sum()),
            "fraction_above_10_percent": fraction,
            "passed": e2,
        },
        "E3": {
            "n_danger_eligible": int(danger.sum()),
            "n_danger_evaluable": int(interval_valid.sum()),
            "coverage90": coverage,
            "interval_score90": score90,
            "width90": width90,
            "passed": bool(coverage is not None and 0.85 <= coverage <= 0.95),
        },
        "E4": {
            "n_paired_danger": int(paired.sum()),
            "D2_mae": mae,
            "plugin_mae": reference,
            "relative_mae_improvement": improvement,
            "passed": bool(improvement is not None and improvement >= 0.2),
        },
        "joint_primary_passed": e1 and e2,
        "inference_unit": "connected group, never mask replicate",
        "scope": "E3/E4 are descriptive registered point criteria here; no inferential superiority or individual conditional guarantee is implied",
    }
    return result, counts.reset_index()


def load_acquisition_plan(study: Path) -> dict:
    """Read the study's measurement settings directly."""
    return json.loads((study / "acquisition_plan.json").read_text())
