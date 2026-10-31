#!/usr/bin/env python3
"""Stage public USGS daily API responses without local panel mappings."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity'
PRIVATE=ROOT/'private/wrr_open_source_sensitivity_20261026/donor_provenance';DAILY=PRIVATE/'usgs_daily';SNAP=OUT/'donor_usgs_daily_snapshot'

def main():
    plan=json.loads((OUT/'donor_usgs_daily_plan.json').read_text());acq=json.loads((OUT/'donor_usgs_daily_acquisition.json').read_text())
    audit=json.loads((OUT/'donor_usgs_daily_independent_audit.json').read_text());amb=json.loads((OUT/'donor_usgs_ambiguous_independent_audit.json').read_text())
    receipt=DAILY/'acquisition.json'
    if acq['status']!='completed' or audit['status']!='passed' or amb['status']!='passed':
        raise ValueError('Current USGS comparison not independently checked')
    ids=sorted(set(pd.read_csv(PRIVATE/'usgs_metadata/unresolved_columns.csv',dtype=str).station_id))
    SNAP.mkdir(parents=True,exist_ok=True);batches=[]
    for item in json.loads(receipt.read_text()):
        i=item['batch'];src=DAILY/f'batch_{i:02d}.json.gz';dest=SNAP/src.name
        if dest.exists():raise FileExistsError('Preserve existing USGS daily snapshot')
        if not dest.exists():shutil.copyfile(src,dest)
        requested=ids[(i-1)*10:i*10]
        if len(requested)!=item['requested_sites']:raise ValueError('Requested site list differs')
        batches.append({'file':dest.name,'sites':requested,
                        'retrieved_utc_file_mtime':datetime.fromtimestamp(src.stat().st_mtime,timezone.utc).isoformat()})
    manifest={'endpoint':'https://waterservices.usgs.gov/nwis/dv/',
              'parameters':{'format':'json','parameterCd':'00010','statCd':'00003','startDT':plan['start_date'],
                            'endDT':plan['end_date'],'siteStatus':'all'},'batches':batches,
              'selection':'The 69 USGS identifiers selected for the post-hoc donor provenance check; source metadata and source models were already examined.',
              'limits':'Contains current USGS API responses, not historical API versions or the local water panel, network-to-site mapping, source roles or masked cases. It does not itself establish local-value consistency, water quality or derivative rights.'}
    (SNAP/'request_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (SNAP/'ATTRIBUTION.txt').write_text('U.S. Geological Survey, National Water Information System, daily values web service: https://waterservices.usgs.gov/docs/dv-service/\nUSGS-produced data are generally U.S. public domain; acknowledge USGS, and review separate rights for third-party data: https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits\nThese are current retrieved USGS responses, not historical snapshots or the locally processed model input.\n')
    print('Staged seven public USGS responses without local panel mappings.')

if __name__=='__main__':main()
