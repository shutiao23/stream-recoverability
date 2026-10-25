"""Metadata-only preparation and immutable public-registration checks.

The metadata client has no observation method. Public file verification uses
the registration's archived storage, never the mutable originating project.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse
import xml.etree.ElementTree as ET

import requests
import numpy as np
import pandas as pd


METADATA_REQUESTS = frozenset({"SiteList", "MeasurementList", "TimeRange", "SiteInfo", "CollectionList"})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metadata_url(endpoint: str, request: str, **parameters) -> str:
    if request not in METADATA_REQUESTS or any(k.lower() in {"service", "request"} for k in parameters):
        raise ValueError("Only explicit Hilltop metadata requests are allowed")
    # The public Horizons server does not decode '+' as a space consistently.
    query = urlencode({"Service": "Hilltop", "Request": request, **parameters}, quote_via=quote)
    return endpoint.rstrip("?") + "?" + query


def parse_metadata(content: bytes) -> ET.Element:
    root = ET.fromstring(content)
    forbidden = {"Data", "E", "V", "Value", "MeasurementTimeseries", "MeasurementTVP", "observationData"}
    if any(e.tag.rsplit("}", 1)[-1] in forbidden for e in root.iter()):
        raise RuntimeError("Observation-bearing response rejected by metadata-only client")
    return root


def fetch_metadata(endpoint: str, cache: Path, request: str, **parameters) -> ET.Element:
    url = metadata_url(endpoint, request, **parameters)
    key = hashlib.sha256(url.encode()).hexdigest()[:24]
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (key + ".xml")
    if path.exists():
        return parse_metadata(path.read_bytes())
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    root = parse_metadata(response.content)
    path.write_bytes(response.content)
    (cache / (key + ".request.json")).write_text(json.dumps({
        "url": url, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": sha256(path), "temperature_observations_requested": False,
    }, indent=2) + "\n")
    return root


def complete_hot_years_in_span(start: str, end: str) -> int:
    """Calendar support only: no claim about actual values or their completeness."""
    try:
        a, b = datetime.fromisoformat(start).date(), datetime.fromisoformat(end).date()
    except (TypeError, ValueError):
        return 0
    return sum(a <= datetime(y, 7, 1).date() and b >= datetime(y + 1, 6, 30).date()
               for y in range(a.year - 1, b.year + 1))


def _related(item: dict, relationship: str) -> str:
    value = item.get("relationships", {}).get(relationship, {}).get("links", {}).get("related", {})
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
    if not a.get("public") or a.get("withdrawn") or a.get("embargoed") or a.get("pending_registration_approval"):
        raise RuntimeError("Registration is not public and accepted")
    if a.get("archiving") or a.get("pending_withdrawal") or a.get("pending_embargo_approval"):
        raise RuntimeError("Registration archive or approval is pending")
    stamp = a.get("date_registered")
    try:
        instant = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant > datetime.now(timezone.utc):
            raise ValueError("invalid registration time")
    except (TypeError, ValueError, AttributeError) as error:
        raise RuntimeError("Registration has no valid platform timestamp") from error
    return stamp


def verify_registration_attachments(identifier: str, local_files: list[Path], *, session=None) -> dict:
    """Require exact byte matches in this registration's archived osfstorage.

    Files can live in folders. The API returns archive-owned file identifiers;
    checking source-project files or just matching their names is insufficient.
    No new local archive is prepared or mutated here.
    """
    identifier = registration_identifier(identifier)
    session = session or requests.Session()

    def get_json(url):
        response = session.get(_api_url(url), timeout=60)
        response.raise_for_status()
        return response.json()

    # OSF API >=2.2 explicitly serializes UTC with a 'Z'; the legacy default
    # can omit its timezone. Pin the documented version instead of guessing.
    record = get_json(f"https://api.osf.io/v2/registrations/{identifier}/?version=2.20")
    timestamp = accepted_public_registration(record, identifier)
    initial = _related(record["data"], "files")
    if not initial or not urlparse(initial).path.startswith(f"/v2/registrations/{identifier}/files/"):
        raise RuntimeError("Registration has no archived file relationship")
    pending, seen, candidates = [initial], set(), []
    while pending:
        url = _api_url(pending.pop())
        if url in seen:
            continue
        seen.add(url)
        if len(seen) > 1000:
            raise RuntimeError("Unexpectedly large registration archive")
        page = get_json(url)
        for item in page.get("data", []):
            a = item.get("attributes", {})
            if a.get("kind") == "file":
                if a.get("provider") == "osfstorage":
                    candidates.append(item)
            elif a.get("kind") == "folder" and a.get("provider") == "osfstorage":
                link = _related(item, "files")
                if link:
                    pending.append(link)
        following = page.get("links", {}).get("next")
        if following:
            pending.append(following)
    matched = []
    for local in local_files:
        expected = sha256(local)
        choices = [item for item in candidates if item.get("attributes", {}).get("name") == local.name]
        match = None
        for item in choices:
            download = item.get("links", {}).get("download", "")
            parsed = urlparse(download)
            if parsed.scheme != "https" or parsed.hostname not in {"osf.io", "www.osf.io", "files.osf.io"}:
                raise RuntimeError("Expected an OSF archived file download")
            response = session.get(download, stream=True, timeout=120)
            response.raise_for_status()
            digest, count = hashlib.sha256(), 0
            for block in response.iter_content(chunk_size=1024 * 1024):
                count += len(block)
                if count > local.stat().st_size:
                    break
                digest.update(block)
            if count == local.stat().st_size and digest.hexdigest() == expected:
                match = {"name": local.name, "sha256": expected, "bytes": count,
                         "registration_file_id": item["id"], "download_url": download}
                break
        if match is None:
            raise RuntimeError(f"No exact archived attachment match for {local.name}")
        matched.append(match)
    return {"status": "public_registration_and_attachments_verified", "registration_id": identifier,
            "url": f"https://osf.io/{identifier}/", "registered_utc": timestamp,
            "verified_utc": datetime.now(timezone.utc).isoformat(), "attachments": matched,
            "water_temperature_values_requested": False}


def evaluate_endpoints(frame: pd.DataFrame, *, draws=2000, seed=0) -> tuple[dict, pd.DataFrame]:
    """Frozen E1--E4 from all eligible controlled cases, including unavailable rows.

    Mask replicates are never resampled independently. The E1 upper bound
    resamples whole connected groups, and empty bootstrap selections receive
    risk one, so dropping them cannot improve a certificate.
    """
    required={"independence_group","design_family","D2","risk_score","eval_truth_h30",
              "h30__policy","peak_overlap","D2_q05","D2_q95"}
    if required-set(frame):
        raise ValueError(f"Missing endpoint columns: {sorted(required-set(frame))}")
    c=frame.loc[frame.design_family.eq("crossed")].copy()
    if c.empty:
        return {"n_eligible":0,"n_independent_groups":0,"n_available":0,"n_admitted":0,
                "n_admitted_without_labels":0,"retention":None,"joint_primary_passed":False,
                "E1":{"risk":None,"one_sided_95_group_bootstrap_upper":None,"passed":False},
                "E2":{"n_evaluable_groups":0,"fraction_above_10_percent":None,"passed":False},
                "E3":{"coverage90":None,"passed":False},"E4":{"relative_mae_improvement":None,"passed":False},
                "status":"no_evaluable_controlled_cases"},pd.DataFrame(columns=["independence_group","n_eligible","n_admitted","n_bad","risk"])
    if c.independence_group.isna().any():
        raise ValueError("Explicit independent groups are required")
    finite_prediction=np.isfinite(c[["D2","risk_score","D2_q05","D2_q95"]]).all(axis=1)
    valid_probability=c.risk_score.between(0,1)
    available=finite_prediction&valid_probability&c.D2_q05.le(c.D2_q95)
    admitted=available&c.risk_score.le(.1)
    labeled=np.isfinite(c.eval_truth_h30)
    bad=labeled&(c.D2-c.eval_truth_h30).abs().gt(.5)
    counts=c.assign(admitted=admitted.astype(int),admitted_labeled=(admitted&labeled).astype(int),
                    bad=(admitted&bad).astype(int)).groupby("independence_group").agg(
        n_eligible=("admitted","size"),n_admitted=("admitted","sum"),
        n_admitted_labeled=("admitted_labeled","sum"),n_bad=("bad","sum"))
    counts["risk"]=counts.n_bad/counts.n_admitted_labeled.replace(0,np.nan)
    counts["risk_evaluable"]=counts.n_admitted.ge(20)&counts.n_admitted_labeled.eq(counts.n_admitted)
    counts["above_10_percent"]=counts.risk.gt(.1)&counts.risk_evaluable
    n_admitted=int(admitted.sum());unknown=int((admitted&~labeled).sum())
    risk=float(bad[admitted&labeled].mean()) if (admitted&labeled).any() else None
    rng=np.random.default_rng(seed)
    index=rng.integers(0,len(counts),(draws,len(counts)))
    total=counts.n_admitted_labeled.to_numpy()[index].sum(axis=1)
    errors=counts.n_bad.to_numpy()[index].sum(axis=1)
    bootstrap_risk=np.divide(errors,total,out=np.ones(draws),where=total>0)
    upper=float(np.quantile(bootstrap_risk,.95,method="higher"))
    evaluable=counts.risk_evaluable
    fraction=float(counts.loc[evaluable,"above_10_percent"].mean()) if evaluable.any() else None
    e1=bool(n_admitted and not unknown and risk is not None and risk<=.06 and upper<=.08)
    e2=bool(evaluable.any() and not unknown and fraction is not None and fraction<=.1)
    danger=c.peak_overlap.ge(.5)
    interval_valid=danger&available&labeled
    coverage=float(((c.D2_q05<=c.eval_truth_h30)&(c.eval_truth_h30<=c.D2_q95))[interval_valid].mean()) if interval_valid.any() else None
    from .statistics import interval_score
    score90=float(interval_score(c.loc[interval_valid,"D2_q05"].to_numpy(),c.loc[interval_valid,"D2_q95"].to_numpy(),c.loc[interval_valid,"eval_truth_h30"].to_numpy()).mean()) if interval_valid.any() else None
    width90=float((c.D2_q95-c.D2_q05)[interval_valid].mean()) if interval_valid.any() else None
    paired=danger&available&labeled&np.isfinite(c.h30__policy)
    reference=float((c.h30__policy-c.eval_truth_h30).abs()[paired].mean()) if paired.any() else None
    mae=float((c.D2-c.eval_truth_h30).abs()[paired].mean()) if paired.any() else None
    improvement=1-mae/reference if reference is not None and reference>0 else None
    result={"n_eligible":len(c),"n_independent_groups":len(counts),"n_available":int(available.sum()),
            "n_admitted":n_admitted,"n_admitted_without_labels":unknown,"retention":n_admitted/len(c),
            "E1":{"risk":risk,"one_sided_95_group_bootstrap_upper":upper,"passed":e1,
                  "bootstrap_draws":draws,"empty_bootstrap_draws":int((total==0).sum())},
            "E2":{"n_evaluable_groups":int(evaluable.sum()),"fraction_above_10_percent":fraction,"passed":e2},
            "E3":{"n_danger_eligible":int(danger.sum()),"n_danger_evaluable":int(interval_valid.sum()),
                  "coverage90":coverage,"interval_score90":score90,"width90":width90,"passed":bool(coverage is not None and .85<=coverage<=.95)},
            "E4":{"n_paired_danger":int(paired.sum()),"D2_mae":mae,"plugin_mae":reference,
                  "relative_mae_improvement":improvement,"passed":bool(improvement is not None and improvement>=.2)},
            "joint_primary_passed":e1 and e2,"inference_unit":"connected group, never mask replicate",
            "scope":"E3/E4 are descriptive registered point criteria here; no inferential superiority or individual conditional guarantee is implied"}
    return result,counts.reset_index()


REGISTERED_EXECUTION_REQUIRED={
    "scripts/495_review_completion_independent_analysis.py",
    "scripts/496_review_completion_independent_acquisition.py",
    "scripts/497_review_completion_independent_cases.py",
    "scripts/431_tr_cases.py","scripts/wrr_tr_common.py","scripts/wrr_tr_features.py",
    "src/stream_recoverability/experiments/tr_revision/independent.py",
    "src/stream_recoverability/experiments/tr_revision/native_temperature.py",
    "configs/wrr_target_recovery_20261022.json","configs/wrr_review_completion_20261024.json",
}


def require_acquisition_plan(study: Path, status: dict, runtime_root: Path | None=None, runtime_config: Path | None=None) -> dict:
    """Validate frozen, registered plan files before any observation is read."""
    if status.get("status")!="public_registration_and_attachments_verified":
        raise RuntimeError("A public registration with exact archived attachments is required")
    plan_path=study/"acquisition_plan.json"
    if not plan_path.exists():
        raise RuntimeError("Qualified acquisition plan has not been frozen")
    plan=json.loads(plan_path.read_text())
    required={"status","provider","metadata_roster_file","metadata_roster_sha256",
              "qc_specification","native_time_zone","independence_groups_verified",
              "prior_temperature_access_excluded"}
    if required-set(plan) or plan.get("status")!="metadata_roster_frozen":
        raise RuntimeError("Acquisition plan is incomplete")
    if not plan["independence_groups_verified"] or not plan["prior_temperature_access_excluded"]:
        raise RuntimeError("Independent groups and absence of prior target access must be verified")
    if not plan["qc_specification"] or not plan["native_time_zone"]:
        raise RuntimeError("Measurement quality and native clock are not fixed")
    roster=study/plan["metadata_roster_file"]
    if not roster.resolve().is_relative_to(study.resolve()) or sha256(roster)!=plan["metadata_roster_sha256"]:
        raise RuntimeError("Frozen roster bytes do not match")
    # The plan and roster must themselves be part of the exact registered code
    # archive, not merely written next to it after registration.
    import tarfile
    archive=study/"registration_code_and_protocol.tar.gz"
    attachment=next((f for f in status.get("attachments",[]) if f["name"]==archive.name),None)
    if attachment is None or sha256(archive)!=attachment["sha256"]:
        raise RuntimeError("Registered archive bytes do not match")
    with tarfile.open(archive) as bundle:
        snapshot_prefix=None
        for path in [plan_path,roster]:
            matches=[m for m in bundle.getmembers() if m.isfile() and m.name.endswith("/"+str(path.relative_to(study)))]
            if len(matches)!=1:
                raise RuntimeError("Plan/roster absent or ambiguous in registered archive")
            member=bundle.extractfile(matches[0])
            if member is None or hashlib.sha256(member.read()).hexdigest()!=sha256(path):
                raise RuntimeError("Plan/roster differs from the registration snapshot")
            if path==plan_path:snapshot_prefix=str(Path(matches[0].name).parent)
        try:manifest_member=bundle.extractfile(snapshot_prefix+"/file_sha256.json")
        except KeyError as error:raise RuntimeError("Registered execution manifest is missing") from error
        if manifest_member is None:raise RuntimeError("Registered execution manifest is missing")
        manifest=json.load(manifest_member)
        if not REGISTERED_EXECUTION_REQUIRED.issubset(manifest):raise RuntimeError("Registered execution manifest omits required analysis files")
        root=(runtime_root or Path(__file__).resolve().parents[4]).resolve()
        if runtime_config is not None:
            active=Path(runtime_config)
            if not active.is_absolute():active=root/active
            if not active.is_file() or sha256(active)!=manifest["configs/wrr_target_recovery_20261022.json"]:
                raise RuntimeError("Active source configuration differs from registered archive")
        executable=[name for name in manifest if (name.startswith(("src/","scripts/")) and name.endswith(".py")) or name in REGISTERED_EXECUTION_REQUIRED]
        for name in executable:
            target=(root/name).resolve()
            if not target.is_relative_to(root) or not target.is_file() or sha256(target)!=manifest[name]:
                raise RuntimeError("Execution file differs from registered archive: "+name)
        for name,field in [("source_case_settings.json","source_case_settings_sha256"),("source_missingness_generator.json","source_generator_sha256")]:
            target=study/name;key=snapshot_prefix+"/"+name
            if key not in manifest or not target.exists() or sha256(target)!=manifest[key] or plan.get(field)!=manifest[key]:
                raise RuntimeError("Generation input differs from registered archive: "+name)
        for name,field in [("global_source_candidate.joblib","source_model_sha256"),("classical_calibration.json","classical_calibration_sha256")]:
            key="results/wrr_review_completion_20261024/deployment/"+name;target=root/key
            if key not in manifest or not target.exists() or sha256(target)!=manifest[key] or plan.get(field)!=manifest[key]:
                raise RuntimeError("Source inference artifact differs from registered archive: "+name)
    return plan
