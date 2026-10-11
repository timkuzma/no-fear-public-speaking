"""Offline backup/restore of private pilot data. Stop the application first."""
import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from pathlib import Path


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def check_database(path):
    with sqlite3.connect(path) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed')
        return [row[0] for row in db.execute('SELECT filename FROM segments')]


def backup(source, target):
    if target.exists():
        raise ValueError('Destination already exists; choose a new directory')
    if not (source / 'pilot.sqlite3').is_file():
        raise ValueError('Source database does not exist')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='.stage-backup-') as temporary:
        staging = Path(temporary) / 'snapshot'
        staging.mkdir(mode=0o700)
        with sqlite3.connect(source / 'pilot.sqlite3') as original:
            with sqlite3.connect(staging / 'pilot.sqlite3') as saved:
                original.backup(saved)
        names = check_database(staging / 'pilot.sqlite3')
        (staging / 'media').mkdir()
        for name in names:
            if Path(name).name != name:
                raise ValueError('Unsafe media path')
            shutil.copy2(source / 'media' / name, staging / 'media' / name)
        manifest = {str(path.relative_to(staging)): digest(path) for path in staging.rglob('*') if path.is_file()}
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        staging.rename(target)


def restore(source, target):
    if target.exists():
        raise ValueError('Restore only into a new empty location')
    manifest = json.loads((source / 'manifest.json').read_text())
    if not isinstance(manifest, dict) or 'pilot.sqlite3' not in manifest:
        raise ValueError('Incomplete backup manifest')
    if any(path.is_symlink() for path in source.rglob('*')):
        raise ValueError('Backup must not contain symlinks')
    actual = {str(path.relative_to(source)) for path in source.rglob('*') if path.is_file() and path != source / 'manifest.json'}
    if actual != set(manifest):
        raise ValueError('Backup contains unverified or missing files')
    for relative, expected in manifest.items():
        path = source / relative
        if not path.resolve().is_relative_to(source.resolve()) or path.is_symlink() or digest(path) != expected:
            raise ValueError('Backup checksum or path verification failed')
    for name in check_database(source / 'pilot.sqlite3'):
        if Path(name).name != name or 'media/' + name not in manifest:
            raise ValueError('Referenced media is absent from verified backup')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='.stage-restore-') as temporary:
        staging = Path(temporary) / 'restored'
        staging.mkdir(mode=0o700)
        (staging / 'media').mkdir(mode=0o700)
        for relative in manifest:
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(source / relative, destination)
            destination.chmod(0o600)
        staging.rename(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore'])
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('--offline', action='store_true', help='Confirm the application is stopped')
    args = parser.parse_args()
    if not args.offline:
        parser.error('Stop the application and pass --offline')
    try:
        (backup if args.action == 'backup' else restore)(args.source.resolve(), args.target.resolve())
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')
    print('Verified', args.action, 'complete')
