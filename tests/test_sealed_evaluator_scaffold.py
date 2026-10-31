from __future__ import annotations
import json
import shutil
from pathlib import Path
import pytest
from stream_recoverability.experiments.sealed_evaluator_scaffold import FIXTURE_RESULT_SCHEMA, FilesystemSealedObjectReader, MemorySealedObjectReader, SealedEvaluatorError, SealedObjectRef, evaluate_synthetic_fixture, parse_foen_response, parse_huc8_nwis_response, registered_object_references, run_sealed_qc, vault_path_for_reference
ROOT = Path(__file__).resolve().parents[1]

def _nwis_payload(site: str='01234567') -> bytes:
    document = {'value': {'timeSeries': [{'sourceInfo': {'siteCode': [{'value': site}]}, 'variable': {'variableCode': [{'value': '00010'}], 'unit': {'unitCode': 'deg C'}, 'options': {'option': [{'name': 'Statistic', 'optionCode': '00003'}]}}, 'values': [{'value': [{'value': '12.5', 'dateTime': '2020-01-01T00:00:00Z', 'qualifiers': ['A']}, {'value': '-999999', 'dateTime': '2020-01-02T00:00:00Z', 'qualifiers': ['A']}]}]}]}}
    return json.dumps(document).encode()

def _foen_payload(site: str='2018') -> bytes:
    document = {'data': {'water': {'observations': {'data_1day_mean': [{'timestamp': '2020-01-01T00:00:00Z', 'value': 8.5, 'parameterName': 'WT', 'unitSymbol': '°C', 'releaseState': 2, 'station': {'no': site}}, {'timestamp': '2020-01-02T00:00:00Z', 'value': 8.8, 'parameterName': 'WT', 'unitSymbol': '°C', 'releaseState': 1, 'station': {'no': site}}]}}}}
    return json.dumps(document).encode()

def _reference(provider: str, body: bytes, *, network: str, site: str, year: int | None=None) -> SealedObjectRef:
    return SealedObjectRef(provider=provider, network_id=network, site_id=site, request_year=year, expected_byte_count=len(body), request_start=f'{year:04d}-01-01T00:00:00Z' if year else '2020-01-01', request_end=f'{year + 1:04d}-01-01T00:00:00Z' if year else '2020-12-31', request_end_inclusive=year is None)

def test_provider_parsers_are_strict_and_preserve_qc_codes() -> None:
    nwis = parse_huc8_nwis_response(_nwis_payload(), site_id='01234567')
    assert nwis['temperature_c'].tolist() == [12.5, -999999.0]
    assert nwis['approval_code'].tolist() == ['A', 'A']
    foen = parse_foen_response(_foen_payload(), site_id='2018')
    assert foen['approval_code'].tolist() == ['A', 'P']
    with pytest.raises(SealedEvaluatorError, match='station mismatch'):
        parse_foen_response(_foen_payload(), site_id='wrong')

def test_nwis_requires_daily_mean_celsius_and_locked_date_range() -> None:
    base = json.loads(_nwis_payload().decode())
    variable = base['value']['timeSeries'][0]['variable']
    variable['options']['option'][0]['optionCode'] = '00001'
    with pytest.raises(SealedEvaluatorError, match='daily mean statistic 00003'):
        parse_huc8_nwis_response(json.dumps(base).encode(), site_id='01234567')
    variable['options']['option'][0]['optionCode'] = '00003'
    variable['unit']['unitCode'] = 'deg F'
    with pytest.raises(SealedEvaluatorError, match='not Celsius'):
        parse_huc8_nwis_response(json.dumps(base).encode(), site_id='01234567')
    with pytest.raises(SealedEvaluatorError, match='precedes request range'):
        parse_huc8_nwis_response(_nwis_payload(), site_id='01234567', request_start='2021-01-01', request_end='2021-12-31')

def test_foen_enforces_request_year_and_calendar_day_duplicate_rule() -> None:
    with pytest.raises(SealedEvaluatorError, match='precedes request range'):
        parse_foen_response(_foen_payload(), site_id='2018', request_year=2021)
    document = json.loads(_foen_payload().decode())
    rows = document['data']['water']['observations']['data_1day_mean']
    rows.append(dict(rows[0]))
    frame = parse_foen_response(json.dumps(document).encode(), site_id='2018', request_year=2020)
    assert len(frame) == 2
    rows[-1]['value'] = 99.0
    with pytest.raises(SealedEvaluatorError, match='conflicting duplicate'):
        parse_foen_response(json.dumps(document).encode(), site_id='2018', request_year=2020)

def test_filesystem_reader_resolves_vault_paths_and_verifies_bytes(tmp_path: Path) -> None:
    body = _nwis_payload()
    ref = _reference('usgs_nwis', body, network='huc8_test', site='01234567')
    vault = tmp_path / 'huc8_vault' / 'huc8_test'
    vault.mkdir(parents=True)
    object_path = vault_path_for_reference(ref, huc8_vault=tmp_path / 'huc8_vault')
    object_path.write_bytes(body)
    reader = FilesystemSealedObjectReader(huc8_vault=tmp_path / 'huc8_vault')
    assert reader.read_object(ref) == body
    assert reader.read_keys == [ref.key]

def test_default_registry_builds_opaque_references_without_vault_paths() -> None:
    references = registered_object_references()
    assert len(references) == 228 + 2652
    assert sum((ref.provider == 'usgs_nwis' for ref in references)) == 228
    assert sum((ref.provider == 'foen' for ref in references)) == 2652
    assert all(('vault' not in ref.key.lower() for ref in references))
    assert all((ref.request_start and ref.request_end for ref in references))

def test_registry_reference_replay_rejects_incomplete_registry(tmp_path: Path) -> None:
    source = ROOT / 'results/framework/public_catalog/sealed_byte_registry_v1/sealed'
    shutil.copytree(source, tmp_path / 'sealed')
    sorted((tmp_path / 'sealed').glob('*/*.json'))[0].unlink()
    with pytest.raises(SealedEvaluatorError, match='complete locked request set'):
        registered_object_references(huc8_registry_root=tmp_path / 'sealed')

def test_synthetic_fixture_records_sentinel_attrition(tmp_path: Path) -> None:
    nwis_body = _nwis_payload()
    foen_body = _foen_payload()
    refs = [_reference('usgs_nwis', nwis_body, network='huc8_x', site='01234567'), _reference('foen', foen_body, network='foen_x', site='2018', year=2020)]
    reader = MemorySealedObjectReader({ref.key: body for ref, body in zip(refs, [nwis_body, foen_body])})
    manifest = evaluate_synthetic_fixture(references=refs, reader=reader, output_dir=tmp_path)
    assert manifest['manifest_schema'] == FIXTURE_RESULT_SCHEMA
    assert manifest['formal_evidence'] is False
    assert manifest['n_synthetic_objects_read'] == 2
    qc = (tmp_path / 'synthetic_station_qc.csv').read_text(encoding='utf-8')
    assert 'rejected_sentinel' in qc
    attrition = (tmp_path / 'synthetic_network_attrition.csv').read_text(encoding='utf-8')
    assert 'fewer_than_3_qc_accepted_stations' in attrition

def test_sealed_qc_runner_reads_vault_objects_and_records_attrition(tmp_path: Path) -> None:
    nwis_body = _nwis_payload()
    foen_body = _foen_payload()
    refs = [_reference('usgs_nwis', nwis_body, network='huc8_x', site='01234567'), _reference('foen', foen_body, network='foen_x', site='2018', year=2020), _reference('usgs_nwis', nwis_body, network='huc8_x', site='07654321')]
    huc8_vault = tmp_path / 'huc8_vault'
    foen_vault = tmp_path / 'foen_vault'
    for ref, body in zip(refs[:2], [nwis_body, foen_body]):
        path = vault_path_for_reference(ref, huc8_vault=huc8_vault, foen_vault=foen_vault)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    reader = FilesystemSealedObjectReader(huc8_vault=huc8_vault, foen_vault=foen_vault)
    output = tmp_path / 'qc'
    manifest = run_sealed_qc(output_dir=output, references=refs, reader=reader)
    assert manifest['n_sealed_objects_read'] == 2
    assert manifest['n_object_parse_failures'] == 1
    assert manifest['n_huc8_eligible_networks'] == 0
    assert manifest['passed'] is False
    assert 'sealed vault object missing' in (output / 'object_attrition.csv').read_text(encoding='utf-8')
    assert 'rejected_sentinel' in (output / 'station_qc.csv').read_text(encoding='utf-8')
    stored = json.loads((output / 'sealed_qc_manifest.json').read_text(encoding='utf-8'))
    assert stored == manifest

def test_memory_reader_subclass_is_refused(tmp_path: Path) -> None:

    class MemoryReaderSubclass(MemorySealedObjectReader):
        pass
    with pytest.raises(SealedEvaluatorError, match='exact memory reader'):
        evaluate_synthetic_fixture(references=[], reader=MemoryReaderSubclass({}), output_dir=tmp_path)
    assert not (tmp_path / 'manifest.json').exists()
