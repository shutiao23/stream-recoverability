import importlib.util
import json
import hashlib
from pathlib import Path
import stat
import zipfile
import pytest

def module():
    path=Path(__file__).resolve().parents[1]/'scripts/728_isolated_groupmax_check.py'
    spec=importlib.util.spec_from_file_location('isolated_groupmax_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_manifest_paths_cannot_escape_workspace():
    m=module();assert m.validate_relative('results/data/file.csv')==Path('results/data/file.csv')
    for bad in ['/etc/passwd','../../outside']:
        with pytest.raises(ValueError,match='Unsafe'):m.validate_relative(bad)

def test_python_environment_must_be_outside_hidden_workspace(tmp_path):
    m=module();root=tmp_path/'workspace';root.mkdir()
    m.check_python_location(root,str(tmp_path/'venv/bin/python'),str(tmp_path/'venv'))
    with pytest.raises(ValueError,match='inside the workspace'):
        m.check_python_location(root,str(root/'.venv/bin/python'),str(root/'.venv'))

def test_candidate_archive_rejects_private_entries_and_symlinks(tmp_path):
    m=module();dest=tmp_path/'extract';dest.mkdir()
    archive=tmp_path/'private.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr('private/confidential.txt','x')
    with zipfile.ZipFile(archive) as z:
        with pytest.raises(ValueError,match='private'):m.inspect_archive(z,dest)
    archive=tmp_path/'symlink.zip';info=zipfile.ZipInfo('data/link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
    with zipfile.ZipFile(archive,'w') as z:z.writestr(info,'target')
    with zipfile.ZipFile(archive) as z:
        with pytest.raises(ValueError,match='symbolic'):m.inspect_archive(z,dest)

def test_isolated_groupmax_requires_matching_local_bridge_repair(tmp_path):
    m=module();package=tmp_path/'package';origin=tmp_path/'origin';package.mkdir();origin.mkdir()
    out=package/m.GROUPMAX;out.mkdir(parents=True)
    relative=Path('results/study/repair.parquet');source=origin/relative;source.parent.mkdir(parents=True)
    source.write_bytes(b'original repair')
    record={'status':'passed','repaired_source_group_maxima_reproduced':True,
            'repair_path':str(relative),
            'input_sha256':{str(relative):hashlib.sha256(source.read_bytes()).hexdigest()}}
    (out/'source_repair_dependency.json').write_text(json.dumps(record))
    assert m.require_local_repair(package,origin)==relative
    source.write_bytes(b'changed')
    with pytest.raises(ValueError,match='missing or changed'):m.require_local_repair(package,origin)
    source.write_bytes(b'original repair')
    record.pop('input_sha256')
    (out/'source_repair_dependency.json').write_text(json.dumps(record))
    with pytest.raises(ValueError,match='missing or changed'):m.require_local_repair(package,origin)
