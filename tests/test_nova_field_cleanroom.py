"""Clean-room extraction must reject private files, symlinks and path escape."""
import importlib.util
from pathlib import Path
import stat
import zipfile
import pytest

path=Path(__file__).resolve().parents[1]/'scripts/758_nova_field_cleanroom.py'
spec=importlib.util.spec_from_file_location('nova_field_cleanroom',path)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_rejects_unsafe_or_private_archive_entries(tmp_path):
    destination=tmp_path/'extract';destination.mkdir()
    for name in ['../outside','private/secret']:
        archive=tmp_path/(str(len(name))+'.zip')
        with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'x')
        with zipfile.ZipFile(archive) as z:
            with pytest.raises(ValueError):m.inspect(z,destination)
    info=zipfile.ZipInfo('data/link');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
    archive=tmp_path/'link.zip'
    with zipfile.ZipFile(archive,'w') as z:z.writestr(info,'target')
    with zipfile.ZipFile(archive) as z:
        with pytest.raises(ValueError,match='symlink'):m.inspect(z,destination)


def test_cleanroom_python_must_survive_workspace_hiding(tmp_path):
    workspace=tmp_path/'workspace';workspace.mkdir()
    m.check_python_location(workspace,str(tmp_path/'venv/bin/python'),str(tmp_path/'venv'))
    with pytest.raises(ValueError,match='inside the hidden workspace'):
        m.check_python_location(workspace,str(workspace/'.venv/bin/python'),str(workspace/'.venv'))
