"""Offline backup/restore of private pilot data. Stop the application first."""
import argparse
from contextlib import closing
import hashlib
import json
import shutil
import sqlite3
import tempfile
import os
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.locking import data_lock


def digest(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def check_database(path):
    with closing(sqlite3.connect(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Database integrity check failed')
        names = [row[0] for row in db.execute('SELECT filename FROM segments')]
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if {'live_chunks', 'live_sessions'} <= tables:
            # Obsolete sessions and cancelled chunks intentionally lose their files.
            # Active queued/running chunks still need audio after offline recovery.
            names.extend(row[0] for row in db.execute(
                "SELECT c.filename FROM live_chunks c JOIN live_sessions s "
                "ON s.practice_id=c.practice_id AND s.session_id=c.session_id "
                "WHERE s.status IN ('open','bound') AND c.status!='cancelled'"))
        for name in names:
            if not isinstance(name, str) or not name or name in ('.', '..') or Path(name).name != name:
                raise ValueError('Unsafe media path')
        return list(dict.fromkeys(names))


def backup(source, target):
    if source.is_symlink():
        raise ValueError('Backup source must not be a symlink')
    source, target = source.resolve(), target.resolve()
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('Backup source and destination must not overlap')
    with data_lock(source):
        _backup(source, target)


def _backup(source, target):
    if target.exists():
        raise ValueError('Destination already exists; choose a new directory')
    if not (source / 'pilot.sqlite3').is_file():
        raise ValueError('Source database does not exist')
    if (source / 'pilot.sqlite3').is_symlink():
        raise ValueError('Source database must not be a symlink')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix='.stage-backup-') as temporary:
        staging = Path(temporary) / 'snapshot'
        staging.mkdir(mode=0o700)
        with closing(sqlite3.connect(source / 'pilot.sqlite3')) as original:
            with closing(sqlite3.connect(staging / 'pilot.sqlite3')) as saved:
                original.backup(saved)
        names = check_database(staging / 'pilot.sqlite3')
        (staging / 'media').mkdir(mode=0o700)
        for name in names:
            media = source / 'media' / name
            if media.is_symlink():
                raise ValueError('Source media must not contain symlinks')
            shutil.copy2(media, staging / 'media' / name)
        for path in staging.rglob('*'):
            if path.is_file():
                path.chmod(0o600)
                with path.open('rb') as saved_file:
                    os.fsync(saved_file.fileno())
        manifest = {str(path.relative_to(staging)): digest(path) for path in staging.rglob('*') if path.is_file()}
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        (staging / 'manifest.json').chmod(0o600)
        with (staging / 'manifest.json').open('rb') as manifest_file:
            os.fsync(manifest_file.fileno())
        verify(staging)
        sync_directory(staging / 'media')
        sync_directory(staging)
        staging.rename(target)
        sync_directory(target.parent)


def verify(source):
    if source.is_symlink():
        raise ValueError('Backup must not be a symlink')
    manifest = json.loads((source / 'manifest.json').read_text())
    if not isinstance(manifest, dict) or 'pilot.sqlite3' not in manifest:
        raise ValueError('Incomplete backup manifest')
    if any(path.is_symlink() for path in source.rglob('*')):
        raise ValueError('Backup must not contain symlinks')
    actual = {str(path.relative_to(source)) for path in source.rglob('*') if path.is_file() and path != source / 'manifest.json'}
    if actual != set(manifest):
        raise ValueError('Backup contains unverified or missing files')
    for relative, expected in manifest.items():
        if not isinstance(expected, str) or not re.fullmatch(r'[a-f0-9]{64}', expected):
            raise ValueError('Invalid backup checksum')
        path = source / relative
        if not path.resolve().is_relative_to(source.resolve()) or path.is_symlink() or digest(path) != expected:
            raise ValueError('Backup checksum or path verification failed')
    for name in check_database(source / 'pilot.sqlite3'):
        if Path(name).name != name or 'media/' + name not in manifest:
            raise ValueError('Referenced media is absent from verified backup')
    return manifest


def restore(source, target):
    if source.is_symlink():
        raise ValueError('Restore source must not be a symlink')
    source, target = source.resolve(), target.resolve()
    if target.is_relative_to(source) or source.is_relative_to(target):
        raise ValueError('Restore source and destination must not overlap')
    if target.exists():
        raise ValueError('Restore only into a new empty location')
    manifest = verify(source)
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
            if digest(destination) != manifest[relative]:
                raise ValueError('Restored file checksum verification failed')
            with destination.open('rb') as saved_file:
                os.fsync(saved_file.fileno())
        check_database(staging / 'pilot.sqlite3')
        sync_directory(staging / 'media')
        sync_directory(staging)
        staging.rename(target)
        sync_directory(target.parent)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'restore', 'verify'])
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path, nargs='?')
    parser.add_argument('--offline', action='store_true', help='Confirm the application is stopped')
    args = parser.parse_args()
    if args.action != 'verify' and not args.offline:
        parser.error('Stop the application and pass --offline')
    if args.action != 'verify' and args.target is None:
        parser.error('Destination is required')
    try:
        if args.action == 'verify':
            verify(args.source)
        else:
            (backup if args.action == 'backup' else restore)(args.source, args.target)
    except (ValueError, OSError, sqlite3.Error, RuntimeError) as error:
        parser.exit(1, str(error) + '\n')
    print('Verified', args.action, 'complete')
