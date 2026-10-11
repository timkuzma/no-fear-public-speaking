import json
import sqlite3
from pathlib import Path

import pytest

from scripts.backup import backup, restore
from server.store import Store


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


def live_fixture_data(tmp_path):
    store = Store(tmp_path / 'original')
    store.execute('INSERT INTO practices(id,user_id,config,created) VALUES(?,?,?,?)',
                  ('practice', 'user', '{}', 1))
    for index, (session_status, chunk_status) in enumerate([
        ('open', 'pending'), ('bound', 'running'), ('bound', 'succeeded'), ('open', 'failed'),
        ('obsolete', 'succeeded'), ('obsolete', 'running'), ('open', 'cancelled'),
    ]):
        session_id = f'session-{index}'
        filename = f'chunk-{index}.wav'
        store.execute('INSERT INTO live_sessions(practice_id,session_id,created,status) VALUES(?,?,?,?)',
                      ('practice', session_id, 1, session_status))
        store.execute('INSERT INTO live_chunks(id,practice_id,session_id,chunk_index,offset_seconds,duration,filename,sha256,status,created) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (f'chunk-{index}', 'practice', session_id, 0, 0, 5, filename, 'fixture', chunk_status, index))
        if index < 4:
            (store.media / filename).write_bytes(f'synthetic chunk {index}'.encode())
    return store


def test_live_queue_media_survives_offline_backup_and_recovery(tmp_path):
    original = live_fixture_data(tmp_path)
    saved = tmp_path / 'backup'
    backup(original.directory, saved)
    manifest = json.loads((saved / 'manifest.json').read_text())
    assert set(manifest) == {'pilot.sqlite3', *[f'media/chunk-{index}.wav' for index in range(4)]}

    target = tmp_path / 'restored'
    restore(saved, target)
    recovered = Store(target)
    recovered.recover_live_chunks()
    first, second = recovered.claim_live_chunk(), recovered.claim_live_chunk()
    assert [first['id'], second['id']] == ['chunk-0', 'chunk-1']
    assert recovered.claim_live_chunk() is None
    for index in range(4):
        assert (recovered.media / f'chunk-{index}.wav').read_bytes() == f'synthetic chunk {index}'.encode()
    # Replaced/cancelled metadata survives without requiring already-deleted files.
    assert len(recovered.all('SELECT id FROM live_chunks')) == 7
    assert not (recovered.media / 'chunk-4.wav').exists()


def test_backup_refuses_missing_active_live_media(tmp_path):
    original = live_fixture_data(tmp_path)
    (original.media / 'chunk-0.wav').unlink()
    target = tmp_path / 'backup'
    with pytest.raises(FileNotFoundError):
        backup(original.directory, target)
    assert not target.exists()


def test_restore_refuses_removed_live_media_even_with_matching_manifest(tmp_path):
    original = live_fixture_data(tmp_path)
    saved = tmp_path / 'backup'
    backup(original.directory, saved)
    (saved / 'media' / 'chunk-1.wav').unlink()
    manifest = json.loads((saved / 'manifest.json').read_text())
    del manifest['media/chunk-1.wav']
    (saved / 'manifest.json').write_text(json.dumps(manifest))
    target = tmp_path / 'restored'
    with pytest.raises(ValueError, match='Referenced media is absent'):
        restore(saved, target)
    assert not target.exists()


@pytest.mark.parametrize('unsafe', ['../outside.wav', '..', '/outside.wav'])
def test_live_media_paths_cannot_escape_backup(tmp_path, unsafe):
    original = live_fixture_data(tmp_path)
    original.execute('UPDATE live_chunks SET filename=? WHERE id=?', (unsafe, 'chunk-0'))
    target = tmp_path / 'backup'
    with pytest.raises(ValueError, match='Unsafe media path'):
        backup(original.directory, target)
    assert not target.exists()


def test_backup_refuses_source_live_media_symlink(tmp_path):
    original = live_fixture_data(tmp_path)
    linked = original.media / 'chunk-0.wav'
    linked.unlink()
    outside = tmp_path / 'outside.wav'
    outside.write_bytes(b'outside private data')
    linked.symlink_to(outside)
    target = tmp_path / 'backup'
    with pytest.raises(ValueError, match='Source media must not contain symlinks'):
        backup(original.directory, target)
    assert not target.exists()
