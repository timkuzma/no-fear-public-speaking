import json
import sqlite3
from pathlib import Path

import pytest

from scripts.backup import backup, restore


def fixture_data(tmp_path):
    data = tmp_path / 'original'
    (data / 'media').mkdir(parents=True)
    (data / 'media' / 'private.wav').write_bytes(b'synthetic private recording')
    with sqlite3.connect(data / 'pilot.sqlite3') as db:
        db.execute('CREATE TABLE segments(filename TEXT)')
        db.execute('INSERT INTO segments VALUES(?)', ('private.wav',))
    target = tmp_path / 'backup'
    backup(data, target)
    return target


def test_verified_restore_and_refuse_overwrite(tmp_path):
    saved = fixture_data(tmp_path)
    target = tmp_path / 'restored'
    restore(saved, target)
    assert (target / 'media' / 'private.wav').read_bytes() == b'synthetic private recording'
    with pytest.raises(ValueError):
        restore(saved, target)


@pytest.mark.parametrize('damage', ['corrupt', 'extra', 'symlink', 'missing_manifest_entry', 'missing_media', 'no_database'])
def test_restore_rejects_unverified_data(tmp_path, damage):
    saved = fixture_data(tmp_path)
    manifest_path = saved / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if damage == 'corrupt':
        (saved / 'media' / 'private.wav').write_bytes(b'changed')
    elif damage == 'extra':
        (saved / 'unverified.txt').write_text('extra')
    elif damage == 'symlink':
        (saved / 'unsafe').symlink_to(saved / 'pilot.sqlite3')
    elif damage == 'missing_manifest_entry':
        manifest.pop('media/private.wav')
        manifest_path.write_text(json.dumps(manifest))
    elif damage == 'missing_media':
        (saved / 'media' / 'private.wav').unlink()
        manifest.pop('media/private.wav')
        manifest_path.write_text(json.dumps(manifest))
    else:
        manifest.pop('pilot.sqlite3')
        manifest_path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        restore(saved, tmp_path / 'restored')
    assert not (tmp_path / 'restored').exists()
