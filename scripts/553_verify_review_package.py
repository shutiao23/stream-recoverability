#!/usr/bin/env python3
"""Check figures, TeX, and two observation results in an extracted package.

This does NOT rebuild the main model predictions, fit models, validate all
summary inputs, or resolve data rights. The test uses the current Python and TeX environment.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from PIL import Image, ImageChops
import matplotlib
import numpy
import pandas

ROOT=Path(__file__).resolve().parents[1]
NAMES=['02_annual_comparators','03_archive_factorial','04_joint_uncertainty','05_output_boundaries']

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,default=ROOT/'dist/wrr_review_response_candidate.zip')
    p.add_argument('--require-pixel-match',action='store_true',help='Fail on raster differences as well as build errors; rendering may vary with fonts and library versions')
    p.add_argument('--output',type=Path,default=ROOT/'results/wrr_review_response_20261027/audit/package_check.json')
    a=p.parse_args()
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'archive':str(a.archive),
            'archive_sha256':hashlib.sha256(a.archive.read_bytes()).hexdigest(),
            'scope':'extracted package; Graphviz architecture, figures from supplied summaries, manuscript TeX compilation, the 95-station observation subset, seasonal-window and past-only screening comparisons, the processed-data interannual summer-regression proxy, USGS donor metadata and daily responses, the Truckee reference, POWER timing and WQP same-agency field inputs, the USACE reservoir availability and conditional H30 bounds, and the USGS observation-only replay',
            'not_tested':['full raw-data reconstruction','original source-model and daily-reconstruction fitting','other case-level scientific validation','data rights','independent accuracy validation'],
            'environment':{'python':sys.version.split()[0],'matplotlib':matplotlib.__version__,'numpy':numpy.__version__,'pandas':pandas.__version__},
            'checks':{}}
    try:
        with tempfile.TemporaryDirectory(prefix='wrr_package_verify_') as temp:
            dest=Path(temp)
            with zipfile.ZipFile(a.archive) as z:
                bad=z.testzip()
                if bad:raise RuntimeError(f'ZIP CRC failure: {bad}')
                for member in z.infolist():
                    if not (dest/member.filename).resolve().is_relative_to(dest):raise RuntimeError('Unsafe ZIP path')
                z.extractall(dest)
            report['checks']['zip_crc']='passed'
            architecture_source=dest/'paper/wrr_tr/figures/architecture/fig1_evidence_actual.dot'
            architecture_original=dest/'paper/wrr_tr/figures/architecture/fig1_evidence_actual.pdf'
            architecture_redraw=dest/'architecture_recreated.pdf'
            proc=subprocess.run(['dot','-Tpdf',str(architecture_source),'-o',str(architecture_redraw)],capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Architecture regeneration failed: '+(proc.stdout+proc.stderr)[-2000:])
            extracted=subprocess.run(['pdftotext','-layout',str(architecture_redraw),'-'],capture_output=True,text=True)
            expected=['Fixed source annual models','Hidden target days are excluded from local fitting.',
                      'Visible target and donor records remain usable.']
            if extracted.returncode or not all(text in extracted.stdout for text in expected):
                raise RuntimeError('Architecture text does not state the required fitting boundaries')
            for source,stem in [(architecture_original,'architecture_original'),(architecture_redraw,'architecture_redrawn')]:
                proc=subprocess.run(['pdftoppm','-f','1','-l','1','-singlefile','-r','100','-png',str(source),str(dest/stem)],capture_output=True,text=True)
                if proc.returncode:raise RuntimeError('Architecture raster comparison failed: '+(proc.stdout+proc.stderr)[-2000:])
            with Image.open(dest/'architecture_original.png') as original,Image.open(dest/'architecture_redrawn.png') as rebuilt:
                x,y=original.convert('RGB'),rebuilt.convert('RGB')
                architecture_match=bool(x.size==y.size and ImageChops.difference(x,y).getbbox() is None)
            report['checks']['architecture_regeneration']='passed'
            report['checks']['architecture_pixel_match']=architecture_match
            if a.require_pixel_match and not architecture_match:raise RuntimeError('Architecture pixels differ in current rendering environment')
            proc=subprocess.run([sys.executable,'scripts/654_verify_open_observed_snapshot.py','--manifest','results/wrr_process_revision_20261029/replay_integrity/open_observed_current_manifest.json'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Main observation subset audit failed: '+(proc.stdout+proc.stderr)[-3000:])
            observed=json.loads((dest/'results/wrr_review_response_20261027/audit/open_observed_reproduction.json').read_text())
            if observed.get('status')!='passed':raise RuntimeError('Main observation subset audit did not pass')
            report['checks']['main_observation_open_subset']={'status':'passed','stations':observed['included_stations'],
                'original_stations':observed['original_stations'], 'witness_station_years':observed['witness_station_years'],
                'rule_decisions_checked':observed['rule_decisions_checked']}
            proc=subprocess.run([sys.executable,'scripts/712_verify_summer_snapshot.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Summer-window snapshot replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            summer=json.loads((dest/'results/wrr_review_response_20261027/audit/summer_snapshot_reproduction.json').read_text())
            if summer.get('status')!='passed':raise RuntimeError('Summer-window snapshot replay did not pass')
            report['checks']['summer_snapshot_reproduction']={'status':'passed','complete_station_years':summer['complete_station_years'],
                'witnesses':summer['witnesses'],'tables':summer['tables_reproduced']}
            proc=subprocess.run([sys.executable,'scripts/778_donor_usgs_snapshot_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('USGS donor site metadata replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            donor=json.loads((dest/'results/wrr_review_response_20261027/audit/donor_usgs_snapshot_replay.json').read_text())
            if donor.get('status')!='passed':raise RuntimeError('USGS donor site metadata replay did not pass')
            report['checks']['usgs_donor_metadata_reproduction']={'status':'passed','identifiers':donor['metadata_identifiers'],'responses':donor['responses']}
            proc=subprocess.run([sys.executable,'scripts/784_usgs_donor_daily_snapshot_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('USGS donor daily response replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            daily=json.loads((dest/'results/wrr_review_response_20261027/audit/donor_usgs_daily_snapshot_replay.json').read_text())
            if daily.get('status')!='passed':raise RuntimeError('USGS donor daily response replay did not pass')
            report['checks']['usgs_donor_daily_response_reproduction']={'status':'passed','identifiers':daily['requested_sites'],'numeric_values':daily['numeric_source_values']}
            proc=subprocess.run([sys.executable,'scripts/805_truckee_open_reference_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Truckee public reference replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            truckee=json.loads((dest/'results/wrr_review_response_20261027/audit/truckee_open_reference_replay.json').read_text())
            if truckee.get('status')!='passed':raise RuntimeError('Truckee public reference replay did not pass')
            report['checks']['truckee_public_reference_reproduction']={'status':'passed','stations':truckee['stations'],
                'station_years':truckee['station_years'],'complete_finite_years':truckee['complete_finite_years'],'power_days':truckee['power_days']}
            proc=subprocess.run([sys.executable,'scripts/812_truckee_power_time_open_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Truckee POWER time-standard replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            clock=json.loads((dest/'results/wrr_review_response_20261027/audit/truckee_power_time_open_replay.json').read_text())
            if clock.get('status')!='passed':raise RuntimeError('Truckee POWER time-standard replay did not pass')
            report['checks']['truckee_power_time_reproduction']={'status':'passed','hour_pairs':clock['finite_hour_pairs'],'daily_pairs':clock['daily_pairs']}
            proc=subprocess.run([sys.executable,'scripts/818_truckee_wqp_open_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Truckee WQP field replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            field=json.loads((dest/'results/wrr_review_response_20261027/audit/truckee_wqp_open_replay.json').read_text())
            if field.get('status')!='passed':raise RuntimeError('Truckee WQP field replay did not pass')
            report['checks']['truckee_wqp_field_reproduction']={'status':'passed','source_rows':field['source_rows'],'comparable_rows':field['comparable_rows']}
            proc=subprocess.run([sys.executable,'scripts/829_usace_open_reference_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Reservoir public reference replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            reservoir=json.loads((dest/'results/wrr_review_response_20261027/audit/usace_open_reference_replay.json').read_text())
            if reservoir.get('status')!='passed':raise RuntimeError('Reservoir public reference replay did not pass')
            report['checks']['reservoir_public_reference_reproduction']={'status':'passed','resources':reservoir['resources'],
                'station_years':reservoir['station_years'],'complete_finite_years':reservoir['complete_finite_years']}
            proc=subprocess.run([sys.executable,'scripts/834_usace_bounds_open_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Reservoir bounds replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            reservoir_bounds=json.loads((dest/'results/wrr_review_response_20261027/audit/usace_bounds_open_replay.json').read_text())
            if reservoir_bounds.get('status')!='passed':raise RuntimeError('Reservoir bounds replay did not pass')
            report['checks']['reservoir_bounds_reproduction']={'status':'passed','station_years':reservoir_bounds['station_years'],
                'complete_days':reservoir_bounds['complete_days_recomputed'],'accepted_year_record_witnesses':reservoir_bounds['guaranteed_added_record_years_95']}
            proc=subprocess.run([sys.executable,'scripts/847_usace_partial_power_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Reservoir POWER replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            reservoir_power=json.loads((dest/'results/wrr_review_response_20261027/audit/usace_partial_power_open_replay.json').read_text())
            if reservoir_power.get('status')!='passed':raise RuntimeError('Reservoir POWER replay did not pass')
            report['checks']['reservoir_power_reproduction']={'status':'passed','resources':reservoir_power['resources'],'daily_rows':reservoir_power['daily_rows']}
            proc=subprocess.run([sys.executable,'data/external/wrr_usgs_partial_daily_20261027/scripts/890_public_usgs_reference_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('USGS partial-daily public reference replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            usgs_partial=json.loads((dest/'data/external/wrr_usgs_partial_daily_20261027/results/public_reference_replay.json').read_text())
            if usgs_partial.get('status')!='passed':raise RuntimeError('USGS partial-daily public reference replay did not pass')
            report['checks']['usgs_partial_daily_reference_reproduction']={'status':'passed','target_years':usgs_partial['target_years'],
                'day_clock_rows':usgs_partial['day_clock_rows'],'fixed_hourly_complete_years':usgs_partial['fixed_hourly_complete_years'],
                'fixed_quarter_complete_years':usgs_partial['fixed_quarter_complete_years']}
            proc=subprocess.run([sys.executable,'data/external/wrr_usgs_partial_daily_20261027/scripts/892_public_usgs_raw_daily_audit.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('USGS raw daily audit failed: '+(proc.stdout+proc.stderr)[-3000:])
            daily_raw=json.loads((dest/'data/external/wrr_usgs_partial_daily_20261027/results/raw_daily_reference_replay.json').read_text())
            if daily_raw.get('status')!='passed':raise RuntimeError('USGS raw daily audit did not pass')
            report['checks']['usgs_partial_raw_daily_reproduction']={'status':'passed','target_years':daily_raw['target_years'],'daily_rows':daily_raw['raw_daily_rows']}
            proc=subprocess.run([sys.executable,'data/external/wrr_usgs_partial_daily_20261027/scripts/901_public_subdaily_bounds_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('USGS conditional subdaily bounds replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            usgs_bounds=json.loads((dest/'data/external/wrr_usgs_partial_daily_20261027/results/subdaily_bounds_reference_replay.json').read_text())
            if usgs_bounds.get('status')!='passed':raise RuntimeError('USGS conditional subdaily bounds replay did not pass')
            report['checks']['usgs_partial_subdaily_bounds_reproduction']={'status':'passed','target_years':usgs_bounds['target_years'],
                'day_clock_rows':usgs_bounds['day_clock_rows'],'fixed_zero_width_years':usgs_bounds['fixed_zero_width_years']}
            proc=subprocess.run([sys.executable,'data/external/wrr_usgs_partial_daily_20261027/scripts/916_public_qualifier_history_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('USGS qualifier history replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            qualifier=json.loads((dest/'data/external/wrr_usgs_partial_daily_20261027/qualifier_history_replay_status.json').read_text())
            if qualifier.get('status')!='passed':raise RuntimeError('USGS qualifier history replay did not pass')
            report['checks']['usgs_qualifier_history_reproduction']={'status':'passed','target_years':qualifier['targets'],'excluded_history_assignments':qualifier['history_assignments_removed']}
            proc=subprocess.run([sys.executable,'data/external/wrr_usgs_partial_daily_20261027/scripts/917_public_riomora_expansion_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Rio Mora expansion replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            expansion=json.loads((dest/'data/external/wrr_usgs_partial_daily_20261027/expansion_reference_replay_status.json').read_text())
            if expansion.get('status')!='passed':raise RuntimeError('Rio Mora expansion replay did not pass')
            report['checks']['riomora_expansion_reproduction']={'status':'passed','years':expansion['expansion_years'],'day_clock_rows':expansion['day_clock_rows']}
            proc=subprocess.run([sys.executable,'scripts/854_source_history_open_reference_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Source partial-history reference replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            history_reference=json.loads((dest/'results/wrr_review_response_20261027/audit/source_partial_history_open_reference_replay.json').read_text())
            if history_reference.get('status')!='passed':raise RuntimeError('Source partial-history reference replay did not pass')
            report['checks']['source_partial_history_reference_reproduction']={'status':'passed','stations':history_reference['stations'],
                'complete_station_years':history_reference['complete_station_years'],'target_h30_values':history_reference['target_h30_values_checked']}
            proc=subprocess.run([sys.executable,'scripts/767_beaufort_proxy_open_replay.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Interannual thermal-peak proxy replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            proxy=json.loads((dest/'results/wrr_review_response_20261027/audit/beaufort_proxy_open_replay.json').read_text())
            if proxy.get('status')!='passed':raise RuntimeError('Interannual thermal-peak proxy did not pass')
            report['checks']['interannual_summer_proxy_reproduction']={'status':'passed','stations':proxy['stations'],
                'case_masks':proxy['case_masks'],'summary_rows':proxy['summary_rows'],'leave_provider_rows':proxy['leave_provider_rows']}
            proc=subprocess.run([sys.executable,'scripts/718_verify_past_season_snapshot.py'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Past-only season snapshot replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            past=json.loads((dest/'results/wrr_review_response_20261027/audit/past_season_snapshot_reproduction.json').read_text())
            if past.get('status')!='passed':raise RuntimeError('Past-only season snapshot replay did not pass')
            report['checks']['past_season_snapshot_reproduction']={'status':'passed','station_years':past['station_years'],
                'rule_decisions':past['decisions'],'future_perturbation_probes':past['future_perturbation_probes']}
            proc=subprocess.run([sys.executable,'scripts/652_verify_usgs_observed_reproduction.py','--manifest','results/wrr_process_revision_20261029/replay_integrity/usgs_observed_current_manifest.json'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('USGS observation replay failed: '+(proc.stdout+proc.stderr)[-3000:])
            replay=json.loads((dest/'results/wrr_review_response_20261027/audit/usgs_observed_reproduction.json').read_text())
            if replay.get('status')!='passed':raise RuntimeError('USGS observation replay did not pass')
            report['checks']['usgs_observation_only_replay']={'status':'passed','stations':replay['station_count'],
                'complete_reference_station_years':replay['complete_reference_station_years'],
                'witness_station_years':replay['witness_station_years']}
            proc=subprocess.run(['make','review-figures-from-summaries'],cwd=dest,capture_output=True,text=True)
            if proc.returncode:raise RuntimeError('Figure regeneration failed: '+(proc.stdout+proc.stderr)[-3000:])
            matches={}
            for name in NAMES:
                reference=dest/'paper/wrr_tr/figures/simple_research'/(name+'.png')
                redraw=dest/'dist/reviewer_recreated_figures'/(name+'.png')
                with Image.open(reference) as r,Image.open(redraw) as s:
                    x,y=r.convert('RGB'),s.convert('RGB')
                    matches[name]=bool(x.size==y.size and ImageChops.difference(x,y).getbbox() is None)
            report['checks']['figure_regeneration']='passed'
            report['checks']['figure_pixel_matches']=matches
            if a.require_pixel_match and not all(matches.values()):raise RuntimeError('Figure pixels differ in current rendering environment')
            env=os.environ.copy();env['TEXINPUTS']='.:../wrr/template:'
            tex=dest/'paper/wrr_tr'
            for stem in ['review_completion_article','review_completion_supporting']:
                proc=subprocess.run(['latexmk','-g','-pdf','-silent','-interaction=nonstopmode','-halt-on-error',stem+'.tex'],cwd=tex,env=env,capture_output=True,text=True)
                if proc.returncode:raise RuntimeError(stem+' compilation failed: '+(proc.stdout+proc.stderr)[-3000:])
                log=(tex/(stem+'.log')).read_text(errors='replace')
                if 'undefined references' in log or 'undefined citations' in log:
                    raise RuntimeError(stem+' has unresolved references')
                report['checks'][stem+'_compile']='passed'
            report['status']='passed'
    except (OSError,RuntimeError,zipfile.BadZipFile) as exc:
        report['status']='failed';report['error']=str(exc)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if report['status']!='passed':raise SystemExit(1)

if __name__=='__main__':main()
