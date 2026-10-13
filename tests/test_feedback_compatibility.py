"""Owned repeat selection and additive feedback metadata survive code rollback/restore."""
import importlib.util
import json
from pathlib import Path

from fastapi.testclient import TestClient
from scripts.backup import backup, restore
from server.app import create_app
from server.store import Store


def test_owned_repeat_preserves_explicit_criteria(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.delenv('REQUIRE_INVITE', raising=False)
    monkeypatch.delenv('APP_ORIGIN', raising=False)
    app = create_app(tmp_path, start_worker=False)
    one, other = TestClient(app), TestClient(app)
    def signup(client, email):
        response = client.post('/api/auth/register', json={
            'email': email, 'name': 'Проверка', 'password': 'SyntheticSecret2026', 'role': 'other'})
        assert response.status_code == 200
        return {'X-CSRF-Token': response.json()['csrf_token']}
    headers = signup(one, 'repeat@example.test')
    other_headers = signup(other, 'other-repeat@example.test')
    config = {'scenario': 'free', 'topic': '', 'duration': 1, 'criteria': 'Понятна ли связь событий', 'questions': False}
    source = one.post('/api/practices', headers=headers, json=config).json()['id']
    report = {'schema_version': 2, 'recommendations': [
        {'title': 'Свяжи события', 'action': 'Уточни последовательность событий', 'transcript_revision': 'source-hash'},
        {'title': 'Проясни ссылку', 'action': 'Уточни, к чему относится «это»', 'transcript_revision': 'source-hash'}]}
    app.state.store.execute("UPDATE practices SET report=?,status='ready' WHERE id=?", (json.dumps(report), source))
    request = {**config, 'repeat_source_id': source, 'repeat_recommendation_index': 1,
               'repeat_focus': {'action': 'Invented untrusted client advice'}}
    response = one.post('/api/practices', headers=headers, json=request)
    assert response.status_code == 200
    saved = response.json()['config']
    assert saved['criteria'] == config['criteria']
    assert saved['repeat_focus']['action'] == report['recommendations'][1]['action']
    assert saved['repeat_focus']['source_practice_id'] == source
    assert other.post('/api/practices', headers=other_headers, json=request).status_code == 404
    assert one.post('/api/practices', headers=headers, json={**request, 'repeat_recommendation_index': 4}).status_code == 422
    assert one.post('/api/practices', headers=headers, json={**config, 'repeat_recommendation_index': 0}).status_code == 422
    assert one.post('/api/practices', headers=headers, json={**request, 'repeat_recommendation_index': True}).status_code == 422
    # Nullable focus permits an ordinary repeat without inventing an action.
    ordinary = one.post('/api/practices', headers=headers, json={**request, 'repeat_recommendation_index': None})
    assert ordinary.status_code == 200
    assert 'repeat_focus' not in ordinary.json()['config']
    assert ordinary.json()['config']['criteria'] == config['criteria']
    # Existing stored reports remain usable and select their saved text.
    legacy = {'insight': 'Сохрани смысл', 'recommendations': [{'title': 'Связь', 'text': 'Сохрани связь событий'}]}
    app.state.store.execute('UPDATE practices SET report=? WHERE id=?', (json.dumps(legacy), source))
    response = one.post('/api/practices', headers=headers, json={**request, 'repeat_recommendation_index': 0})
    assert response.status_code == 200
    assert response.json()['config']['repeat_focus']['action'] == 'Сохрани связь событий'


def test_frozen_store_and_offline_restore_preserve_feedback_metadata(tmp_path):
    store = Store(tmp_path / 'current')
    report = {'schema_version': 2, 'insight': None, 'primary_recommendation_index': None,
              'strengths': [], 'recommendations': [], 'transcript_segments': [{'index': 0, 'text': 'Спасибо'}]}
    provenance = {'schema_version': 2, 'transcript_revision': 'fixture-revision', 'items': []}
    store.execute('INSERT INTO practices(id,user_id,config,created,report,question_provenance) VALUES(?,?,?,?,?,?)',
                  ('practice', 'owner', '{}', 1, json.dumps(report), json.dumps(provenance)))
    (store.media / 'speech.wav').write_bytes(b'Synthetic saved media')
    store.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',
                  ('segment', 'practice', 'speech', 0, 'speech.wav', 1, 'Спасибо', 1))
    # Both actual code versions open the same additive schema without erasing metadata.
    original = Path(__file__).resolve().parents[1] / 'evals/speech-feedback/baseline/server/store.py'
    spec = importlib.util.spec_from_file_location('frozen_store', original)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = module.Store(store.directory)
    row = old.one('SELECT * FROM practices WHERE id=?', ('practice',))
    assert json.loads(row['report']) == report
    assert json.loads(row['question_provenance']) == provenance
    old.execute('INSERT INTO practices(id,user_id,config,created) VALUES(?,?,?,?)', ('old-created', 'owner', '{}', 2))
    saved = tmp_path / 'backup'
    backup(store.directory, saved)
    restore(saved, tmp_path / 'restored')
    restored = Store(tmp_path / 'restored')
    row = restored.one('SELECT * FROM practices WHERE id=?', ('practice',))
    assert json.loads(row['report']) == report
    assert json.loads(row['question_provenance']) == provenance
    assert restored.one('SELECT id FROM practices WHERE id=?', ('old-created',)) is not None
    assert (restored.media / 'speech.wav').read_bytes() == b'Synthetic saved media'
