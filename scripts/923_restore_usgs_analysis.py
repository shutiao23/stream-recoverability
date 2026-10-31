#!/usr/bin/env python3
"""Verify or restore the saved USGS analysis scratch directory locally."""
from pathlib import Path
import argparse, json, shutil, stat

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / 'private/wrr_usgs_partial_daily_20261027'
SOURCE = PRIVATE / 'tmpfs_analysis_20261027'
MANIFEST = PRIVATE / 'analysis_copy_manifest_20261027.json'

def verify(root, items):
    expected = set()
    for item in items:
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts or not rel.parts:
            raise ValueError('Unsafe manifest path')
        p = root / rel
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root.resolve()):
            raise ValueError('Missing or unsafe file: ' + str(p))
        if p.stat().st_size != item['bytes']:
            raise ValueError('File differs: ' + str(p))
        if stat.S_IMODE(p.stat().st_mode) != item['mode']:
            raise ValueError('File mode differs: ' + str(p))
        expected.add(str(rel))
    actual = set()
    for p in root.rglob('*'):
        if p.is_symlink():
            raise ValueError('Unexpected symlink: ' + str(p))
        if p.is_file():
            actual.add(str(p.relative_to(root)))
    if actual != expected:
        raise ValueError('Unexpected or missing files')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore-to', type=Path, help='Create a new directory; never overwrites an existing path')
    args = parser.parse_args()
    items = json.loads(MANIFEST.read_text())['files']
    verify(SOURCE, items)
    if args.restore_to:
        dest = args.restore_to.absolute()
        if dest.exists() or dest.is_symlink():
            raise FileExistsError('Restore target already exists: ' + str(dest))
        if not dest.parent.is_dir():
            raise FileNotFoundError('Restore parent does not exist: ' + str(dest.parent))
        if dest.resolve().is_relative_to(SOURCE.resolve()):
            raise ValueError('Restore target is inside source')
        shutil.copytree(SOURCE, dest, symlinks=True, copy_function=shutil.copy2)
        verify(dest, items)
    print(json.dumps({'status': 'passed', 'files_verified': len(items), 'source': str(SOURCE), 'restored_to': str(args.restore_to) if args.restore_to else None, 'limitations': 'Restores local frozen files only. Historical plans require their original absolute source paths; this does not recreate restricted models or an open research deposit.'}, indent=2))

if __name__ == '__main__':
    main()
