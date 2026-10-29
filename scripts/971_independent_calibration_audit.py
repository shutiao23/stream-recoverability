#!/usr/bin/env python3
"""Independently audit source-role offsets and the same-target annual scores.

Does not import 968 or call its offset/calibration functions. Weighted endpoint
ranks use cumulative integer counts, not replication plus np.quantile. Scoring
uses direct two-sample absolute distances for the 256-point annual CRPS.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import norm
from stream_recoverability.experiments.tr_revision.baselines import ar1_bridge

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/wrr_process_experiments_20261029/source_calibration"
SOURCE = ROOT / "results/wrr_review_completion_20261024"
ARCHIVE = ROOT / "results/wrr_review_response_20261027/whole_archive"
IDENTITY = ["network_id", "station_key", "year", "design_family", "realization_id", "policy_choice", "mask_runs"]
LEVELS = (.05, .10, .25, .50, .75, .90, .95)
QCOLS = [f"q{int(q*100):02d}" for q in LEVELS]
REGIONS = ("foen", "gkd_bayern")


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def array_digest(*arrays):
    digest=hashlib.sha256()
    for array in arrays:
        values=np.ascontiguousarray(np.asarray(array,dtype="<f8"))
        digest.update(str(values.shape).encode())
        digest.update(values.tobytes())
    return digest.hexdigest()


def native_h30(observed,mean,residual,seed):
    paths=ar1_bridge(observed,mean,residual,seed,20)
    return np.lib.stride_tricks.sliding_window_view(paths,30,axis=1).mean(axis=-1).max(axis=1)


def integer_seed(*parts):
    digits = "".join(f"{int(p) % 1000000:06d}" for p in parts)
    return int(digits) % (2**32 if len(parts) <= 4 else 2**32-5)


def project(q, bound):
    result = np.asarray(q, float).copy()
    b = np.asarray(bound, float)
    finite = np.isfinite(b)
    result[finite] = np.maximum(result[finite], b[finite, None])
    return result


def weighted_endpoint(values, weights, probability):
    values, weights = np.asarray(values, float), np.asarray(weights)
    require(np.isfinite(values).all() and np.all(weights >= 1) and np.all(weights == weights.astype(int)), "Invalid weighted order statistic")
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order].astype(np.int64))
    fractional_rank = (int(cumulative[-1])-1)*probability
    rank = int(np.ceil(fractional_rank) if probability >= .5 else np.floor(fractional_rank))
    position = int(np.searchsorted(cumulative, rank+1, side="left"))
    return float(values[order[position]])


def cell_labels(frame):
    labels = []
    for overlap, policy in zip(frame.peak_overlap, frame.policy_choice):
        bin_number = 0 if overlap <= 0 else 1 if overlap <= .25 else 2 if overlap <= .5 else 3 if overlap <= .75 else 4
        layer = policy if policy in ("air_ridge", "donor_ridge") else "other"
        labels.append(f"{bin_number}|{layer}")
    return np.asarray(labels)


def derive_offsets(source, quantiles, weights, cells):
    quantiles = project(quantiles, source.observed_lower_bound__observed_days.to_numpy(float))
    weights = np.asarray(weights, int)
    eligible = np.isfinite(quantiles).all(axis=1) & (weights > 0)
    require(eligible.sum() >= 2, "No finite positive source pool")
    labels, truth = cell_labels(source), source.eval_truth_h30.to_numpy(float)
    result, diagnostics = {}, {}
    for cell in cells:
        local = eligible & (labels == cell)
        use_local = cell != "__pooled__" and int(local.sum()) >= 50
        selected = local if use_local else eligible
        residuals = truth[selected, None] - quantiles[selected]
        result[cell] = np.asarray([weighted_endpoint(residuals[:, j], weights[selected], q) for j, q in enumerate(LEVELS)])
        diagnostics[cell] = dict(positive_valid_cell_cases=int(local.sum()), selected_pool_cases=int(selected.sum()),
                                 weighted_pool_rows=int(weights[selected].sum()), fallback=not use_local)
    return result, diagnostics


def apply_offsets(raw, bounds, labels, correction):
    bounded = project(raw, bounds)
    adjustment = np.asarray([correction.get(c, correction["__pooled__"]) for c in labels])
    adjusted = np.asarray([sorted(row) for row in bounded+adjustment], float)
    return project(adjusted, bounds)


def score(q, truth, bound):
    q = np.asarray(q, float)
    low, point, high = q[0], q[3], q[-1]
    sample_q=project(q[None,:],np.asarray([bound]))[0]
    u = (np.arange(256)+.5)/256
    samples = np.interp(u, LEVELS, sample_q)
    z, levels_z = norm.ppf(u), norm.ppf(LEVELS)
    for edge, neighbor, selected in [(0,1,u<.05), (-1,-2,u>.95)]:
        scale = (sample_q[neighbor]-sample_q[edge])/(levels_z[neighbor]-levels_z[edge])
        samples[selected] = sample_q[edge]+scale*(z[selected]-levels_z[edge])
    if np.isfinite(bound):
        samples = np.maximum(samples, bound)
    crps = np.abs(samples-truth).mean()-.5*np.abs(samples[:,None]-samples[None,:]).mean()
    return dict(bias=float(point-truth), mae=float(abs(point-truth)), width90=float(high-low),
                covered90=int(low-1e-8 <= truth <= high+1e-8), crps256_normal=float(crps),
                interval_score90=float(high-low+20*max(low-truth,0)+20*max(truth-high,0)))


def original_source():
    raw = pd.read_parquet(SOURCE / "cases/before_2010/seed_00.parquet")
    require(not raw.duplicated(IDENTITY).any(), "Original source case identity is not unique")
    raw["independent_local_position"] = raw.groupby(["network_id","station_key","year","replication_seed"],sort=False).cumcount()
    repair = pd.read_parquet(SOURCE / "repairs/before_2010/seed_00.parquet")
    require(not repair.duplicated(IDENTITY).any(), "Repair identity is not unique")
    fixed = repair.set_index(IDENTITY)
    index = pd.MultiIndex.from_frame(raw[IDENTITY])
    positions = fixed.index.get_indexer(index)
    present = positions >= 0
    cols = ["stochastic_h30_draws", *["stochastic_h30_"+c for c in QCOLS]]
    for column in cols:
        raw.loc[present,column] = fixed.iloc[positions[present]][column].to_numpy()
    raw = raw.loc[raw.policy_choice.ne("unavailable") & raw.eval_truth_h30.notna()].copy()
    raw["independent_case_id"] = [hashlib.sha256(json.dumps([str(row[c]) for c in IDENTITY],separators=(",",":")).encode()).hexdigest()[:24] for _,row in raw.iterrows()]
    return raw


def independently_rebuild_roles(source, region, config):
    held = source.region.eq(region) & source.training_partition.eq("test")
    held_groups = set(source.loc[held,"independence_group"])
    eligible = source.loc[~source.independence_group.isin(held_groups) & source.training_partition.eq("train")]
    groups = np.asarray(sorted(set(eligible.independence_group)))
    seed = integer_seed(7,0,sorted(set(source.region)|{region}).index(region))
    rng = np.random.default_rng(seed)
    rng.shuffle(groups)
    boundaries = np.maximum.accumulate(np.rint(np.cumsum(config["fit_role_shares"])[:-1]*len(groups)).astype(int))
    sections = np.split(groups,boundaries)
    assignments, multiplicities = {}, {}
    for name, section in zip(config["fit_role_names"],sections):
        assignments[name] = section.tolist()
        multiplicities[name] = Counter(rng.choice(section,len(section),replace=True).tolist())
    weights = np.asarray([multiplicities["interval_calibration"].get(g,0) if partition=="train" else 0 for g,partition in zip(source.independence_group,source.training_partition)],int)
    return sorted(held_groups), assignments, weights, seed


def audit(folder):
    full = folder / "full"
    union = pd.read_parquet(folder / "source_union_cases.parquet").set_index("case_id",drop=False)
    roles = pd.read_csv(folder / "source_role_cases.csv",float_precision="round_trip")
    source = original_source()
    indexed_source = source.set_index("independent_case_id")
    require(union.index.is_unique and set(union.index).issubset(indexed_source.index), "Union case IDs disagree with raw+repair source")
    expected = indexed_source.loc[union.index]
    for c in [*IDENTITY,"region","independence_group","training_partition"]:
        require(union[c].astype(str).tolist()==expected[c].astype(str).tolist(), "Source union identity differs: "+c)
    for c in ["eval_truth_h30","observed_lower_bound__observed_days","peak_overlap",*["stochastic_h30_"+c for c in QCOLS]]:
        require(np.allclose(union[c],expected[c],atol=1e-12,rtol=0,equal_nan=True), "Source union values differ from raw+repair: "+c)
    require(np.array_equal(union.local_position,expected.independent_local_position), "Local source seed position differs")
    require(np.array_equal(cell_labels(union),union.difficulty), "Source difficulty labels differ")
    config = json.loads((ROOT / "configs/wrr_review_completion_20261024.json").read_text())
    old = json.loads((ARCHIVE / "classical_calibration.json").read_text())["forward"]
    role_checks, original_corrections = {}, {}
    for region in REGIONS:
        held, assignment, original_weights, role_seed = independently_rebuild_roles(source,region,config)
        metadata = json.loads((SOURCE / f"refits/before_2010/seed_00/{region}.json").read_text())
        bundle = joblib.load(SOURCE / f"refits/before_2010/seed_00/{region}.joblib")
        require(assignment==metadata["roles"]==bundle["roles"], "Original role assignment differs for "+region)
        require(held==sorted(metadata["held_groups"]), "Original held groups differ")
        flattened = [g for values in assignment.values() for g in values]
        require(len(flattened)==len(set(flattened)) and not set(flattened)&set(held), "Roles or held groups overlap")
        local = roles.loc[roles.calibration_region.eq(region)].set_index("case_id")
        positive = source.loc[original_weights>0]
        require(set(local.index)==set(positive.independent_case_id), "Saved calibration rows differ from original positive role")
        original_weight_map = pd.Series(original_weights,index=source.independent_case_id)
        require(np.array_equal(local.calibration_weight.to_numpy(int),original_weight_map.loc[local.index]), "Calibration multiplicity differs from original RNG")
        values = union.loc[local.index]
        require(values.year.lt(2010).all() and values.training_partition.eq("train").all(), "Source calibration includes target-period/test data")
        cells = list(old[region]["offsets"]["stochastic"])
        corrections, _ = derive_offsets(values, values[["stochastic_h30_"+c for c in QCOLS]].to_numpy(float), local.calibration_weight.to_numpy(int), cells)
        baseline_error = max(float(np.max(abs(corrections[c]-old[region]["offsets"]["stochastic"][c]))) for c in cells)
        require(baseline_error<1e-10,"Independent historical native20 offsets differ")
        original_corrections[region] = corrections
        role_checks[region] = dict(role_seed=role_seed, positive_cases=len(local), integer_weight_sum=int(local.calibration_weight.sum()),
                                   positive_groups=int(local.independence_group.nunique()), held_groups=held, original_json_and_joblib_roles_match=True,
                                   historical_native_offset_max_error=baseline_error)
    source_draws = pd.read_parquet(full / "source_nested_draws.parquet")
    source_q = pd.read_csv(full / "source_nested_quantiles.csv",float_precision="round_trip")
    saved_offsets = pd.read_csv(full / "source_reestimated_offsets.csv",float_precision="round_trip")
    require(len(source_draws)==len(union)*3 and not source_draws.duplicated(["case_id","seed"]).any(), "Source sample collection changed")
    require(set(source_draws.case_id)==set(union.index) and set(source_draws.seed)=={0,1,2},"Source case/seed scope differs")
    require(len(source_q)==len(union)*9 and not source_q.duplicated(["case_id","seed","count"]).any(), "Source quantile collection changed")
    require(not saved_offsets.duplicated(["region","seed","count","cell"]).any(),"Duplicate source correction identity")
    require(set(zip(saved_offsets.region,saved_offsets.seed,saved_offsets["count"]))=={(r,s,n) for r in REGIONS for s in [0,1,2] for n in [20,100,500]},"Source correction factorial scope differs")
    nested_q_error, native_draw_error, native_q_error, native_nested_different = 0.,0.,0.,0
    native_nested_max = 0.
    manifest = pd.read_csv(full / "source_frozen_manifest.csv",float_precision="round_trip").set_index("case_id")
    source_q_index=source_q.set_index(["case_id","seed","count"])
    frozen_cache={}
    frozen_hashes_checked=0
    independent_native_replay_error=0.
    for case_id,m in manifest.iterrows():
        file=folder/m.input_file
        if str(file) not in frozen_cache:
            with np.load(file) as archive:
                frozen_cache[str(file)]={k:archive[k] for k in archive.files}
        arrays=frozen_cache[str(file)]
        observed=arrays["observed"][int(m.case_position)]
        mean=arrays["mean"][int(m.case_position)]
        residual=arrays[f"residual_{int(m.residual_index)}"]
        require(array_digest(observed,mean,residual)==m.input_sha256,"Frozen source daily arrays changed")
        mask=np.zeros(len(observed),bool)
        for run in str(union.loc[case_id].mask_runs).split(";"):
            start,length=map(int,run.split(":"));mask[start:start+length]=True
        require(np.isnan(observed[mask]).all(),"Source hidden target days remain observed in frozen input")
        native=native_h30(observed,mean,residual,integer_seed(9,0,m.station_index,m.year,union.loc[case_id].local_position))
        historical=np.asarray(union.loc[case_id].stochastic_h30_draws,float)
        require(np.array_equal(np.isfinite(native),np.isfinite(historical)),"Frozen input native20 availability differs")
        if np.isfinite(native).all():
            independent_native_replay_error=max(independent_native_replay_error,float(abs(native-historical).max()))
        frozen_hashes_checked+=1
    require(independent_native_replay_error<1e-8,"Native20 replay of actual frozen arrays differs from original source repair")
    for row in source_draws.itertuples(index=False):
        m, c = manifest.loc[row.case_id], union.loc[row.case_id]
        require(int(row.bridge_seed)==integer_seed(9,row.seed,m.station_index,row.year,c.local_position), "Source MC seed formula differs")
        training_years = [int(y) for y in str(m.training_years).split(";") if y]
        require(all(y<2010 and y!=row.year for y in training_years), "Frozen source local fit uses target/held year")
        draws = np.asarray(row.draws,float)
        if row.seed==0:
            native = np.asarray(row.native20,float)
            historical = np.asarray(c.stochastic_h30_draws,float)
            require(np.array_equal(native,historical,equal_nan=True),"Source native20 differs from original repaired draws")
            if np.isfinite(native).all():
                native_draw_error=max(native_draw_error,float(abs(native-historical).max()))
                native_q_error=max(native_q_error,float(abs(np.quantile(native,LEVELS)-c[["stochastic_h30_"+q for q in QCOLS]].to_numpy(float)).max()))
                difference=float(abs(native-draws[:20]).max())
                native_nested_different+=int(difference>1e-10)
                native_nested_max=max(native_nested_max,difference)
        for count in [20,100,500]:
            computed = np.quantile(draws[:count],LEVELS)
            saved = source_q_index.loc[(row.case_id,row.seed,count),QCOLS].to_numpy(float)
            require(saved.shape==(7,) and np.array_equal(np.isfinite(computed),np.isfinite(saved)), "Source quantile availability differs")
            if np.isfinite(computed).all(): nested_q_error=max(nested_q_error,float(abs(computed-saved).max()))
    require(nested_q_error<1e-10,"Saved nested source quantiles disagree with draws")
    require(native_q_error<1e-10,"Historical source native quantiles disagree with original repaired draws")
    corrections_by_key, offset_error, fallback_errors = {},0.,0
    for (region,seed,count), block in saved_offsets.groupby(["region","seed","count"]):
        require(set(block.cell)==set(old[region]["offsets"]["stochastic"]),"Source correction cell set differs from historical cells")
        local = roles.loc[roles.calibration_region.eq(region)].set_index("case_id")
        qs = source_q.loc[source_q.seed.eq(seed)&source_q["count"].eq(count)].set_index("case_id").loc[local.index,QCOLS].to_numpy(float)
        corrections, diagnostic = derive_offsets(union.loc[local.index],qs,local.calibration_weight.to_numpy(int),block.cell.tolist())
        corrections_by_key[(region,int(seed),int(count))] = corrections
        for row in block.itertuples(index=False):
            got = np.asarray([getattr(row,"offset"+c[1:]) for c in QCOLS])
            offset_error=max(offset_error,float(abs(corrections[row.cell]-got).max()))
            fallback_errors+=sum(getattr(row,key)!=value for key,value in diagnostic[row.cell].items())
    require(len(saved_offsets)==288 and offset_error<1e-10 and fallback_errors==0,"Independent offset/order-statistic/fallback audit failed")
    target = pd.read_csv(folder / "fixed_target_cases.csv",float_precision="round_trip").set_index(["station_key","year"],drop=False)
    target_draws = pd.read_parquet(full / "target_nested_draws.parquet")
    scored = pd.read_csv(full / "target_three_layer_cases.csv",float_precision="round_trip")
    baseline = pd.read_csv(full / "target_historical_reference.csv",float_precision="round_trip")
    require(len(target)==27 and len(scored)==729,"Target diagnostic denominator changed")
    require(not scored.duplicated(["station_key","year","seed","count","layer"]).any(),"Duplicate three-layer target row")
    expected_target_keys={(station,int(year),seed,count,layer) for station,year in target.index for seed in [0,1,2] for count in [20,100,500] for layer in ["uncalibrated","fixed_old_offset","reestimated_source_offset"]}
    require(set(zip(scored.station_key,scored.year,scored.seed,scored["count"],scored.layer))==expected_target_keys,"Target case/seed/count/layer factorial is incomplete")
    require(len(baseline)==54 and not baseline.duplicated(["station_key","year","method"]).any(),"Historical target reference denominator differs")
    target_original, target_native_different, target_native_max = {},0,0.
    reference=pd.read_parquet(SOURCE/"cases/leave_one_year_out/seed_00.parquet",columns=["station_key","year","design_family","eval_truth_h30"])
    reference=reference.loc[reference.design_family.eq("crossed")]
    require(reference.groupby(["station_key","year"]).eval_truth_h30.nunique(dropna=False).eq(1).all(),"Original complete-year truth is not unique")
    reference=reference.drop_duplicates(["station_key","year"]).set_index(["station_key","year"])
    empty_prediction_truth=0
    historical_target_calibration_error=0.
    for key,row in target.iterrows():
        original = pd.read_parquet(ARCHIVE / "crossed/forward/replicate_00" / row.station_key.replace("|","_") / "annual_predictions.parquet").set_index("year").loc[row.year]
        require(np.isclose(float(row.truth),float(reference.loc[key].eval_truth_h30),atol=1e-12,rtol=0),"Target truth differs from original complete-year reference")
        empty_prediction_truth+=int(not np.isfinite(original.eval_truth_h30))
        require(row.independence_group in role_checks[row.region]["held_groups"],"Target connected group is not held out")
        require(row.independence_group not in set(roles.loc[roles.calibration_region.eq(row.region),"independence_group"]),"Target group leaks into its source calibration role")
        with np.load(ROOT/"results/wrr_process_revision_20261029"/row.input_file) as frozen:
            require(array_digest(frozen["observed"],frozen["mean"],frozen["residual"])==row.input_sha256,"Frozen target inputs changed")
        require(np.isclose(float(row.bound),float(original.observed_lower_bound__observed_days),atol=1e-12,rtol=0),"Target bound differs")
        for prefix in ["D2","stochastic_cal","stochastic_h30"]:
            q = np.asarray([row[prefix+"_"+c] for c in QCOLS],float)
            expected_q = original[[prefix+"_"+c for c in QCOLS]].to_numpy(float)
            require(np.allclose(q,expected_q,atol=1e-12,rtol=0),"Fixed target quantities changed from original archive: "+prefix)
        native_raw=original[["stochastic_h30_"+c for c in QCOLS]].to_numpy(float)[None,:]
        native_cal=apply_offsets(native_raw,np.asarray([row.bound]),[row.difficulty],original_corrections[row.region])[0]
        native_saved=original[["stochastic_cal_"+c for c in QCOLS]].to_numpy(float)
        historical_target_calibration_error=max(historical_target_calibration_error,float(abs(native_cal-native_saved).max()))
        target_original[key]=original
    require(historical_target_calibration_error<1e-10,"Historical target native20 calibration does not reproduce independently")
    source_seed_set=set(map(int,source_draws.bridge_seed))
    target_seed_set=set(map(int,target_draws.bridge_seed))
    require(not source_seed_set&target_seed_set,"Source and target MC streams collide")
    for row in target_draws.itertuples(index=False):
        c=target.loc[(row.station_key,row.year)]
        require(row.bridge_seed==integer_seed(9,row.seed,c.station_index,row.year,0),"Target MC seed formula differs")
        if row.seed==0:
            native=np.asarray(target_original[(row.station_key,row.year)].stochastic_h30_draws,float)
            require(np.array_equal(native,np.asarray(json.loads(c.historical_native_draws),float)),"Target historical native draw identity differs")
            d=float(abs(native-np.asarray(row.draws,float)[:20]).max())
            target_native_different+=int(d>1e-10);target_native_max=max(target_native_max,d)
    quantile_error, metric_error, fixed_reference_error=0.,0.,0.
    for row in scored.itertuples(index=False):
        c=target.loc[(row.station_key,row.year)]
        draws=target_draws.loc[target_draws.station_key.eq(row.station_key)&target_draws.year.eq(row.year)&target_draws.seed.eq(row.seed),"draws"].iloc[0]
        raw=np.quantile(np.asarray(draws,float)[:row.count],LEVELS)[None,:]
        if row.layer=="uncalibrated": q=project(raw,np.asarray([c.bound]))[0]
        elif row.layer=="fixed_old_offset": q=apply_offsets(raw,np.asarray([c.bound]),[c.difficulty],original_corrections[c.region])[0]
        elif row.layer=="reestimated_source_offset": q=apply_offsets(raw,np.asarray([c.bound]),[c.difficulty],corrections_by_key[(c.region,row.seed,row.count)])[0]
        else: raise AssertionError("Unknown target layer")
        quantile_error=max(quantile_error,float(abs(q-np.asarray([getattr(row,qc) for qc in QCOLS])).max()))
        metrics=score(q,c.truth,c.bound)
        metric_error=max(metric_error,max(abs(metrics[k]-getattr(row,k)) for k in metrics))
        for method,prefix in [("fixed_D2","D2"),("historical_native20","stochastic_cal")]:
            b=baseline.loc[baseline.station_key.eq(row.station_key)&baseline.year.eq(row.year)&baseline.method.eq(method)].iloc[0]
            bq=np.asarray([c[prefix+"_"+qc] for qc in QCOLS])
            bm=score(bq,c.truth,c.bound)
            fixed_reference_error=max(fixed_reference_error,max(abs(bm[k]-b[k]) for k in bm))
            suffix="D2" if method=="fixed_D2" else "native20"
            for k in ["mae","covered90","width90","crps256_normal"]:
                fixed_reference_error=max(fixed_reference_error,abs((metrics[k]-bm[k])-getattr(row,"delta_"+k+"_vs_"+suffix)))
    require(quantile_error<1e-10 and metric_error<1e-10 and fixed_reference_error<1e-10,"Target quantile/scoring/D2 audit failed")
    # Observe the executed generator's source/target dataflow without invoking it.
    tree=ast.parse((ROOT / "scripts/968_process_source_calibration.py").read_text())
    analyse=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="analyse_full")
    calls=[n for n in ast.walk(analyse) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
    source_calls=[n for n in calls if n.func.id=="offsets"]
    target_calls=[n for n in calls if n.func.id in ["load_targets","target_draws"]]
    require(len(source_calls)==1 and source_calls[0].lineno<min(n.lineno for n in target_calls),"Offsets are not completed before target loading")
    require(isinstance(source_calls[0].args[0],ast.Name) and source_calls[0].args[0].id=="cases","Offset input is not the source-only cases variable")
    # Source offsets do not consume target truth. Recompute after arbitrary target
    # truth perturbation with all source inputs unchanged; compare every scalar.
    perturbed=target.copy()
    perturbed["truth"]=np.random.default_rng(971).permutation(perturbed.truth.to_numpy())+1000
    perturb_error=0.
    for (region,seed,count), reference in corrections_by_key.items():
        local=roles.loc[roles.calibration_region.eq(region)].set_index("case_id")
        qs=source_q.loc[source_q.seed.eq(seed)&source_q["count"].eq(count)].set_index("case_id").loc[local.index,QCOLS].to_numpy(float)
        again,_=derive_offsets(union.loc[local.index],qs,local.calibration_weight.to_numpy(int),list(reference))
        perturb_error=max(perturb_error,max(float(abs(again[c]-reference[c]).max()) for c in reference))
    require(perturb_error==0,"Target perturbation affected source-only independent offsets")
    return dict(status="passed", independent_of_968_functions=True, original_roles=role_checks,
                source_cases=len(union), source_nested_quantile_rows=len(source_q), source_nested_quantile_max_error=nested_q_error,
                source_frozen_array_hashes_checked=frozen_hashes_checked,
                independent_native20_frozen_input_replay_max_error=independent_native_replay_error,
                offsets_checked=len(saved_offsets), offset_scalar_values_checked=len(saved_offsets)*7, max_offset_error=offset_error, fallback_count_mismatches=int(fallback_errors),
                target_rows_checked=len(scored), target_quantile_values_checked=len(scored)*7, max_target_quantile_error=quantile_error,
                max_target_metric_error=metric_error,max_fixed_D2_native_reference_or_delta_error=fixed_reference_error,
                target_MC_seeds=len(target_seed_set),source_MC_seeds=len(source_seed_set),source_target_seed_intersection=0,
                historical_native20_source_draw_error=native_draw_error,
                historical_native20_source_quantile_error=native_q_error,
                historical_target_native20_calibration_max_error=historical_target_calibration_error,
                target_truth_source="Original LOYO seed00 crossed-mask complete-year reference, unique by station/year; not whole-archive annual prediction rows.",
                target_prediction_rows_with_intentionally_missing_truth=empty_prediction_truth,
                native20_vs_nested20=dict(source_cases_with_different_seed0_paths=native_nested_different,source_max_absolute_path_difference=native_nested_max,
                                         target_cases_with_different_seed0_paths=target_native_different,target_max_absolute_path_difference=target_native_max,
                                         interpretation="Native draws=20 and prefix20 of draws=500 are different implementations; neither is silently substituted for the other."),
                target_truth_perturbation=dict(max_source_offset_change=perturb_error,source_offset_dataflow_precedes_target_loading=True,
                                               generator_reexecuted_with_mutated_targets=False,
                                               scope="Independent source-only recomputation plus generator AST/data-provenance checks; not a claim to have rerun 968 with modified target files."),
                fixed_D2_scope="Original annual D2 seven quantiles and projected-distribution scoring are fixed; no D2 retraining/recalibration or full-archive trend comparison.",
                limits=["This audit checks saved draws, source-role identities, offsets and annual score arithmetic; it does not independently refit all source daily models.",
                        "Same 27 target station-years in two groups; 500 paths are not an infinite-draw convergence proof.",
                        "Equal normal-tail/256-point scoring is an assumed annual approximation, not a verified tail law or a general method ranking."],
                input_sha256={str(p.relative_to(ROOT)):sha(p) for p in [folder/"source_union_cases.parquet",folder/"source_role_cases.csv",folder/"fixed_target_cases.csv",full/"source_nested_quantiles.csv",full/"source_nested_draws.parquet",full/"source_frozen_manifest.csv",full/"source_reestimated_offsets.csv",full/"target_three_layer_cases.csv",full/"target_nested_draws.parquet",full/"target_historical_reference.csv",SOURCE/"cases/before_2010/seed_00.parquet",SOURCE/"repairs/before_2010/seed_00.parquet",SOURCE/"cases/leave_one_year_out/seed_00.parquet",ROOT/"configs/wrr_review_completion_20261024.json",ARCHIVE/"classical_calibration.json",ROOT/"scripts/968_process_source_calibration.py",*[SOURCE/f"refits/before_2010/seed_00/{r}.{extension}" for r in REGIONS for extension in ["json","joblib"]]]})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=OUT)
    args=parser.parse_args()
    try: report=audit(args.output)
    except (AssertionError,ValueError,KeyError,IndexError,OSError,RuntimeError) as exc: report=dict(status="failed",error=f"{type(exc).__name__}: {exc}")
    report["auditor_script_sha256"]=sha(Path(__file__))
    (args.output/"independent_audit.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return 0 if report["status"]=="passed" else 1


if __name__=="__main__":
    raise SystemExit(main())
