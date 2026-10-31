#!/usr/bin/env python3
"""Record the post-hoc common-cohort scoring design for the archive proxy."""
from datetime import datetime,timezone
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/summer_proxy_archive'

def main():
    target=OUT/'analysis_plan.json'
    if target.exists():raise FileExistsError('Preserve existing archive-proxy analysis plan')
    pilot=json.loads((OUT/'pilot.json').read_text());source=json.loads((OUT/'plan.json').read_text())
    if pilot['status']!='pilot_completed' or pilot['archive_settings']!=16:raise ValueError('Archive-proxy pilot incomplete')
    plan={'created_utc':datetime.now(timezone.utc).isoformat(),
          'status':'post-hoc after prior archive and published-method proxy results; after a two-station pipeline pilot',
          'cohort':'All fixed 3,320 archive settings and all their masked station-years; report unavailable outputs explicitly.',
          'methods':['plug_in','D2','stochastic_calibrated','summer_air_proxy'],
          'annual':'For each family and time mode, compare each existing method to the proxy on both pairwise finite cases and the four-method common cohort. Report availability, stations, distinct station-years, connected groups, MAE, signed bias and failure above 0.5 C.',
          'annual_strata':'Report all cases, retrospective bound-equals-reference, reference-above-bound, and missing-bound strata. These strata use complete reference values and cannot be used to select a release at decision time.',
          'trend':'On the same finite-record target and retention=all, report each pairwise and four-method common cohort, both all archives and only archives with at least one masked year. Report point RMSE, bias and paired MSE difference, without interval claims for the deterministic proxy.',
          'uncertainty':'For each paired difference resample connected groups 4,000 times with deterministic seed and retain repeated mask cases inside groups; report group-equal contrast and fixed-prediction leave-region-out for four-method nontrivial trend cohorts.',
          'support':'Count unavailable proxy reasons, cases where no summer fill is needed and proxy values equal the observed bound. In forward mode reject any proxy fit using 2010-or-later water.',
          'limitations':'Post-hoc after earlier results, different target and implementation from the cited article; original source model roles and stored local fits are reused. Bound-defined strata use hidden reference outcomes, repeated masks are not independent climates, and no sensor accuracy, rights or interval guarantee is established.',
          }
    target.write_text(json.dumps(plan,indent=2)+'\n');print('Recorded post-hoc proxy scoring plan before full-archive scores are summarized.')

if __name__=='__main__':main()
