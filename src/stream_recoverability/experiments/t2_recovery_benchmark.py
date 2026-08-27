"""Open-role-only preparation and bounded execution for the v9.1 T2 benchmark.

This module is deliberately separate from the historical M1--M10 runner.  Its
input surface is a three-directory allowlist, and it refuses any network whose
manifest is sealed, opened, incomplete, or not overlap-qualified.  Work items
are deterministic and checkpointed one JSON file at a time so an interrupted
large run can resume without rewriting completed results.

Only the artificial-stress Tier-1 geometry is executable here.  Natural-outage
and adversarial catalogs remain explicit workload dependencies rather than
being silently approximated.  Tier 2 is metadata-only: this module can lock its
roster, but it never imports or trains a deep model.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from itertools import chain
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd
import yaml

from stream_recoverability.analysis.recoverability_spectrum import recoverability
from stream_recoverability.experiments.frozen_outage_geometry import (
    load_frozen_geometry_bindings,
)
from stream_recoverability.models.baselines import (
    ClimatologyBaseline,
    DonorRegressionBaseline,
    KalmanSmootherBaseline,
    OfflineLinearInterpolation,
    PCHIPInterpolation,
    XGBoostBaseline,
)

DESIGN_RELATIVE_PATH = Path("configs/design_freeze_v9.yaml")
CATALOG_RELATIVE_PATH = Path("configs/network_catalog_v3_split.yaml")
ALLOWED_INPUTS: tuple[tuple[str, str], ...] = (
    ("open_role_qc/development", "development"),
    ("open_role_qc/validation", "validation"),
    ("w3_development_pilot", "development"),
)
FAILURE_CLOSURE_INPUTS: tuple[tuple[str, str], ...] = (
    ("open_role_qc/failure_closure6/development", "development"),
    ("open_role_qc/failure_closure6/validation", "validation"),
)
GEOMETRY_BINDING_RELATIVE_PATH = Path("results/framework/t2_outage_geometry_v1")
TIER1_MODELS = (
    "climatology",
    "pchip_or_linear",
    "kalman",
    "donor_regression",
    "xgboost",
)
BASE_INFORMATION_CONDITIONS = ("B", "D", "B_union_D")
EXTENDED_INFORMATION_CONDITIONS = (
    "B_union_D_union_M",
    "B_union_D_union_M_union_H",
)
TIER2_MODELS = ("air2stream", "saits", "csdi", "grin")
TIER2_GAPS = (30, 90, 180)
MIN_TRAIN_OBSERVATIONS = 365
RUNNER_CONTRACT_VERSION = "t2_v91_runner_v3_frozen_geometry_bindings"


@dataclass(frozen=True)
class FitCacheKey:
    """Identity of one fit, excluding held-out truth, predictions, and skill."""

    input_sha256: str
    target_station: str
    model: str
    information_condition: str
    meteorology_lag_days: int | None
    training_mask_sha256: str
    training_features_sha256: str


FitResolver = Callable[[FitCacheKey, Callable[[], Any]], Any]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _training_mask_sha256(mask: pd.Series) -> str:
    """Hash the exact dated boolean mask presented to a model fit."""

    if not isinstance(mask.index, pd.DatetimeIndex):
        raise TypeError("fit-cache training mask requires a DatetimeIndex")
    digest = hashlib.sha256()
    digest.update(np.asarray(mask.index.view("i8"), dtype="<i8").tobytes())
    digest.update(mask.to_numpy(dtype=np.uint8).tobytes())
    return digest.hexdigest()


def _training_features_sha256(
    frame: pd.DataFrame,
    mask: pd.Series,
    columns: Sequence[str],
) -> str:
    """Hash only dated training rows and the named raw fit inputs.

    The target is intentionally included because it is a fit input.  Held-out
    target values, predictions, MAE, and skill never enter this digest.
    """

    selected = mask.reindex(frame.index, fill_value=False).to_numpy(dtype=bool)
    names = [str(value) for value in columns]
    missing = [name for name in names if name not in frame.columns]
    if missing:
        raise KeyError(f"fit-cache feature columns are absent: {missing}")
    digest = hashlib.sha256()
    digest.update(
        json.dumps(names, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    index = pd.DatetimeIndex(frame.index)
    digest.update(np.asarray(index.view("i8")[selected], dtype="<i8").tobytes())
    values = frame.loc[selected, names].apply(pd.to_numeric, errors="coerce")
    digest.update(np.asarray(values.to_numpy(dtype=float), dtype="<f8").tobytes())
    return digest.hexdigest()


def _fit_cache_key(
    *,
    input_sha256: str,
    target_station: str,
    model: str,
    information_condition: str,
    meteorology_lag_days: int | None,
    frame: pd.DataFrame,
    train_mask: pd.Series,
    feature_columns: Sequence[str],
) -> FitCacheKey:
    """Build the strict fit identity used by all T2 v4 fit caches."""

    return FitCacheKey(
        input_sha256=str(input_sha256),
        target_station=str(target_station),
        model=str(model),
        information_condition=str(information_condition),
        meteorology_lag_days=(
            None if meteorology_lag_days is None else int(meteorology_lag_days)
        ),
        training_mask_sha256=_training_mask_sha256(train_mask),
        training_features_sha256=_training_features_sha256(
            frame, train_mask, feature_columns
        ),
    )


def _resolve_fit(
    resolver: FitResolver | None,
    key: FitCacheKey,
    factory: Callable[[], Any],
) -> Any:
    return factory() if resolver is None else resolver(key, factory)


def _canonical_sha(rows: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(
        list(rows), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return _sha256_bytes(payload)


def json_safe(value: Any) -> Any:
    """Replace non-finite scalars before strict JSON serialization."""

    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if math.isfinite(float(value)) else None
    return value


def load_v91_budget(repo_root: str | Path) -> dict[str, Any]:
    """Load and validate the exact v9.1 two-tier fields used by this runner."""

    path = Path(repo_root).resolve() / DESIGN_RELATIVE_PATH
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError(f"design freeze is not a mapping: {path}")
    if document.get("design_id") != "design_freeze_v9":
        raise ValueError("T2 runner requires design_freeze_v9")
    benchmark = document.get("recovery_benchmark") or {}
    if benchmark.get("protocol_amendment") != "v9.1":
        raise ValueError("T2 runner requires protocol_amendment v9.1")
    budget = benchmark.get("two_tier_compute_budget") or {}
    tier1 = budget.get("tier_1_full_corpus") or {}
    tier2 = budget.get("tier_2_stratified_subsample") or {}
    if tuple(tier1.get("models") or ()) != TIER1_MODELS:
        raise ValueError("v9.1 Tier-1 roster changed; refuse an implicit remap")
    if tier1.get("grid") != "full_gap_times_placement_times_information":
        raise ValueError("v9.1 Tier-1 grid is not the expected full grid")
    if int(benchmark.get("placements_per_cell_min", 0)) < 20:
        raise ValueError("v9.1 requires at least 20 placements per cell")
    information = tuple(benchmark.get("information_conditions") or ())
    expected_information = BASE_INFORMATION_CONDITIONS + EXTENDED_INFORMATION_CONDITIONS
    if information != expected_information:
        raise ValueError("v9.1 information-condition roster changed")
    gaps = tuple(int(value) for value in benchmark["gap_geometries"]["artificial_stress"])
    if gaps != (7, 14, 30, 60, 90, 180, 365):
        raise ValueError("v9.1 artificial gap roster changed")
    if tuple(tier2.get("models") or ()) != TIER2_MODELS:
        raise ValueError("v9.1 Tier-2 roster changed")
    if tuple(int(value) for value in tier2.get("gaps_all_required") or ()) != TIER2_GAPS:
        raise ValueError("v9.1 Tier-2 gap roster changed")
    if int(tier2.get("n_target", 0)) != 30 or tuple(tier2.get("n_allowed_range") or ()) != (28, 32):
        raise ValueError("v9.1 Tier-2 sample size contract changed")
    return {
        "design_path": str(DESIGN_RELATIVE_PATH),
        "design_sha256": _sha256_file(path),
        "design_id": document["design_id"],
        "protocol_amendment": benchmark["protocol_amendment"],
        "placements": int(benchmark["placements_per_cell_min"]),
        "information_conditions": information,
        "gaps": gaps,
        "tier_1_models": tuple(tier1["models"]),
        "tier_2": tier2,
        "primary_evidence_forbids": tuple(benchmark.get("primary_evidence_forbids") or ()),
    }


@dataclass(frozen=True)
class OpenNetwork:
    network_id: str
    role: str
    source_key: str
    wide_path: str
    wide_sha256: str
    manifest_path: str
    n_days: int
    n_stations: int


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (FileNotFoundError, ValueError):
        return False
    return True


def _network_manifest(directory: Path) -> Path | None:
    for name in ("network_qc_manifest.json", "network_manifest.json"):
        path = directory / name
        if path.is_file():
            return path
    return None


def _locked_catalog_roles(repo: Path) -> tuple[str, dict[str, str]]:
    """Return the declared split SHA and network roles from the locked catalog."""

    path = repo / CATALOG_RELATIVE_PATH
    if not path.is_file():
        raise FileNotFoundError(f"locked catalog split is required: {path}")
    catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, dict) or catalog.get("status") != "locked_before_download":
        raise ValueError("open-role discovery requires the locked-before-download catalog")
    split_sha = str(catalog.get("sha256") or "")
    if len(split_sha) != 64:
        raise ValueError("locked catalog has no valid declared split SHA")
    roles: dict[str, str] = {}
    for row in catalog.get("networks") or []:
        network_id = str(row.get("network_id") or "")
        role = str(row.get("role") or "")
        if not network_id or network_id in roles:
            raise ValueError("locked catalog contains a missing or duplicate network_id")
        roles[network_id] = role
    return split_sha, roles


def discover_open_networks(
    repo_root: str | Path,
    *,
    input_roots: Sequence[tuple[str, str]] = ALLOWED_INPUTS,
    require_failure_closure6: bool = False,
) -> tuple[list[OpenNetwork], dict[str, Any]]:
    """Discover overlap-qualified inputs without traversing any sealed directory."""

    repo = Path(repo_root).resolve()
    corpus = repo / "data_versions/global_network_corpus_v1"
    catalog_split_sha, catalog_roles = _locked_catalog_roles(repo)
    selected: dict[str, OpenNetwork] = {}
    roots: list[dict[str, Any]] = []
    rejected = Counter()
    # Full-QC development wins over its pilot duplicate. Validation is disjoint.
    for source_key, expected_role in input_roots:
        root = corpus / source_key
        root_summary: dict[str, Any] = {
            "source_key": source_key,
            "expected_role": expected_role,
            "exists": root.is_dir(),
            "networks_seen": 0,
            "networks_eligible": 0,
        }
        roots.append(root_summary)
        if not root.is_dir():
            continue
        networks_root = root / "networks"
        if not networks_root.is_dir() or not _inside(networks_root, root):
            rejected["missing_or_unsafe_networks_directory"] += 1
            continue
        for directory in sorted(networks_root.glob("huc8_*")):
            root_summary["networks_seen"] += 1
            if not directory.is_dir() or not _inside(directory, root):
                rejected["unsafe_network_directory"] += 1
                continue
            manifest_path = _network_manifest(directory)
            if manifest_path is None or not _inside(manifest_path, root):
                rejected["missing_or_unsafe_manifest"] += 1
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            role = str(manifest.get("role", ""))
            network_id = str(manifest.get("network_id") or directory.name)
            overlap = manifest.get("overlap") or {}
            overlap_role = str(overlap.get("role", role))
            if role != expected_role or overlap_role != expected_role:
                rejected["role_mismatch_or_sealed"] += 1
                continue
            if role == "sealed" or bool(manifest.get("sealed_temperature_records_read")):
                rejected["sealed_or_opened_input"] += 1
                continue
            if str(manifest.get("split_sha256") or "") != catalog_split_sha:
                rejected["catalog_split_sha_mismatch"] += 1
                continue
            if catalog_roles.get(network_id) != role:
                rejected["catalog_role_mismatch_or_network_absent"] += 1
                continue
            if require_failure_closure6 and (
                manifest.get("qualification_mode") != "failure_closure6"
                or manifest.get("qualified_years_min") != 6
                or manifest.get("relaxation_applied") is not True
                or manifest.get("relaxation_trigger")
                != "open_survival_projection_lt_100"
            ):
                rejected["not_failure_closure6"] += 1
                continue
            if manifest.get("status") != "complete":
                rejected["network_incomplete"] += 1
                continue
            if overlap.get("complete_enough") is not True:
                rejected["overlap_not_complete_enough"] += 1
                continue
            wide_path = directory / "daily_wide_qc.csv"
            if not wide_path.is_file() or not _inside(wide_path, root):
                rejected["missing_or_unsafe_daily_wide_qc"] += 1
                continue
            header = pd.read_csv(wide_path, nrows=0)
            n_stations = max(0, len(header.columns) - 1)
            n_days = int(overlap.get("n_days") or 0)
            network = OpenNetwork(
                network_id=network_id,
                role=role,
                source_key=source_key,
                wide_path=str(wide_path.relative_to(repo)),
                wide_sha256=_sha256_file(wide_path),
                manifest_path=str(manifest_path.relative_to(repo)),
                n_days=n_days,
                n_stations=n_stations,
            )
            if network.network_id not in selected:
                selected[network.network_id] = network
                root_summary["networks_eligible"] += 1
            else:
                rejected["duplicate_shadowed_by_preferred_root"] += 1
    networks = sorted(selected.values(), key=lambda item: (item.role, item.network_id))
    return networks, {
        "allowed_input_roots": [value for value, _ in input_roots],
        "sealed_input_roots_allowed": [],
        "catalog_path": str(CATALOG_RELATIVE_PATH),
        "catalog_split_sha256": catalog_split_sha,
        "catalog_roles_cross_checked": True,
        "qualification_mode": (
            "failure_closure6" if require_failure_closure6 else "primary8_or_pilot"
        ),
        "roots": roots,
        "rejected": dict(sorted(rejected.items())),
        "n_networks_eligible": len(networks),
        "roles": dict(sorted(Counter(item.role for item in networks).items())),
    }


def discover_failure_closure_networks(
    repo_root: str | Path,
) -> tuple[list[OpenNetwork], dict[str, Any]]:
    """Discover the frozen six-year open corpus used by all T2 geometries."""

    return discover_open_networks(
        repo_root,
        input_roots=FAILURE_CLOSURE_INPUTS,
        require_failure_closure6=True,
    )


def read_panel(repo_root: str | Path, network: OpenNetwork) -> pd.DataFrame:
    repo = Path(repo_root).resolve()
    path = repo / network.wide_path
    allowed = [
        repo / "data_versions/global_network_corpus_v1" / source
        for source, _ in (*ALLOWED_INPUTS, *FAILURE_CLOSURE_INPUTS)
    ]
    if not any(root.is_dir() and _inside(path, root) for root in allowed):
        raise ValueError(f"refusing a panel outside the open-role allowlist: {path}")
    if _sha256_file(path) != network.wide_sha256:
        raise ValueError(f"panel changed after workload inventory: {network.network_id}")
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index))
    frame = frame.apply(pd.to_numeric, errors="coerce").sort_index()
    if frame.index.has_duplicates:
        raise ValueError(f"duplicate dates in {network.network_id}")
    return frame


def _year_split(index: pd.DatetimeIndex, fraction: float = 0.7) -> tuple[np.ndarray, np.ndarray]:
    years = np.asarray(sorted(pd.unique(index.year)), dtype=int)
    if years.size < 2:
        return np.ones(len(index), dtype=bool), np.zeros(len(index), dtype=bool)
    cut = min(years.size - 1, max(1, round(years.size * fraction)))
    training_years = set(years[:cut].tolist())
    train = np.asarray([year in training_years for year in index.year], dtype=bool)
    return train, ~train


def deterministic_placements(
    panel: pd.DataFrame,
    *,
    target: str,
    gap_length: int,
    count: int,
) -> list[int]:
    """Choose a common strict B-union-D roster for every information condition."""

    values = panel[target].to_numpy(dtype=float)
    train, test = _year_split(panel.index)
    gap = int(gap_length)
    if gap < 1 or len(values) < gap or int(np.isfinite(values[train]).sum()) < MIN_TRAIN_OBSERVATIONS:
        return []
    observed = np.isfinite(values)
    target_run = np.convolve(observed.astype(int), np.ones(gap, dtype=int), mode="valid") == gap
    test_run = np.convolve(test.astype(int), np.ones(gap, dtype=int), mode="valid") == gap
    eligible = target_run & test_run
    boundary = np.zeros_like(eligible)
    starts = np.arange(len(eligible))
    valid = (starts > 0) & (starts + gap < len(values))
    boundary[valid] = observed[starts[valid] - 1] & observed[starts[valid] + gap]
    eligible &= boundary
    donors = panel.drop(columns=[target]).to_numpy(dtype=float)
    if donors.shape[1] == 0:
        return []
    donor_any = np.isfinite(donors).any(axis=1)
    donor_run = np.convolve(donor_any.astype(int), np.ones(gap, dtype=int), mode="valid") == gap
    eligible &= donor_run
    candidates = np.flatnonzero(eligible)
    if candidates.size <= count:
        return [int(value) for value in candidates]
    positions = np.linspace(0, candidates.size - 1, num=int(count), dtype=int)
    return [int(candidates[value]) for value in positions]


@dataclass(frozen=True)
class WorkItem:
    ordinal: int
    item_id: str
    network_id: str
    role: str
    source_key: str
    target_station: str
    model: str
    gap_length: int
    placement: int
    start_index: int
    information_condition: str
    task: str = "offline_archival"
    geometry: str = "artificial_stress"
    geometry_id: str = ""
    geometry_catalog_file_sha256: str = ""
    geometry_row_sha256: str = ""
    truth_start_date: str = ""
    observed_missing_start_date: str = ""
    donor_mask_rule: str = "preserve_observed_donors"
    target_mask_scope: str = "target_station_gap"
    boundary_mode: str = "both"
    stress_id: str = ""


def iter_work_items(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    budget: Mapping[str, Any],
    *,
    roles: Iterable[str] | None = None,
    network_ids: Iterable[str] | None = None,
    models: Iterable[str] | None = None,
    gaps: Iterable[int] | None = None,
    information_conditions: Iterable[str] | None = None,
) -> Iterable[WorkItem]:
    """Yield the stable artificial-stress grid in lexical/network order."""

    role_filter = None if roles is None else set(roles)
    network_filter = None if network_ids is None else set(network_ids)
    selected_models = tuple(models or budget["tier_1_models"])
    selected_gaps = tuple(int(value) for value in (gaps or budget["gaps"]))
    selected_information = tuple(information_conditions or budget["information_conditions"])
    if not set(selected_models).issubset(TIER1_MODELS):
        raise ValueError("model filter contains a non-Tier-1 model")
    if not set(selected_gaps).issubset(set(budget["gaps"])):
        raise ValueError("gap filter contains a non-frozen gap")
    if not set(selected_information).issubset(set(budget["information_conditions"])):
        raise ValueError("information filter contains a non-frozen condition")
    ordinal = 0
    for network in networks:
        if role_filter is not None and network.role not in role_filter:
            continue
        if network_filter is not None and network.network_id not in network_filter:
            continue
        panel = read_panel(repo_root, network)
        for target in sorted(str(value) for value in panel.columns):
            for gap in selected_gaps:
                starts = deterministic_placements(
                    panel,
                    target=target,
                    gap_length=gap,
                    count=int(budget["placements"]),
                )
                # The common strict B-union-D roster is shared by every
                # information condition; shortfalls occupy the same slots.
                padded_starts = [
                    starts[position] if position < len(starts) else -1
                    for position in range(int(budget["placements"]))
                ]
                for information in selected_information:
                    for placement, start in enumerate(padded_starts):
                        for model in selected_models:
                            identity = {
                                "design_sha256": budget["design_sha256"],
                                "input_sha256": network.wide_sha256,
                                "network_id": network.network_id,
                                "target_station": target,
                                "model": model,
                                "gap_length": gap,
                                "placement": placement,
                                "start_index": start,
                                "information_condition": information,
                                "task": "offline_archival",
                                "geometry": "artificial_stress",
                                "runner_contract_version": RUNNER_CONTRACT_VERSION,
                            }
                            yield WorkItem(
                                ordinal=ordinal,
                                item_id=_canonical_sha([identity])[:24],
                                network_id=network.network_id,
                                role=network.role,
                                source_key=network.source_key,
                                target_station=target,
                                model=model,
                                gap_length=gap,
                                placement=placement,
                                start_index=start,
                                information_condition=information,
                            )
                            ordinal += 1


def _bool_value(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _boundary_mode(left: bool, right: bool) -> str:
    if left and right:
        return "both"
    if left:
        return "left_only"
    if right:
        return "right_only"
    return "none"


def iter_frozen_geometry_work_items(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    budget: Mapping[str, Any],
    natural: pd.DataFrame,
    adversarial: pd.DataFrame,
    geometry_manifest: Mapping[str, Any],
    *,
    models: Iterable[str] | None = None,
    information_conditions: Iterable[str] | None = None,
) -> Iterable[WorkItem]:
    """Expand frozen natural/adversarial rows without selecting new geometry."""

    selected_models = tuple(models or budget["tier_1_models"])
    selected_information = tuple(information_conditions or budget["information_conditions"])
    if not set(selected_models).issubset(TIER1_MODELS):
        raise ValueError("model filter contains a non-Tier-1 model")
    if not set(selected_information).issubset(set(budget["information_conditions"])):
        raise ValueError("information filter contains a non-frozen condition")
    lookup = {network.network_id: network for network in networks}
    panel_cache: dict[str, pd.DataFrame] = {}
    catalog_file_sha = {
        "natural_outage": str(geometry_manifest["natural_outage"]["file_sha256"]),
        "adversarial_stress": str(geometry_manifest["adversarial"]["file_sha256"]),
    }
    natural_ready = natural.loc[natural["benchmark_eligible"].map(_bool_value)].copy()
    geometry_rows = chain(
        (("natural_outage", row) for _, row in natural_ready.iterrows()),
        (("adversarial_stress", row) for _, row in adversarial.iterrows()),
    )
    ordinal = 0
    for geometry, row in geometry_rows:
        record = json_safe(row.to_dict())
        network_id = str(record["network_id"])
        station_id = str(record["station_id"])
        network = lookup.get(network_id)
        if network is None:
            raise ValueError(f"frozen geometry network absent from closure6 corpus: {network_id}")
        if str(record["role"]) != network.role:
            raise ValueError(f"frozen geometry role mismatch: {network_id}")
        if network_id not in panel_cache:
            panel_cache[network_id] = read_panel(repo_root, network)
        panel = panel_cache[network_id]
        if station_id not in panel.columns:
            raise ValueError(f"frozen geometry station absent from panel: {network_id}/{station_id}")
        if geometry == "natural_outage":
            if _bool_value(record["actual_missing_truth_available"]):
                raise ValueError("natural missing days may not be used as truth")
            truth_start = str(record["benchmark_start_date"])
            observed_missing_start = str(record["start_date"])
            donor_mask_rule = "preserve_observed_donors"
            target_mask_scope = "target_station_gap"
            boundary_mode = "both"
            stress_id = ""
        else:
            truth_start = str(record["start_date"])
            observed_missing_start = ""
            donor_mask_rule = str(record["donor_mask_rule"])
            target_mask_scope = str(record["target_mask_scope"])
            boundary_mode = _boundary_mode(
                _bool_value(record["left_boundary_required"]),
                _bool_value(record["right_boundary_required"]),
            )
            stress_id = str(record["stress_id"])
        stamp = pd.Timestamp(truth_start)
        positions = np.flatnonzero(panel.index == stamp)
        length = int(record["length_days"])
        start_index = int(positions[0]) if len(positions) == 1 else -1
        if start_index >= 0:
            expected_dates = pd.date_range(stamp, periods=length, freq="D")
            observed_dates = panel.index[start_index : start_index + length]
            truth = panel[station_id].iloc[start_index : start_index + length]
            if not observed_dates.equals(expected_dates) or not np.isfinite(
                truth.to_numpy(dtype=float)
            ).all():
                start_index = -1
        row_sha = _canonical_sha([record])
        for information in selected_information:
            for model in selected_models:
                identity = {
                    "runner_contract_version": RUNNER_CONTRACT_VERSION,
                    "geometry_catalog_file_sha256": catalog_file_sha[geometry],
                    "geometry_id": str(record["geometry_id"]),
                    "geometry_row_sha256": row_sha,
                    "model": model,
                    "information_condition": information,
                    "input_sha256": network.wide_sha256,
                }
                yield WorkItem(
                    ordinal=ordinal,
                    item_id=_canonical_sha([identity])[:24],
                    network_id=network_id,
                    role=network.role,
                    source_key=network.source_key,
                    target_station=station_id,
                    model=model,
                    gap_length=length,
                    placement=0,
                    start_index=start_index,
                    information_condition=information,
                    task="offline_archival",
                    geometry=geometry,
                    geometry_id=str(record["geometry_id"]),
                    geometry_catalog_file_sha256=catalog_file_sha[geometry],
                    geometry_row_sha256=row_sha,
                    truth_start_date=truth_start,
                    observed_missing_start_date=observed_missing_start,
                    donor_mask_rule=donor_mask_rule,
                    target_mask_scope=target_mask_scope,
                    boundary_mode=boundary_mode,
                    stress_id=stress_id,
                )
                ordinal += 1


def load_t2_geometry_workload(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    budget: Mapping[str, Any],
    *,
    directory: str | Path | None = None,
    models: Iterable[str] | None = None,
    information_conditions: Iterable[str] | None = None,
) -> tuple[Iterable[WorkItem], dict[str, Any]]:
    """Validate frozen catalog bytes, then return a lazy T2 work-item stream."""

    binding_root = (
        Path(directory)
        if directory is not None
        else Path(repo_root).resolve() / GEOMETRY_BINDING_RELATIVE_PATH
    )
    natural, adversarial, manifest = load_frozen_geometry_bindings(binding_root)
    return (
        iter_frozen_geometry_work_items(
            repo_root,
            networks,
            budget,
            natural,
            adversarial,
            manifest,
            models=models,
            information_conditions=information_conditions,
        ),
        manifest,
    )


def iter_all_work_items(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    budget: Mapping[str, Any],
) -> Iterable[WorkItem]:
    """Yield the complete frozen workload with one global ordinal namespace."""

    geometry_items, _ = load_t2_geometry_workload(repo_root, networks, budget)
    combined = chain(iter_work_items(repo_root, networks, budget), geometry_items)
    for ordinal, item in enumerate(combined):
        yield replace(item, ordinal=ordinal)


def _cell_contract(item: WorkItem) -> dict[str, Any]:
    """Declare whether and how a model consumes the advertised information."""

    information = item.information_condition
    if item.start_index < 0:
        return {
            "supported": False,
            "reason": (
                "fewer_than_frozen_common_bd_placements_are_data_eligible"
                if item.geometry == "artificial_stress"
                else "frozen_geometry_truth_window_unavailable_without_reselection"
            ),
            "consumed_information": [],
            "category": "data_ineligible",
        }
    if item.model == "climatology":
        return {
            "supported": True,
            "reason": "reference_ignores_available_information_by_design",
            "consumed_information": [],
            "category": "reference",
        }
    if information in EXTENDED_INFORMATION_CONDITIONS:
        return {
            "supported": False,
            "reason": "structural_unimplemented_no_meteorology_or_hydraulics_adapter",
            "consumed_information": [],
            "category": "structural_not_applicable",
        }
    if item.model == "pchip_or_linear":
        if information == "B":
            if item.boundary_mode != "both":
                return {
                    "supported": False,
                    "reason": "pchip_or_linear_requires_two_boundaries",
                    "consumed_information": ["B"],
                    "category": "structural_not_applicable",
                }
            return {
                "supported": True,
                "reason": "",
                "consumed_information": ["B"],
                "category": "executable",
            }
        return {
            "supported": False,
            "reason": "model_does_not_implement_full_information_condition",
            "consumed_information": ["B"],
            "category": "structural_not_applicable",
        }
    if item.model == "kalman":
        if information == "B" and item.boundary_mode != "none":
            return {
                "supported": True,
                "reason": "",
                "consumed_information": ["B"],
                "category": "executable",
            }
        return {
            "supported": False,
            "reason": "model_does_not_implement_full_information_condition",
            "consumed_information": ["B"],
            "category": "structural_not_applicable",
        }
    if item.model in {"donor_regression", "xgboost"}:
        if information in {"D", "B_union_D"} and item.donor_mask_rule == (
            "mask_all_network_stations_during_gap"
        ):
            return {
                "supported": False,
                "reason": "donor_information_masked_by_frozen_geometry",
                "consumed_information": [],
                "category": "structural_not_applicable",
            }
        if information == "D":
            return {
                "supported": True,
                "reason": "",
                "consumed_information": ["D"],
                "category": "executable",
            }
        if information == "B_union_D":
            if item.boundary_mode == "none":
                return {
                    "supported": False,
                    "reason": "boundary_information_absent_in_frozen_geometry",
                    "consumed_information": ["D"],
                    "category": "structural_not_applicable",
                }
            return {
                "supported": True,
                "reason": "",
                "consumed_information": ["B", "D"],
                "category": "executable",
            }
        return {
            "supported": False,
            "reason": "model_does_not_implement_information_condition",
            "consumed_information": ["D"],
            "category": "structural_not_applicable",
        }
    return {
        "supported": False,
        "reason": "unknown_model",
        "consumed_information": [],
        "category": "structural_not_applicable",
    }


def _cell_support(item: WorkItem) -> tuple[bool, str]:
    contract = _cell_contract(item)
    return bool(contract["supported"]), str(contract["reason"])


def _boundary_predictions(
    masked_target: pd.Series, *, start: int, stop: int, boundary_mode: str
) -> pd.Series:
    """Two-boundary offline reconstruction, with frozen linear fallback."""

    if boundary_mode in {"left_only", "right_only", "none"}:
        result = masked_target.copy()
        if boundary_mode == "left_only" and start > 0:
            result.iloc[start:stop] = masked_target.iloc[start - 1]
        elif boundary_mode == "right_only" and stop < len(masked_target):
            result.iloc[start:stop] = masked_target.iloc[stop]
        return result
    try:
        return PCHIPInterpolation(target_col=str(masked_target.name)).predict(masked_target)
    except (ValueError, np.linalg.LinAlgError):
        return OfflineLinearInterpolation(target_col=str(masked_target.name)).predict(
            masked_target
        )


def _prediction_sha256(values: np.ndarray) -> str:
    array = np.asarray(values, dtype="<f8")
    return _sha256_bytes(array.shape.__repr__().encode() + b"|" + array.tobytes())


def _combined_model_frame(
    panel: pd.DataFrame,
    *,
    target: str,
    train_mask: pd.Series,
    start: int,
    stop: int,
    boundary_mode: str,
) -> tuple[pd.DataFrame, str]:
    """Build a leakage-safe B feature for donor/XGBoost B-union-D cells.

    Training rows use leave-one-out adjacent training boundaries.  Gap rows use
    the two-sided PCHIP/linear prediction from the masked series.  Test targets
    never enter model fitting or training-feature construction.
    """

    feature_name = "__boundary_B_prediction"
    training_target = panel[target].where(train_mask)
    train_boundary = (
        training_target.shift(1) + training_target.shift(-1)
    ) / 2.0
    masked_target = panel[target].copy()
    masked_target.iloc[start:stop] = np.nan
    gap_boundary = _boundary_predictions(
        masked_target,
        start=start,
        stop=stop,
        boundary_mode=boundary_mode,
    ).iloc[start:stop]
    feature = train_boundary.copy()
    feature.iloc[start:stop] = gap_boundary.to_numpy(dtype=float)
    model_frame = panel.copy()
    model_frame.loc[model_frame.index[start:stop], target] = np.nan
    model_frame[feature_name] = feature
    return model_frame, feature_name


def execute_item(
    repo_root: str | Path,
    network: OpenNetwork,
    item: WorkItem,
    *,
    panel: pd.DataFrame | None = None,
    climatology_cache: dict[
        tuple[str, str, int, int], tuple[pd.Series, float]
    ]
    | None = None,
    fit_resolver: FitResolver | None = None,
    meteorology_lag_days: int | None = None,
) -> dict[str, Any]:
    """Execute one small traditional-baseline cell; no deep model is imported.

    ``panel`` and the caches are optional execution accelerators.
    Callers supplying a panel must first obtain it through :func:`read_panel`,
    which retains the open-role path allowlist and byte-level custody check.
    The default path is deliberately unchanged for compatibility and A/B
    equivalence checks.
    """

    contract = _cell_contract(item)
    base: dict[str, Any] = {
        **asdict(item),
        "input_sha256": network.wide_sha256,
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "available_information_condition": item.information_condition,
        "consumed_information": contract["consumed_information"],
        "information_condition_result": contract["category"] == "executable",
        "workload_category": contract["category"],
        "formal_evidence": False,
        "sealed_temperature_records_read": False,
    }
    if not contract["supported"]:
        status = {
            "data_ineligible": "data_ineligible",
            "structural_not_applicable": "structural_not_applicable",
            "external_dependency": "external_dependency",
        }[str(contract["category"])]
        return {
            **base,
            "status": status,
            "reason": contract["reason"],
        }
    if panel is None:
        panel = read_panel(repo_root, network)
    target = item.target_station
    if target not in panel:
        return {**base, "status": "failed", "reason": "target_station_missing"}
    start = int(item.start_index)
    stop = start + int(item.gap_length)
    truth = panel[target].iloc[start:stop].to_numpy(dtype=float)
    masked = panel.copy()
    masked.loc[masked.index[start:stop], target] = np.nan
    if item.donor_mask_rule == "mask_all_network_stations_during_gap":
        donor_columns = [column for column in masked.columns if str(column) != target]
        masked.loc[masked.index[start:stop], donor_columns] = np.nan
    train, _ = _year_split(panel.index)
    train[start:stop] = False
    train_mask = pd.Series(train, index=panel.index)
    donors = [str(value) for value in panel.columns if str(value) != target]
    began = perf_counter()
    try:
        legacy_climate_key = (network.wide_sha256, target, start, stop)
        cached_climate = (
            None
            if climatology_cache is None
            else climatology_cache.get(legacy_climate_key)
        )
        if cached_climate is not None and fit_resolver is None:
            climate_prediction, climate_mae = cached_climate
        else:
            climate_key = _fit_cache_key(
                input_sha256=network.wide_sha256,
                target_station=target,
                model="climatology",
                information_condition=item.information_condition,
                meteorology_lag_days=meteorology_lag_days,
                frame=panel,
                train_mask=train_mask,
                feature_columns=[target],
            )
            climatology = _resolve_fit(
                fit_resolver,
                climate_key,
                lambda: ClimatologyBaseline(target_col=target).fit(
                    panel, dates=panel.index, train_mask=train_mask
                ),
            )
            climate_prediction = climatology.predict(
                panel, dates=panel.index
            ).iloc[start:stop]
            climate_mae = float(
                np.mean(np.abs(climate_prediction.to_numpy(dtype=float) - truth))
            )
            if climatology_cache is not None and fit_resolver is None:
                climatology_cache[legacy_climate_key] = (
                    climate_prediction.copy(),
                    climate_mae,
                )
        if not np.isfinite(climate_mae) or climate_mae <= 0.0:
            return {
                **base,
                "status": "data_ineligible",
                "workload_category": "data_ineligible",
                "reason": "undefined_skill_nonpositive_climatology_mae",
                "runtime_seconds": float(perf_counter() - began),
                "formal_evidence": False,
                "sealed_temperature_records_read": False,
            }
        if item.model == "climatology":
            prediction = climate_prediction
            implementation = "training_doy_climatology"
        elif item.model == "pchip_or_linear":
            prediction = _boundary_predictions(
                masked[target],
                start=start,
                stop=stop,
                boundary_mode=item.boundary_mode,
            ).iloc[start:stop]
            implementation = "pchip_with_linear_fallback_B"
        elif item.model == "kalman":
            key = _fit_cache_key(
                input_sha256=network.wide_sha256,
                target_station=target,
                model=item.model,
                information_condition=item.information_condition,
                meteorology_lag_days=meteorology_lag_days,
                frame=panel,
                train_mask=train_mask,
                feature_columns=[target],
            )
            model = _resolve_fit(
                fit_resolver,
                key,
                lambda: KalmanSmootherBaseline(target_col=target).fit(
                    panel, train_mask=train_mask
                ),
            )
            prediction = model.predict(masked).iloc[start:stop]
            implementation = "local_linear_trend_kalman_smoother"
        elif item.model == "donor_regression":
            if item.information_condition == "B_union_D":
                model_frame, boundary_feature = _combined_model_frame(
                    panel,
                    target=target,
                    train_mask=train_mask,
                    start=start,
                    stop=stop,
                    boundary_mode=item.boundary_mode,
                )
                key = _fit_cache_key(
                    input_sha256=network.wide_sha256,
                    target_station=target,
                    model=item.model,
                    information_condition=item.information_condition,
                    meteorology_lag_days=meteorology_lag_days,
                    frame=model_frame,
                    train_mask=train_mask,
                    feature_columns=[target, *donors, boundary_feature],
                )
                model = _resolve_fit(
                    fit_resolver,
                    key,
                    lambda: DonorRegressionBaseline(
                        donors,
                        target_col=target,
                        covariate_cols=[boundary_feature],
                    ).fit(model_frame, dates=panel.index, train_mask=train_mask),
                )
                prediction = model.predict(model_frame, dates=panel.index).iloc[start:stop]
                implementation = "seasonal_ridge_donor_plus_train_loo_boundary_BD"
            else:
                key = _fit_cache_key(
                    input_sha256=network.wide_sha256,
                    target_station=target,
                    model=item.model,
                    information_condition=item.information_condition,
                    meteorology_lag_days=meteorology_lag_days,
                    frame=masked,
                    train_mask=train_mask,
                    feature_columns=[target, *donors],
                )
                model = _resolve_fit(
                    fit_resolver,
                    key,
                    lambda: DonorRegressionBaseline(donors, target_col=target).fit(
                        masked, dates=panel.index, train_mask=train_mask
                    ),
                )
                prediction = model.predict(masked, dates=panel.index).iloc[start:stop]
                implementation = "seasonal_ridge_donor_regression_D"
        elif item.model == "xgboost":
            if not XGBoostBaseline.is_available():
                return {
                    **base,
                    "status": "external_dependency",
                    "workload_category": "external_dependency",
                    "reason": "xgboost_not_installed",
                }
            if item.information_condition == "B_union_D":
                model_frame, boundary_feature = _combined_model_frame(
                    panel,
                    target=target,
                    train_mask=train_mask,
                    start=start,
                    stop=stop,
                    boundary_mode=item.boundary_mode,
                )
                key = _fit_cache_key(
                    input_sha256=network.wide_sha256,
                    target_station=target,
                    model=item.model,
                    information_condition=item.information_condition,
                    meteorology_lag_days=meteorology_lag_days,
                    frame=model_frame,
                    train_mask=train_mask,
                    feature_columns=[target, *donors, boundary_feature],
                )
                model = _resolve_fit(
                    fit_resolver,
                    key,
                    lambda: XGBoostBaseline(
                        [*donors, boundary_feature], target_col=target
                    ).fit(model_frame, dates=panel.index, train_mask=train_mask),
                )
                prediction = model.predict(model_frame, dates=panel.index).iloc[start:stop]
                implementation = "xgboost_donor_plus_train_loo_boundary_BD"
            else:
                key = _fit_cache_key(
                    input_sha256=network.wide_sha256,
                    target_station=target,
                    model=item.model,
                    information_condition=item.information_condition,
                    meteorology_lag_days=meteorology_lag_days,
                    frame=masked,
                    train_mask=train_mask,
                    feature_columns=[target, *donors],
                )
                model = _resolve_fit(
                    fit_resolver,
                    key,
                    lambda: XGBoostBaseline(donors, target_col=target).fit(
                        masked, dates=panel.index, train_mask=train_mask
                    ),
                )
                prediction = model.predict(masked, dates=panel.index).iloc[start:stop]
                implementation = "xgboost_donor_D"
        else:  # pragma: no cover - guarded by iter_work_items
            raise ValueError(f"unknown Tier-1 model: {item.model}")
        predicted = prediction.to_numpy(dtype=float)
        valid = np.isfinite(truth) & np.isfinite(predicted)
        if not valid.any():
            return {**base, "status": "failed", "reason": "no_finite_gap_predictions"}
        mae = float(np.mean(np.abs(predicted[valid] - truth[valid])))
        reference = contract["category"] == "reference"
        return {
            **base,
            "status": "reference_complete" if reference else "complete",
            "reason": contract["reason"] if reference else "",
            "implementation": implementation,
            "n_scored": int(valid.sum()),
            "mae_deg_c": climate_mae if reference else mae,
            "climatology_mae_deg_c": climate_mae,
            "achieved_skill": 0.0 if reference else recoverability(mae, climate_mae),
            "prediction_sha256": _prediction_sha256(predicted),
            "reference_ignores_available_information": reference,
            "runtime_seconds": float(perf_counter() - began),
            "formal_evidence": False,
            "sealed_temperature_records_read": False,
        }
    except (ImportError, KeyError, RuntimeError, ValueError, np.linalg.LinAlgError) as error:
        return {
            **base,
            "status": "failed",
            "reason": f"{type(error).__name__}: {error}",
            "runtime_seconds": float(perf_counter() - began),
        }


def run_items(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    items: Iterable[WorkItem],
    output_dir: str | Path,
    *,
    start_ordinal: int = 0,
    max_items: int | None = None,
) -> dict[str, Any]:
    """Run/checkpoint a bounded slice. Existing valid item files are resumed."""

    output = Path(output_dir)
    checkpoints = output / "checkpoints_v3"
    checkpoints.mkdir(parents=True, exist_ok=True)
    lookup = {network.network_id: network for network in networks}
    selected = 0
    executed = 0
    resumed = 0
    statuses = Counter()
    for item in items:
        if item.ordinal < int(start_ordinal):
            continue
        if max_items is not None and selected >= int(max_items):
            break
        selected += 1
        path = checkpoints / f"{item.item_id}.json"
        if path.is_file():
            prior = json.loads(path.read_text(encoding="utf-8"))
            if prior.get("item_id") != item.item_id:
                raise RuntimeError(f"checkpoint identity mismatch: {path}")
            resumed += 1
            statuses[str(prior.get("status", "unknown"))] += 1
            continue
        result = execute_item(repo_root, lookup[item.network_id], item)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(json_safe(result), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        executed += 1
        statuses[result["status"]] += 1
    summary = {
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "checkpoint_namespace": "checkpoints_v3",
        "selected": selected,
        "executed": executed,
        "resumed": resumed,
        "statuses": dict(sorted(statuses.items())),
        "start_ordinal": int(start_ordinal),
        "max_items": max_items,
        "checkpoint_dir": str(checkpoints),
        "sealed_temperature_records_read": False,
        "formal_evidence": False,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "last_run.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def build_workload_manifest(
    repo_root: str | Path,
    networks: Sequence[OpenNetwork],
    inventory: Mapping[str, Any],
    budget: Mapping[str, Any],
    *,
    count_items: bool = True,
    include_frozen_geometry: bool = True,
) -> dict[str, Any]:
    """Build an auditable dry-run manifest; it never writes outcome metrics."""

    counts = Counter()
    category_counts = Counter()
    reason_counts = Counter()
    geometry_item_counts = Counter()
    workload_digest = hashlib.sha256()
    n_items = 0
    geometry_binding: dict[str, Any] | None = None
    item_stream: Iterable[WorkItem] = iter_work_items(repo_root, networks, budget)
    if include_frozen_geometry:
        binding_root = Path(repo_root).resolve() / GEOMETRY_BINDING_RELATIVE_PATH
        natural, adversarial, frozen_manifest = load_frozen_geometry_bindings(
            binding_root
        )
        if int(frozen_manifest["n_networks"]) != len(networks):
            raise ValueError("frozen geometry/network corpus count mismatch")
        if frozen_manifest.get("split_sha256") != inventory.get(
            "catalog_split_sha256"
        ):
            raise ValueError("frozen geometry/catalog split SHA mismatch")
        geometry_binding = {
            "directory": str(GEOMETRY_BINDING_RELATIVE_PATH),
            "manifest_schema": frozen_manifest["manifest_schema"],
            "qualification_mode": frozen_manifest["qualification_mode"],
            "n_networks": int(frozen_manifest["n_networks"]),
            "natural_catalog_file_sha256": frozen_manifest["natural_outage"][
                "file_sha256"
            ],
            "natural_catalog_canonical_sha256": frozen_manifest["natural_outage"][
                "canonical_table_sha256"
            ],
            "natural_geometry_rows": int(
                frozen_manifest["natural_outage"]["n_benchmark_eligible"]
            ),
            "adversarial_catalog_file_sha256": frozen_manifest["adversarial"][
                "file_sha256"
            ],
            "adversarial_catalog_canonical_sha256": frozen_manifest["adversarial"][
                "canonical_table_sha256"
            ],
            "adversarial_geometry_rows": int(frozen_manifest["adversarial"]["n_rows"]),
            "split_sha256": frozen_manifest["split_sha256"],
            "geometry_reselected_by_runner": False,
            "runner_truth_rules": {
                "natural_outage": (
                    "plant_at_benchmark_start_date_score_held_out_observed_counterpart_"
                    "never_score_actual_missing_dates"
                ),
                "adversarial_stress": (
                    "plant_at_start_date_then_apply_target_mask_scope_and_donor_mask_rule"
                ),
            },
        }
        item_stream = chain(
            item_stream,
            iter_frozen_geometry_work_items(
                repo_root,
                networks,
                budget,
                natural,
                adversarial,
                frozen_manifest,
            ),
        )
    if count_items:
        for global_ordinal, raw_item in enumerate(item_stream):
            item = replace(raw_item, ordinal=global_ordinal)
            n_items += 1
            geometry_item_counts[item.geometry] += 1
            workload_digest.update(item.item_id.encode())
            workload_digest.update(b"\n")
            counts[(item.role, item.model, item.information_condition)] += 1
            contract = _cell_contract(item)
            category = str(contract["category"])
            reason = str(contract["reason"])
            if (
                category == "executable"
                and item.model == "xgboost"
                and not XGBoostBaseline.is_available()
            ):
                category = "external_dependency"
                reason = "xgboost_not_installed"
            category_counts[category] += 1
            if reason:
                reason_counts[(category, reason)] += 1
    model_information_contract: dict[str, dict[str, Any]] = {}
    for model in budget["tier_1_models"]:
        for information in budget["information_conditions"]:
            probe = WorkItem(
                ordinal=0,
                item_id="manifest_probe",
                network_id="manifest_probe",
                role="development",
                source_key="manifest_probe",
                target_station="manifest_probe",
                model=str(model),
                gap_length=int(budget["gaps"][0]),
                placement=0,
                start_index=0,
                information_condition=str(information),
            )
            contract = _cell_contract(probe)
            model_information_contract[f"{model}|{information}"] = {
                "workload_category": contract["category"],
                "information_condition_result": contract["category"] == "executable",
                "consumed_information": list(contract["consumed_information"]),
                "reason": str(contract["reason"]),
            }
    return {
        "manifest_schema": "t2_v91_open_role_workload_v3",
        "runner_contract_version": RUNNER_CONTRACT_VERSION,
        "design_id": budget["design_id"],
        "protocol_amendment": budget["protocol_amendment"],
        "design_sha256": budget["design_sha256"],
        "purpose": "pipeline_preparation_not_evidence",
        "formal_evidence": False,
        "headline_claim_licensed": False,
        "go_no_go": "NO_GO_T2_PRIMARY_EVIDENCE",
        "network_inference_status": "withheld_n_lt_100_network_interval",
        "aggregation_status": "aggregation_contract_ready_no_complete_result_set",
        "no_go_reasons": [
            f"n_open_networks_{len(networks)}_lt_100_network_interval_floor",
            "network_level_achieved_skill_aggregation_blocked_no_complete_results",
            "online_causal_full_workload_not_executed",
        ],
        "sealed_temperature_records_read": False,
        "sealed_input_roots_allowed": [],
        "input_inventory": dict(inventory),
        "n_networks": len(networks),
        "network_ids": [item.network_id for item in networks],
        "roles": dict(sorted(Counter(item.role for item in networks).items())),
        "geometry_binding": geometry_binding,
        "tier_1": {
            "models": list(budget["tier_1_models"]),
            "gaps": list(budget["gaps"]),
            "placements_per_cell": int(budget["placements"]),
            "placement_roster_scope": "one_common_roster_per_network_target_gap",
            "placement_eligibility": "strict_B_union_D_then_shared_across_all_information_conditions",
            "placement_shortfall_policy": "same_placement_slots_blocked_for_every_information_condition",
            "information_conditions": list(budget["information_conditions"]),
            "information_semantics": {
                "B": "observed_target_boundaries_around_the_planted_gap",
                "D": "same_network_donor_station_values_during_the_planted_gap",
                "B_union_D": "both_boundary_and_donor_inputs_must_be_consumed",
                "B_union_D_union_M": "blocked_until_meteorology_M_is_bound",
                "B_union_D_union_M_union_H": "blocked_until_M_and_hydraulics_H_are_bound",
            },
            "model_information_contract": model_information_contract,
            "climatology_role": "train_only_skill_denominator_not_an_information_condition_result",
            "climatology_computed_inside_each_executable_model_cell": True,
            "checkpoint_namespace": "checkpoints_v3",
            "legacy_checkpoint_namespaces_ignored": ["checkpoints", "checkpoints_v2"],
            "task_executable_now": "offline_archival_and_bounded_online_causal",
            "online_causal_status": "runner_ready_full_results_missing",
            "online_causal_runner_contract": "t2_v91_online_causal_runner_v1",
            "online_causal_manifest": "results/framework/t2_online_causal_v1/workload_manifest.json",
            "n_work_items": n_items if count_items else None,
            "workload_item_identity_sha256": (
                workload_digest.hexdigest() if count_items else None
            ),
            "work_item_identity_sha256": (
                workload_digest.hexdigest() if count_items else None
            ),
            "work_items_by_geometry": dict(sorted(geometry_item_counts.items())),
            "n_executable": category_counts["executable"] if count_items else None,
            "n_reference": category_counts["reference"] if count_items else None,
            "n_not_applicable": (
                category_counts["structural_not_applicable"] if count_items else None
            ),
            "n_data_ineligible": (
                category_counts["data_ineligible"] if count_items else None
            ),
            "n_external_dependency": (
                category_counts["external_dependency"] if count_items else None
            ),
            "reason_counts": {
                "|".join(key): value for key, value in sorted(reason_counts.items())
            },
            "counts_by_role_model_information": {
                "|".join(key): value for key, value in sorted(counts.items())
            },
        },
        "geometry_dependencies": {
            "artificial_stress": "ready",
            "natural_outage": "ready_frozen_catalog_bound",
            "adversarial_stress": "ready_frozen_catalog_bound",
        },
        "dependency_audit": {
            "numpy": True,
            "pandas": True,
            "scipy_pchip": True,
            "statsmodels_kalman": True,
            "sklearn_donor": True,
            "xgboost": bool(XGBoostBaseline.is_available()),
            "meteorology_M": False,
            "hydraulics_H": False,
        },
        "primary_evidence_forbids": list(budget["primary_evidence_forbids"]),
    }


def _hash_order(seed: int, value: str) -> str:
    return _sha256_bytes(f"{int(seed)}|{value}".encode())


def lock_tier2_sample(repo_root: str | Path, *, n_target: int = 30) -> dict[str, Any]:
    """Select Tier-2 only from frozen catalog fields; never inspect data availability."""

    repo = Path(repo_root).resolve()
    budget = load_v91_budget(repo)
    path = repo / CATALOG_RELATIVE_PATH
    catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
    if catalog.get("status") != "locked_before_download":
        raise ValueError("Tier-2 selection requires the pre-download catalog lock")
    eligible_roles = {"development", "validation", "sealed"}
    fields = ("network_id", "role", "climate_band", "regulation_stratum", "size_tertile")
    rows = [
        {field: item[field] for field in fields}
        for item in catalog.get("networks", [])
        if item.get("role") in eligible_roles and not item.get("never_sealed", False)
    ]
    if len(rows) < n_target:
        raise ValueError("frozen catalog has fewer networks than the Tier-2 target")
    seed = int(catalog["seed"])
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (row["climate_band"], row["regulation_stratum"], row["size_tertile"])
        grouped[key].append(row)
    quotas: dict[tuple[str, str, str], int] = {}
    fractions: list[tuple[float, str, tuple[str, str, str]]] = []
    for key, group in grouped.items():
        exact = n_target * len(group) / len(rows)
        quotas[key] = math.floor(exact)
        fractions.append((exact - quotas[key], _hash_order(seed, "|".join(key)), key))
    remainder = n_target - sum(quotas.values())
    for _, _, key in sorted(fractions, key=lambda item: (-item[0], item[1]))[:remainder]:
        quotas[key] += 1
    selected: list[dict[str, Any]] = []
    for key, group in grouped.items():
        ordered = sorted(group, key=lambda row: _hash_order(seed, row["network_id"]))
        selected.extend(ordered[: quotas[key]])
    selected.sort(key=lambda row: row["network_id"])
    if len(selected) != n_target:
        raise AssertionError("Tier-2 proportional allocation did not reach n_target")
    sample_sha = _canonical_sha(selected)
    return {
        "manifest_schema": "t2_v91_tier2_postdownload_metadata_sample_freeze_v2",
        "status": "retrospective_metadata_only_sample_freeze_not_preregistered",
        "design_id": budget["design_id"],
        "protocol_amendment": budget["protocol_amendment"],
        "catalog_path": str(CATALOG_RELATIVE_PATH),
        "catalog_file_sha256": _sha256_file(path),
        "catalog_declared_sha256": catalog.get("sha256"),
        "selection_seed": seed,
        "selection_rule": "proportional_largest_remainder_by_climate_x_regulation_x_size_then_seeded_sha256",
        "selection_fields_only": list(fields),
        "data_availability_inspected": False,
        "preregistered": False,
        "sample_locked_before_download": False,
        "sample_frozen_before_tier2_model_execution": True,
        "timing_exception_ledger": "tier2_timing_exception_ledger.json",
        "n_networks": len(selected),
        "n_target": int(budget["tier_2"]["n_target"]),
        "n_allowed_range": list(budget["tier_2"]["n_allowed_range"]),
        "sample_sha256": sample_sha,
        "models": list(TIER2_MODELS),
        "pgdl_or_graph_wavenet": budget["tier_2"]["pgdl_or_graph_wavenet"],
        "gaps_all_required": list(TIER2_GAPS),
        "purpose": budget["tier_2"]["purpose"],
        "not_t2_primary_y": True,
        "deep_models_run": False,
        "sealed_temperature_records_read": False,
        "sample": selected,
        "role_counts": dict(sorted(Counter(row["role"] for row in selected).items())),
    }


def tier2_timing_exception_ledger(sample: Mapping[str, Any]) -> dict[str, Any]:
    """Document why the Tier-2 sample is fixed but not preregistered."""

    return {
        "manifest_schema": "t2_v91_tier2_timing_exception_ledger_v1",
        "ledger_id": "T2-TIER2-TIMING-001",
        "status": "acknowledged_protocol_deviation",
        "design_id": sample["design_id"],
        "protocol_amendment": sample["protocol_amendment"],
        "deviation": "tier2_sample_artifact_instantiated_after_open_role_downloads_started",
        "sample_sha256": sample["sample_sha256"],
        "sample_preregistered": False,
        "sample_may_be_called_preregistered": False,
        "sample_frozen_before_tier2_model_execution": True,
        "selection_used_metadata_and_roles_only": True,
        "data_availability_inspected": False,
        "sealed_entries_are_metadata_only": True,
        "sealed_temperature_records_read": False,
        "deep_models_run": False,
        "required_reporting": (
            "Describe this as a post-download metadata-only fixed sensitivity sample, "
            "not as a sample locked before download or a preregistered Tier-2 sample."
        ),
        "resolution": "retain_fixed_sample_and_disclose_timing_exception_no_reselection",
        "formal_evidence": False,
    }


__all__ = [
    "ALLOWED_INPUTS",
    "BASE_INFORMATION_CONDITIONS",
    "FAILURE_CLOSURE_INPUTS",
    "TIER1_MODELS",
    "OpenNetwork",
    "WorkItem",
    "build_workload_manifest",
    "deterministic_placements",
    "discover_failure_closure_networks",
    "discover_open_networks",
    "execute_item",
    "iter_all_work_items",
    "iter_frozen_geometry_work_items",
    "iter_work_items",
    "json_safe",
    "load_t2_geometry_workload",
    "load_v91_budget",
    "lock_tier2_sample",
    "read_panel",
    "run_items",
    "tier2_timing_exception_ledger",
]
