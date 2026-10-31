#!/usr/bin/env python3
"""Offline-check the bundled USGS site-metadata snapshot and request roster."""
import argparse
import csv
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/wrr_review_response_20261027/open_source_sensitivity';SNAP=OUT/'donor_usgs_snapshot'

def main():
    p=argparse.ArgumentParser();p.add_argument('--report',type=Path,default=ROOT/'results/wrr_review_response_20261027/audit/donor_usgs_snapshot_replay.json');args=p.parse_args()
    manifest=json.loads((SNAP/'request_manifest.json').read_text());status=json.loads((OUT/'donor_usgs_metadata_status.json').read_text());all_returned=[]
    for batch in manifest['batches']:
        path=SNAP/batch['file']
        with path.open(encoding='utf-8',newline='') as f:
            reader=csv.DictReader((line for line in f if not line.startswith('#') and line.strip()),delimiter='\t');next(reader)
            rows=list(reader)
        requested={x.removeprefix('USGS:') for x in batch['sites']};returned={row['site_no'] for row in rows if row['agency_cd']=='USGS'}
        if requested!=returned or len(rows)!=len(returned):raise ValueError('USGS batch response differs from requested IDs')
        all_returned.extend(returned)
    if len(all_returned)!=len(set(all_returned)) or len(all_returned)!=status['returned_unique_identifiers'] or len(all_returned)!=69:
        raise ValueError('USGS response total differs')
    result={'status':'passed','metadata_identifiers':len(all_returned),'responses':len(manifest['batches']),
            'scope':'Offline verification of public USGS site metadata and request IDs. No private donor-panel mapping, cached water values, physical provenance or permission check is reproduced.'}
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
