#!/usr/bin/env python3
"""Record source-specific LUBW terms locators without granting sharing rights."""
from pathlib import Path
import ast,json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'private/wrr_lubw_terms_review_20261027'
OUT=ROOT/'results/wrr_review_response_20261027/source_rights/lubw_terms_review_20261027.json'
TERMS='https://www.lubw.baden-wuerttemberg.de/umweltinformationssystem/nutzungsvereinbarung'
def main():
 receipts=json.loads((PRIVATE/'receipts.json').read_text());index={r['key']:r for r in receipts};locators=json.loads((PRIVATE/'landing_terms_locators.json').read_text())
 metadata=PRIVATE/'measurement_metadata.html'
 if index['measurement_metadata']['status']!=200:raise ValueError('Official measurement metadata changed')
 if TERMS not in metadata.read_text() or TERMS not in locators['terms_links']:raise ValueError('Terms locator not found in both provider resources')
 module=ROOT/'src/stream_recoverability/data/lubw_temperature.py';tree=ast.parse(module.read_text());landing=None
 for n in tree.body:
  if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='LANDING_URL' for t in n.targets):landing=ast.literal_eval(n.value)
 if landing!=locators['canonical_landing']:raise ValueError('Acquisition landing differs from reviewed landing')
 scope=pd.read_csv(ROOT/'results/wrr_review_response_20261027/source_rights/lubw_station_year_scope.csv',dtype=str);catalog=pd.read_csv(ROOT/'results/development_v11/lubw_temperature/official_station_catalog.csv',dtype=str);ids=set(scope.station_key.str.removeprefix('lubw|'));matched=ids & set(catalog.site_id)
 result={'status':'source_specific_terms_identified_applicability_pending','acquisition_landing':landing,'terms_url':TERMS,'indexed_terms_url':'https://www.lubw.baden-wuerttemberg.de/en/umweltinformationssystem/nutzungsvereinbarung','measurement_metadata_url':index['measurement_metadata']['source_url'],'provider_metadata_links_to_uis_terms':True,'actual_acquisition_landing_links_to_same_terms':True,'source_station_identifiers':len(ids),'source_ids_in_existing_official_catalog':len(matched),'unmatched_source_identifiers':sorted(ids-matched),
 'terms_body_live_status':index['uis_terms_en']['status'],'indexed_terms_summary':'The indexed provider-specific agreement describes attribution on reuse, a warranty disclaimer, and extra commercial-use restrictions for four named GIS datasets. This indexed excerpt is not a successful live fetch of the complete agreement and does not alone establish its application to the archived temperature exports or trained derivatives.',
 'assessment':'The previous general-impressum citation alone is insufficient to characterize the source-specific route. Verify agreement scope and acquisition vintage for observations, reviewer transfer and model/case derivatives before changing the operational hold.',
 'release_decision':'hold_redistribution_pending_scope_confirmation','redistribution_authorized_by_this_review':False,'provider_contact_sent':False,'raw_application_session_state_retained':False,'limitations':'Metadata linkage and identifier matches do not authenticate a historical data vintage or constitute legal advice or a redistribution grant.'}
 OUT.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
