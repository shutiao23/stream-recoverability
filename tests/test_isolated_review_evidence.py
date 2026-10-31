import importlib.util
from pathlib import Path
import stat
import zipfile
import pytest


def module():
    path=Path(__file__).resolve().parents[1]/'scripts/727_isolated_review_evidence_check.py'
    spec=importlib.util.spec_from_file_location('isolated_review_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_archive_rejects_path_escape_and_stored_symlink(tmp_path):
    m=module();destination=tmp_path/'extract';destination.mkdir()
    safe=tmp_path/'safe.zip'
    with zipfile.ZipFile(safe,'w') as z:z.writestr('scripts/example.py','pass')
    with zipfile.ZipFile(safe) as z:m.inspect_members(z,destination)
    escape=tmp_path/'escape.zip'
    with zipfile.ZipFile(escape,'w') as z:z.writestr('../outside','bad')
    with zipfile.ZipFile(escape) as z:
        with pytest.raises(ValueError,match='Unsafe'):m.inspect_members(z,destination)
    link=tmp_path/'link.zip'
    info=zipfile.ZipInfo('some-link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
    with zipfile.ZipFile(link,'w') as z:z.writestr(info,'target')
    with zipfile.ZipFile(link) as z:
        with pytest.raises(ValueError,match='symbolic'):m.inspect_members(z,destination)


def test_python_environment_must_be_outside_hidden_workspace(tmp_path):
    m=module();root=tmp_path/'workspace';root.mkdir()
    m.check_python_location(root,str(tmp_path/'venv/bin/python'),str(tmp_path/'venv'))
    with pytest.raises(ValueError,match='inside the workspace'):
        m.check_python_location(root,str(root/'.venv/bin/python'),str(root/'.venv'))
    with pytest.raises(ValueError,match='inside the workspace'):
        m.check_python_location(root,'/usr/bin/python3',str(root/'.venv'))
