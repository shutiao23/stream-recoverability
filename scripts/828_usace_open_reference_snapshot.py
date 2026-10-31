#!/usr/bin/env python3
"""Stage an attributed, two-column extract of all fixed candidate files."""
import csv
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private/wrr_usace_reservoir_reference_20261027'
DEST = ROOT / 'data/external/wrr_usace_reservoir_20261027'

def main():
    import pandas as pd
    roster = pd.read_csv(PRIVATE / 'roster.csv').set_index('resource_id')
    receipt = json.loads((PRIVATE / 'time_acquisition.json').read_text())
    DEST.mkdir(parents=True, exist_ok=True)
    records = []
    for item in receipt:
        rid = item['resource_id']
        source = PRIVATE / 'raw_level1' / (rid + '.csv.gz')
        path = DEST / (rid + '.csv.gz')
        with gzip.open(source, 'rt', encoding='utf-8-sig', newline='') as f, gzip.open(path, 'wt', encoding='utf-8', newline='') as out:
            reader = csv.DictReader(f)
            writer = csv.DictWriter(out, fieldnames=['timestamp', 'temp_degC'])
            writer.writeheader()
            rows = 0
            for row in reader:
                writer.writerow({k: row[k] for k in ('timestamp', 'temp_degC')})
                rows += 1
        records.append({'resource_id': rid, 'title': roster.loc[rid, 'title'],
            'resource_url': 'https://www.hydroshare.org/resource/' + rid + '/',
            'source_file_url': roster.loc[rid, 'latest_level1_url'],
            'file': path.name, 'rows': rows})
        print('Prepared public column extract', len(records), 'of', len(receipt), flush=True)
    manifest = {'license': 'CC BY 4.0', 'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'attribution': 'Van Horn et al. (2026), USACE reservoir continuous water-quality collection, HydroShare. See each resource URL for its full citation and source metadata.',
        'collection': 'https://www.hydroshare.org/resource/430ee557554948b5811830c1e2ec41aa/',
        'changes': 'Two named columns extracted from each author QA/QC level-1 CSV; original row order and strings retained. Gzip recompressed. No observations filled or changed.',
        'notes': 'Local candidate for review only. Source authors request courtesy notification of derivative products; none sent. Confirm conditions and provenance before external sharing.',
        'records': records}
    (DEST / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (DEST / 'ATTRIBUTION.txt').write_text(manifest['attribution'] + '\n' + manifest['collection'] + '\n' + manifest['license_url'] + '\n' + manifest['changes'] + '\n' + manifest['notes'] + '\n')

if __name__ == '__main__':
    main()
