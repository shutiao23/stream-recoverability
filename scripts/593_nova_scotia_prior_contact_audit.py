#!/usr/bin/env python3
"""Check fixed Nova Scotia site IDs against named previous local inventories."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/wrr_review_response_20261027/external_nova_scotia_verified'


def normalize(x):return str(x).strip().upper().split('|')[-1]


def main():
    roster=pd.read_csv(OUT/'candidate_roster.csv',dtype=str)
    candidates=set(roster.station_id.map(normalize))
    inventories={
      'source_seed_zero_cases':pd.read_parquet(ROOT/'results/wrr_review_completion_20261024/cases/leave_one_year_out/seed_00.parquet',columns=['station_key']).station_key,
      'previous_eccc_opened_cache':pd.read_csv(ROOT/'results/wrr_review_response_20261027/external_eccc_red/prior_eccc_cache_upper_bound.csv',dtype=str).site,
      'previous_bc_published_roster':pd.read_csv(ROOT/'results/wrr_review_response_20261027/external_bc_air2stream/roster.csv',dtype=str).station_number,
    }
    details=[]
    for name,column in inventories.items():
        ids=set(column.dropna().map(normalize));match=sorted(candidates&ids)
        details.append({'inventory':name,'unique_identifiers':len(ids),'exact_candidate_matches':match})
    report={'status':'checked','created_utc':datetime.now(timezone.utc).isoformat(),'candidates':len(candidates),'inventories':details,
            'scope':'exact candidate identifiers only in named inventories; other formats and caches were not exhaustively searched',
            'limitation':'different identifiers may represent the same physical site, river, basin or climate; neither prior full contact nor independence is proven'}
    (OUT/'prior_contact_audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
