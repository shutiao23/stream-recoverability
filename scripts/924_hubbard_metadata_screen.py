#!/usr/bin/env python3
"""Summarize the saved metadata-only Hubbard Brook reference screen."""
from pathlib import Path
import json,re,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
PRIVATE=ROOT/'private/wrr_hubbard_metadata_20261027'
OUT=ROOT/'results/wrr_review_response_20261027/external_hubbard_metadata'
def text(element):return ' '.join(' '.join(element.itertext()).split()) if element is not None else ''
def main():
 plan=json.loads((OUT/'plan.json').read_text());receipts=json.loads((PRIVATE/'metadata_receipts.json').read_text());documents=[]
 for item in receipts:
  path=PRIVATE/(item['name']+'.xml')
  if item['status']!=200:raise ValueError('Metadata missing or changed')
  root=ET.fromstring(path.read_bytes());title=text(root.find('.//title'));entities=[]
  for dt in root.findall('.//dataTable'):
   attrs=[{'name':a.findtext('attributeName'),'definition':a.findtext('attributeDefinition')} for a in dt.findall('.//attribute')]
   entities.append({'name':dt.findtext('entityName'),'temperature_attributes':[a for a in attrs if 'temp' in str(a['name']).lower()]})
  if 'Air Temperature' in title:reason='air_temperature_not_stream_temperature'
  elif any('weekly' in str(x['name']).lower() and x['temperature_attributes'] for x in entities):reason='weekly_sampling_temperature_not_continuous_daily_reference'
  else:reason='not_qualified_by_inspected_metadata'
  documents.append({'identifier':item['identifier'],'title':title,'entities':entities,'metadata_only_reason':reason,})
 queries=[]
 for name in ['dataone_catalog_query.json','dataone_stream_query.json']:
  path=PRIVATE/name;d=json.loads(path.read_text());latest={}
  for x in d['response']['docs']:
   m=re.search(r'/knb-lter-hbr/(\d+)/(\d+)$',x['id'])
   if m and m[1] not in latest or int(m[2])>latest[m[1]][0]:latest[m[1]]=(int(m[2]),x)
  queries.append({'file':name,'hits':d['response']['numFound'],'returned':len(d['response']['docs']),'package_ids_among_returned_versions':len(latest)})
 result={'status':'no_eligible_reference_identified_in_inspected_metadata','metadata_documents':len(documents),'measurement_tables_downloaded':0,'temperature_outcomes_read':False,'model_errors_scored':False,'documents':documents,'queries':queries,'limitations':'This is a post-hoc search of two queries and two selected metadata documents, not an exhaustive provider catalog audit or proof that no suitable records exist. No independence, complete timestamps, quality flags or sensor accuracy was established.'}
 (OUT/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
