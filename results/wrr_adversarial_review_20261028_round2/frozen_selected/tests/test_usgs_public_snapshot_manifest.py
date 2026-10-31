import json
from pathlib import Path

def test_nested_power_manifest_is_included_and_snapshot_hashes_match():
    root=Path(__file__).resolve().parents[1]/'data/external/wrr_usgs_partial_daily_20261027'
    metadata=json.loads((root/'manifest.json').read_text())
    paths={item['path'] for item in metadata['files']}
    assert 'power/manifest.json' in paths
    for item in metadata['files']:
        file=(root/item['path']).resolve()
        assert file.is_relative_to(root.resolve()) and file.is_file()
