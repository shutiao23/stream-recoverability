#!/usr/bin/env python3
"""Stage the public POWER hourly responses used in the time-standard check."""
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/external_truckee_dwr';PRIVATE=ROOT/'private/wrr_truckee_reference_20261027/power_time_standards';SNAP=ROOT/'data/external/wrr_truckee_dwr_20261027/power_time_standards'

def main():
    plan=json.loads((OUT/'power_time_standards_plan.json').read_text());status=json.loads((OUT/'power_time_acquisition.json').read_text());audit=json.loads((OUT/'power_time_independent_audit.json').read_text())
    receipt=PRIVATE/'acquisition.json'
    if status['status']!='completed' or audit['status']!='passed':raise ValueError('Time-standard check incomplete')
    SNAP.mkdir(parents=True,exist_ok=True);records=[]
    for item in json.loads(receipt.read_text()):
        src=PRIVATE/f"{item['year']}_{item['standard']}.json.gz";dest=SNAP/src.name
        if dest.exists():raise FileExistsError('Preserve existing POWER snapshot')
        if not dest.exists():shutil.copyfile(src,dest)
        records.append({'file':dest.name,'year':item['year'],'standard':item['standard'],'api_version':item['api_version'],'retrieved_utc_file_mtime':datetime.fromtimestamp(src.stat().st_mtime,timezone.utc).isoformat()})
    manifest={'endpoint':'https://power.larc.nasa.gov/api/temporal/hourly/point','parameter':'T2M','community':'RE',
              'latitude':plan['latitude'],'longitude':plan['longitude'],'records':records,
              'interpretation':'Current NASA POWER hourly LST and UTC responses for the four exploratory Truckee reference years; independent of the provider sensor clock.',
              'notification':'NASA POWER requests notification when its data are transmitted to other researchers. This local candidate has not been externally released and no notification was sent.'}
    (SNAP/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (SNAP/'ATTRIBUTION.txt').write_text('NASA Langley Research Center POWER Project, Hourly API v2.10.3, accessed 2026-10-27, https://power.larc.nasa.gov/. T2M is derived from MERRA-2; time standards and 15-degree LST bands: https://power.larc.nasa.gov/docs/services/api/temporal/hourly/.\nNASA requests notification upon transmitting POWER data to other researchers; no notification was sent.\n')
    print('Staged eight POWER hourly time-standard responses for local review')

if __name__=='__main__':main()
