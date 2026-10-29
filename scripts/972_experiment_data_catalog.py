#!/usr/bin/env python3
"""Inventory the current experiment artifacts without changing scientific data.

Row counts, hashes, missingness and declared/candidate key uniqueness are read
from current files. A catalog is an inventory, not scientific acceptance.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'results/wrr_process_experiments_20261029'
EXCLUDE={'dataset_catalog.csv','data_dictionary.csv','dataset_catalog_report.json','validation.json','delivery_check.json','current_version_manifest.json','requirements_audit.json'}
K=['station_key','replicate','independence_group']
SPECS={
 'target_crps_grid_cases':(['station_key','year','region','method','seed','count','grid'],'一个目标案例×方法层×桥接seed/budget×CRPS积分网格的分数'),
 'target_crps_grid_summary':(['method','seed','count','grid','region'],'同一固定年度分布在不同CRPS积分网格上的汇总；pooled_27与地区行不相加'),
 'annual_inputs':(K+['year'],'一个档案×年度的固定H30参考/保存预测/缺口与暖季选择状态；冻结重放输入'),
 'time_archive_accounting':(K,'一个前推控制缺口档案；包含所有820档案的分母状态'),
 'time_all_feasible_subsets':(K+['subset_id'],'一个档案的一种同数可行选年集合'),
 'time_fixed_geometry_selections':(K+['scheme'],'一个档案×固定选年策略'),
 'time_exact_random_expectations':(K+['scheme'],'一个档案内均匀随机选集的精确期望'),
 'time_random_selection_draws':(K+['draw_seed'],'一个档案×随机选年种子'),
 'time_sensitivity_summary':(['scope','weighting','scheme'],'一个队列×权重×策略的汇总'),
 'time_sensitivity_paired_cluster':(['scope','weighting','scheme','field'],'一个队列×权重×策略×误差字段的配对RMSE对比'),
 'time_random_seed_summary':(['scope','weighting','draw_seed'],'一个队列×权重×完整随机选年实现'),
 'time_random_selection_variation':(['scope','weighting'],'一个队列×权重的200种子选择变异'),
 'time_secondary_leave_group_out':(['removed_group','scheme'],'删除一个连接群组后的固定预测对比'),
 'time_availability_burden':(['cohort'],'一个分母/支持子集的全保留误差'),
 'gap_overlap_station_year_cases':(['source','replicate','station_key','year'],'观测不完整站年或试验不完整站年×掩码重复'),
 'gap_overlap_summary':(['source','period'],'一个来源×时期的年度最长缺口/同日重叠汇总'),
 'gap_overlap_by_replicate':(['source','period','replicate'],'一个来源×时期×掩码重复的缺口汇总'),
 'source_role_cases':(['calibration_region','case_id'],'一个目标地区模型的正权来源区间校准案例'),
 'source_union_cases':(['case_id'],'来源校准池去重案例；保留来源特征和已修复历史轨迹'),
 'frozen_source_reference':(['case_id'],'当前内容冻结的最小来源参考；2370原native20案例的副本，不是新增实测'),
 'frozen_target_manifest':(['station_key','year'],'当前内容冻结的27目标站年索引；含固定D2/native参考及本轮目标NPZ路径，不是新增目标'),
 'historical_source_fallbacks':(['calibration_region','cell'],'历史来源校准单元及回退池'),
 'fixed_target_cases':(['station_key','year'],'一个固定目标站年；原27案例不因结果筛选'),
 'source_frozen_manifest':(['case_id'],'来源案例至冻结日数组的索引'),
 'source_native20_checks':(['case_id'],'一个来源案例的历史原生20轨迹复现核对'),
 'source_nested_draws':(['case_id','seed'],'一个来源案例×桥接随机种子的500轨迹及原生20参考'),
 'source_nested_quantiles':(['case_id','seed','count'],'一个来源案例×种子×前缀轨迹预算的七分位数'),
 'source_pool_availability':(['case_id','seed'],'来源案例×种子的预算可用性核对'),
 'source_unavailable_cases':(['case_id','seed'],'来源不可用案例台账；允许有列但零行'),
 'source_reestimated_offsets':(['region','seed','count','cell'],'一个原来源角色模型×种子×预算×校准单元的七个偏移'),
 'target_native20_checks':(['station_key','year'],'目标站年的历史原生20轨迹复现核对'),
 'target_nested_draws':(['station_key','year','seed'],'目标站年×桥接种子的500轨迹'),
 'target_historical_reference':(['station_key','year','method'],'目标站年×历史原生20经典法或固定D2参考'),
 'target_three_layer_cases':(['station_key','year','seed','count','layer'],'目标站年×种子×预算×校准层的配对评分'),
 'target_three_layer_summary':(['seed','count','layer','region','reconstructor'],'种子×预算×校准层×地区/重建器的等案例评分汇总'),
 'target_budget_case_deltas':(['station_key','year','seed','layer','comparison'],'同种子同层的目标预算配对变化'),
 'target_budget_tail_summary':(['seed','layer','comparison','region','reconstructor'],'分层预算尾端变化汇总'),
 'target_source_offset_stage_contrasts':(['station_key','year','seed','count','metric'],'固定目标轨迹下，重估偏移减旧偏移的阶段对比'),
 'region_standardized':(['matching','weighting','region','method'],'共同单元标准化后的地区×方法汇总'),
 'independent_regional_standardization':(['matching','region','weighting','method'],'独立直接计算的共同单元标准化汇总'),
 'region_balance_categorical':(['matching','weighting','field'],'一个共同支持/权重条件×分类字段的平衡诊断'),
 'region_balance_continuous':(['matching','weighting','field'],'一个共同支持/权重条件×连续字段的平衡诊断'),
 'region_common_cells':(['matching','cell'],'一个共同支持单元的地区频数和统一目标质量'),
 'region_composition':(['field','region','stratum'],'一个字段×地区×层的原案例比例'),
 'region_support_loss':(['matching','region'],'一个共同支持定义×地区的支持损失'),
 'region_matched':(['matching','region','part','method'],'共同支持筛选后的描述汇总；不等于组成平衡'),
 'region_hidden_matched':(['matching','region','part','method'],'隐藏峰分层的共同支持描述汇总'),
 'region_policy_hidden':(['region','peak_hidden','policy_choice','method'],'地区×峰可见性×重建器×方法的描述汇总'),
 'region_protocol':(['region'],'一个地区的原案例/元数据构成'),
 'region_training_support':(['region','policy_choice'],'地区×重建器的历史支持描述'),
 'regional_leave_group_out':(['omitted_group','matching'],'删除一个群组后重新定义共同支持和共同权重的影响诊断'),
 'independent_training_year_balance_checks':(['matching','weighting'],'两种实现的训练年平衡统计之差；不是已达到平衡'),
 'regional_input_field_denominators':(['region','field'],'地区×字段的有限值分母核对'),
 'water_air_complete_years':(['station_key','year'],'唯一完整水温/气温H30站年；掩码重复去重'),
 'water_air_denominator_audit':(['station_key','year'],'去重站年的有限值/重复来源行数核对'),
 'water_air_station_period_moments':(['region','station_key','period'],'站点×前后时期的充分矩；不含独立新观测'),
 'water_air_summary':(['region','period','centering','bootstrap_unit'],'年度水气关系×时期×中心化×重采样单位'),
 'water_air_paired_changes':(['region','centering','bootstrap_unit','contrast'],'携带同一单位两个时期的配对年度关系变化'),
 'water_air_direct_observation_bootstrap_checks':(['region','period','centering','unit','metric'],'逐观测重建与矩实现的重采样数值差异'),
 'water_air_weight_and_leave_group_sensitivity':(['region','analysis','omitted_group'],'年度等权/站点总权重相等/删群组的站内年度关系；基线omitted为空'),
}


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def group_description(relative):
    s=str(relative)
    if s.startswith('time_frozen_replay/'):
        return 'B_frozen_saved_annual_replay','current_content_annual_input_or_replay_metadata','scripts/977_replay_time_support.py; time_frozen_replay/freeze_manifest.json',\
            '同一820档案年度输入；807共同/805实际遮挡/468可选择层，均匀子集期望先档案内平均MSE',\
            '当前派生内容冻结，不认证历史来源；此闭包复算选年/斜率，不重训、不覆盖200seed/群组CI或实际日缺口审计'
    if s.startswith('source_calibration/'):
        if any(token in s.lower() for token in ('probe','counterfactual','independence')):
            role='counterfactual_or_dependency_audit_not_new_observation'
        elif relative.name=='frozen_source_reference.parquet':role='current_frozen_source_reference_not_new_cases'
        elif relative.name=='frozen_target_manifest.csv':role='current_frozen_target_reference_not_new_cases'
        elif relative.suffix=='.npz':role='frozen_daily_array_replay_input_not_new_observation'
        elif relative.suffix in {'.json','.log'}:role='current_execution_freeze_or_replay_metadata_not_new_observation'
        else:role='target_scoring' if ('target' in relative.name or relative.name=='fixed_target_cases.csv') else 'source_calibration_or_replay'
        if '/pilot/' in s:role='pilot_not_full_calibration'
        return 'C_source_calibration',role,'scripts/968_process_source_calibration.py; source_calibration/plan.json',\
            '来源偏移使用原正权来源角色及calibration_weight；目标评分在同一目标集合内等案例，不把18/9两层等权混成27例',\
            '源案例须原区间校准正权、原可用性、2009及以前、与目标群组分离；目标固定27例。native20另核对，不当作nested20'
    if s.startswith('region_water/'):
        role='inherited_baseline_snapshot' if '/baseline_snapshot/' in s else ('new_influence_or_independent_audit' if '/regenerated/' not in s else 'regenerated_primary_baseline')
        return 'A_and_annual_water_air',role,'scripts/audit_region_water_experiments.py; scripts/960_process_region_identification.py; scripts/process_review_water_air.py',\
            '地区：raw案例等权、min_count共同单元质量或equal_cell；水气：唯一站年等权主估计，等站点总权重/删群组是敏感性',\
            '共同支持要求两地区都有单元；有限值/元数据冲突需明确拒绝。水气仅完整、有限且去重站年；FOEN仅两群组'
    if relative.name.startswith('gap_'):
        return 'observed_and_trial_gaps','daily_missingness_accounting','scripts/969_time_gap_sensitivity.py; eligible_station_years.csv; canonical archive_daily.parquet; saved forward designs',\
            '观测每不完整站年一权；试验每不完整站年×掩码重复一权；同日比例限有同群可评价peer的分母',\
            '年度最长缺口不与段长混列；主2010–2025、观测1981–2025补充；单站群组年从新同日指标分母排除'
    if relative.name.startswith('time_'):
        return 'B_year_set_sensitivity','saved_prediction_sensitivity','scripts/969_time_gap_sensitivity.py; saved D2 annual predictions; unique reference H30; prior revision retained sets',\
            '精确随机先档案内均匀可行集合平均MSE，再按equal_archive/equal_station/equal_group跨档案汇总；200种子只示选择变异',\
            '820总档案、807原共同、805实际遮挡、468非平凡选择；13暖季仅3/4年保持不可评价，2零遮挡单列'
    return 'audit_or_delivery','metadata_or_independent_audit','见该文件和本轮脚本；不据文件名推定额外科学验证',\
        'not_applicable','最终整体状态以实际生成的validation.json为准；本目录清单不替代验收'


def resolve_key(relative,frame):
    stem=relative.stem
    if stem in SPECS:return SPECS[stem][0],SPECS[stem][1],'declared'
    if relative.parent.name=='station_parts':
        if stem.endswith('_draws'):return ['case_id','seed'],'单站来源案例×种子的轨迹分片','declared'
        if stem.endswith('_manifest'):return ['case_id'],'单站来源案例至冻结数组的索引分片','declared'
        if stem.endswith('_native20_checks'):return ['case_id'],'单站来源案例的历史20轨迹核对分片','declared'
    possible=['check','scope','matching','weighting','region','period','centering','unit','metric','seed','count','layer','case_id','station_key','year','replicate','scheme','method','omitted_group']
    columns=[x for x in possible if x in frame]
    if columns and not frame.duplicated(columns).any():
        return columns,'候选标识字段组合；详见生成器，清单不赋予新的科学统计单位','candidate_not_declared'
    return [],'not_applicable_or_documented_feature','not_documented'


def unit_and_definition(relative,column):
    name=column.lower();is_time=relative.name.startswith('time_');is_c='source_calibration' in relative.parts
    is_water=relative.name.startswith('water_air')
    ids={'station_key','case_id','region','network_id','independence_group','calibration_region','reconstructor','policy_choice','design_family','realization_id','difficulty','cell','scheme','method','matching','weighting','source','period','training_partition','analysis','layer','comparison','contrast','status','exclusion_reason','comparison_status','omitted_group','omitted_region','removed_group','cohort','reason','field','metric','unit','bootstrap_unit'}
    if relative.parent.name=='time_frozen_replay' and relative.stem=='annual_inputs':
        if column in {'truth_h30','d2_point_h30','point_h30'}:
            return 'degC','年度H30；truth用于评价，d2_point仅保存缺口年预测，point在完整年保留观测而在缺口年使用D2'
        if column in {'missing','warm_keep','original_all_evaluable','original_warm_evaluable'}:
            return 'dimensionless','布尔状态；保留原五年可评价阈值，不能将不可评价暖季集合当零误差'
    if column in ids:return 'not_applicable','标识或分类；不能将类别或行数自动解释为独立样本'
    if column in {'seed','bridge_seed','draw_seed'}:return 'not_applicable','随机流编号；桥接或选年种子不是掩码重复，也不是独立气候'
    if column=='grid':return 'probability_grid_points','CRPS概率积分点数，区别于残差桥接路径预算count，不是新观测或新Monte Carlo seed'
    if is_c and column=='crps':return 'degC','固定七分位数与边界/外尾假设的CRPS积分结果；不是全档案趋势误差'
    if column=='replicate':return 'not_applicable','整档案掩码重复编号；与随机流种子分开'
    if column=='residual_index':return 'index','来源数组行指向residual_*历史数组的索引；不是温度'
    if column in {'case_position','local_position','station_index'}:return 'index','固定数组或历史生成器中的位置索引；不是新的观测样本'
    if is_c and column=='stochastic_h30_draws':return 'degC','原生native20桥接路径的年度H30数组；不是nested500的前20条'
    if is_c and column in {'observed','mean','residual'}:
        return 'degC','冻结日数组：可见日温度、条件日均值或日残差历史；隐藏温度保持NaN，不作为真值补入'
    if name in {'n_complete_years','mean_complete_training_years','training_year_mean','original_training_year_mean','n_complete','n_full','n_warm','n_incomplete','n_retained','k'}:
        return 'years','年份计数；n_complete_years为案例训练年数，不能当含留出年的档案完整年数'
    if name=='n' or name.startswith('n_') or name.endswith('_valid_draws'):
        return 'count_or_index','明确的计数或有效重复数；n_covered等不能当覆盖比例'
    if column in {'mask_runs','original_mask_runs','missing_runs_zero_based'}:return 'zero_based_day_index:days','分号分隔start:length；start从0计；连续相邻/重叠段按日期并集核算'
    if column.endswith('sha256') or column in {'input_file','training_split','full_years','complete_years','candidate_incomplete_years','retained_years','chosen_incomplete_years','training_years'}:
        return 'not_applicable','校验和、路径、时期或分号分隔年份索引；不作为误差值'
    if column in {'year','year_min','year_max','mean_year'}:return 'calendar_year','日历年；均值可为非整数'
    if name=='source_offset_change':return 'documented_feature','单位由metric决定；分位数/温度评分为degC，covered90为0/1变化，须联接metric'
    if column in {'point_difference','low_difference','high_difference'} and 'bootstrap_checks' in relative.stem:
        return 'documented_feature','两实现的统计数值差异；单位由metric决定，不是物理时期变化'
    if is_time:
        if name in {'estimate_mse','year_set_mse','reconstruction_mse','all_estimate_mse','cross_term','mse_identity_residual'}:
            return '(degC/decade)^2','斜率平方误差或有符号交叉项；E=S+R，不作独立因果份额'
        if any(x in name for x in ['rmse','estimate_error','year_set_error','reconstruction_error','all_estimate_error']) or name.startswith('group_percentile_'):
            return 'degC/decade','有限记录斜率误差/RMSE；paired表端点为对照减暖季的RMSE差区间'
        if name=='sxx':return 'decade^2','对保留年份中心化并除10后平方和；包括固定完整年'
        if name in {'end_abs_weight','max_abs_weight'}:return '1/decade','OLS斜率的年份权重绝对值摘要'
        if name=='span':return 'years','保留年份最大值减最小值'
        if name in {'cdf_distance','uniform_subset_probability'}:return 'dimensionless','仅年份的CDF距离或档案内均匀选集概率'
    if is_water and name.startswith('slope'):return 'degC_water/degC_air','站年H30关联斜率；站内中心化按站点×时期，不是日重建系数'
    if column=='calibration_weight':return 'multiplicity','原来源角色群组bootstrap带来的整数重复权重；不是目标校准权重'
    if name.endswith('_pp') or name=='difference_pp':return 'percentage_points','覆盖率百分数之差；不与fraction混用'
    if any(x in name for x in ['fraction','coverage','covered','correlation','_corr','total_variation','weighted_ks']) or name in {'smd','residual_phi','fallback','peer_evaluable','actual_mask','primary','original_common','nontrivial_choice','finite','included','finite_water','finite_air','availability_unchanged','original_native20_available','nested500_available'}:
        return 'dimensionless','比例通常存0–1；covered90为0/1；相关、AR系数、标准化差或布尔状态按字段定义解释'
    if is_c and (re.fullmatch(r'(q|offset|change_vs_native)\d{2}',name) or re.search(r'^(d2|stochastic_cal|stochastic_h30)_q\d{2}$',name)
                 or name in {'truth','bound','bias','mae','width90','crps256_normal','interval_score90','draws','native20','historical_native_draws','residual_mu','residual_sigma','observed','mean'}
                 or name.startswith('residual_') and name[9:].isdigit()
                 or name.startswith(('delta_q','abs_delta_q','delta_mae','delta_width90','delta_crps','mean_mae_minus','mean_crps_minus','median_abs_q','max_abs_q','median_abs_delta_q','max_abs_delta_q','native20_max_abs_','q05_','q50_','q95_','width90_','crps256_normal_','mean_width'))):
        return 'degC','年度H30、日温度/残差、分位数偏移或温度评分；mae在案例行是绝对误差，在汇总行才是平均值'
    if name in {'eval_truth_h30','air_h30_target_year','air_h30_mean','water_h30_mean','residual_sd','residual_sd_low','residual_sd_high','residual_sd_difference','residual_sd_difference_low','residual_sd_difference_high'}:
        return 'degC','年度H30或年度关系残差尺度；水气H30最大窗口不保证同日'
    if name in {'mae','bias','width90'} or name.startswith(('mae_','bias_','width90_')):
        return 'degC','年度H30温度误差/区间宽度；不是趋势误差'
    if any(x in name for x in ['longest','missing_days','station_days','residual_days']) or column=='finite_residual_days':
        return 'days','连续缺测长度或站日计数，具体分母见文件grain与支持条件'
    if name in {'n_complete_years','mean_complete_training_years','training_year_mean','original_training_year_mean','n_complete','n_full','n_warm','n_incomplete','n_retained','k'}:
        return 'years','年份计数；n_complete_years为案例训练年数，不能当含留出年的档案完整年数'
    if name.startswith(('n_','n')) and (name=='n' or name.startswith('n_')) or name in {'cases','stations','groups','count','random_draws','bootstraps','bootstrap_draws','draws','mask_rows','positive_valid_cell_cases','selected_pool_cases','weighted_pool_rows','source_cases','station_index','case_position','residual_index','local_position','subset_id','replicates','groups_both_periods','stations_both_periods','bootstrap_units','informative_within_stations'} or name.endswith(('_valid_draws','_n')):
        return 'count_or_index','计数/位置索引；统计独立性由grain及群组决定，不能按数值行数推断'
    return 'documented_feature','未从名称推断单位；以生成器和字段原协议为准'


def describe_table(relative,frame):
    key,grain,kind=resolve_key(relative,frame)
    if key and set(key).issubset(frame):
        duplicates=int(frame.duplicated(key,keep=False).sum())
        missing=int(frame[key].isna().any(axis=1).sum())
        unique=len(frame.drop_duplicates(key))
        status='verified_unique' if duplicates==0 else 'duplicate_keys'
        if not len(frame):status='verified_empty_table'
    else:
        key=[];duplicates=missing=unique='not_applicable';status='not_documented'
    return dict(row_count=len(frame),column_count=len(frame.columns),grain=grain,key_kind=kind,
                key_columns=json.dumps(key,ensure_ascii=False),key_status=status,unique_key_rows=unique,
                duplicate_key_rows=duplicates,missing_key_rows=missing)


def generate(folder):
    catalog=[];dictionary=[]
    paths=sorted(path for path in folder.rglob('*') if path.is_file() and path.name not in EXCLUDE
                 and 'delivery_logs' not in path.relative_to(folder).parts
                 and not path.name.endswith(('.partial','.tmp')))
    for path in paths:
        relative=path.relative_to(folder);group,role,source,weight,support=group_description(relative)
        row=dict(dataset_path=str(relative),file_group=group,format=path.suffix.lstrip('.'),bytes=path.stat().st_size,
                 sha256=digest(path),analysis_role=role,source=source,weight_definition=weight,support_and_missingness=support)
        columns=[]
        if path.suffix in {'.csv','.parquet'}:
            frame=pd.read_csv(path) if path.suffix=='.csv' else pd.read_parquet(path)
            row.update(describe_table(relative,frame))
            for col in frame:
                unit,definition=unit_and_definition(relative,col);series=frame[col]
                nonfinite=int((~np.isfinite(series.to_numpy(float))).sum()) if pd.api.types.is_numeric_dtype(series) else 'not_applicable'
                dictionary.append(dict(dataset_path=str(relative),file_group=group,column=col,dtype=str(series.dtype),unit=unit,
                                       definition=definition,missing_count=int(series.isna().sum()),nonfinite_count=nonfinite,
                                       is_key=col in json.loads(row['key_columns']),analysis_role=role))
        elif path.suffix=='.npz':
            grain=('固定目标站年的日数组包；observed/mean/residual按日索引' if 'frozen_target_inputs' in relative.parts else
                   '来源站年日数组包；observed/mean按case_position×day，residual_index指向residual_*；联接source_frozen_manifest')
            row.update(dict(row_count='not_applicable',column_count='not_applicable',grain=grain,
                            key_kind='not_applicable',key_columns='[]',key_status='not_applicable',unique_key_rows='not_applicable',duplicate_key_rows='not_applicable',missing_key_rows='not_applicable'))
            with np.load(path,allow_pickle=False) as arrays:
                row['column_count']=len(arrays.files)
                for col in arrays.files:
                    a=arrays[col];unit,definition=unit_and_definition(relative,col)
                    dictionary.append(dict(dataset_path=str(relative),file_group=group,column=col,dtype=str(a.dtype),unit=unit,
                                           definition=definition+'; shape='+json.dumps(a.shape),missing_count=int(np.isnan(a).sum()) if a.dtype.kind=='f' else 0,
                                           nonfinite_count=int((~np.isfinite(a)).sum()) if a.dtype.kind in 'fi' else 'not_applicable',is_key=False,analysis_role=role))
        else:
            row.update(dict(row_count='not_applicable',column_count='not_applicable',grain='metadata_or_execution_artifact',key_kind='not_applicable',
                            key_columns='[]',key_status='not_applicable',unique_key_rows='not_applicable',duplicate_key_rows='not_applicable',missing_key_rows='not_applicable'))
        catalog.append(row)
    c=pd.DataFrame(catalog);d=pd.DataFrame(dictionary)
    c.to_csv(folder/'dataset_catalog.csv',index=False);d.to_csv(folder/'data_dictionary.csv',index=False)
    report=dict(created_utc=datetime.now(timezone.utc).isoformat(),status='inventory_generated_not_scientific_validation',
                catalogued_artifacts=len(c),tabular_artifacts=int(c.format.isin(['csv','parquet']).sum()),dictionary_fields=len(d),
                declared_key_violations=c.loc[c.key_kind.eq('declared')&c.key_status.eq('duplicate_keys'),'dataset_path'].tolist(),
                unresolved_key_tables=c.loc[c.key_status.eq('not_documented'),'dataset_path'].tolist(),
                unknown_unit_policy='Unknown units remain documented_feature; metadata has not_applicable. No numerical unit is inferred from numeric dtype alone.',
                exclusions=sorted(EXCLUDE),exclusion_reason='Avoid self-hash cycles; final validation, delivery reports/logs and version manifests are acceptance artifacts outside this scientific-data inventory.',
                final_validation='Consult validation.json when actually produced; this catalog does not assert that future validation passed.',
                output_sha256={name:digest(folder/name) for name in ['dataset_catalog.csv','data_dictionary.csv']},
                generator_sha256=digest(Path(__file__).resolve()))
    (folder/'dataset_catalog_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=DEFAULT);args=p.parse_args()
    report=generate(args.root)
    print(json.dumps({key:report[key] for key in ['status','catalogued_artifacts','tabular_artifacts','dictionary_fields','declared_key_violations','unresolved_key_tables']},ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
