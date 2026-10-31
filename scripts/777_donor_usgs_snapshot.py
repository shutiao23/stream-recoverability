#!/usr/bin/env python3
"""Package only the public USGS site-metadata responses, not water panels."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
SOURCE=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance/usgs_metadata'
SNAP=OUT/'donor_usgs_snapshot'

def main():
    plan=json.loads((OUT/'donor_usgs_metadata_plan.json').read_text());status=json.loads((OUT/'donor_usgs_metadata_status.json').read_text())
    audit=json.loads((OUT/'donor_metadata_independent_audit.json').read_text())
    if status['status']!='completed' or audit['status']!='passed_metadata_identity_checks':
        raise ValueError('USGS source audit incomplete')
    ids=sorted(set(pd.read_csv(SOURCE/'unresolved_columns.csv',dtype=str).station_id))
    if len(ids)!=69:raise ValueError('USGS roster differs')
    SNAP.mkdir(parents=True,exist_ok=True);batches=[]
    for item in status['batches']:
        number=item['batch'];src=SOURCE/f'batch_{number:02d}.rdb';dest=SNAP/src.name
        if dest.exists():raise FileExistsError('Preserve existing published metadata snapshot')
        if not dest.exists():shutil.copyfile(src,dest)
        batch_ids=ids[(number-1)*40:number*40]
        if len(batch_ids)!=item['requested_ids']:raise ValueError('Batch roster differs')
        batches.append({'file':dest.name,'sites':['USGS:'+s for s in batch_ids],
                        'retrieved_utc_file_mtime':datetime.fromtimestamp(src.stat().st_mtime,timezone.utc).isoformat()})
    manifest={'endpoint':plan['endpoint'],'parameters':{'format':'rdb','siteOutput':'basic'},'batches':batches,
              'source':'USGS Water Services Site Service','selection':'USGS-labeled donor identifiers missing from three earlier local catalogs, selected after the provenance audit.',
              'limits':'Station metadata alone does not prove local water-value provenance, sensor quality or permissions for derived model outputs. Network-to-site mappings and source water data remain local.'}
    (SNAP/'request_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (SNAP/'ATTRIBUTION.txt').write_text('USGS Water Services Site Service: https://waterservices.usgs.gov/docs/site-service/site-service-details/\nUSGS-produced data are generally in the U.S. public domain; acknowledge USGS as source. Third-party material may have different rights: https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits\nThis snapshot contains public site metadata only; no temperature observations.\n')
    print('Packaged two USGS site metadata responses; no case-level data or water panels.')

if __name__=='__main__':main()
