"""Editorial containment and durable accounting, not semantic-equivalence proofs."""
import asyncio
import copy
import json
from unittest.mock import AsyncMock

import pytest
from server import ai, feedback_prompts
from server.worker import process
from server.store import Store, now

TEXT = 'Мы перенесли встречу, потому что зал закрыт. Новый срок — пятница.'
SEGMENTS = [{'index': 0, 'kind': 'speech', 'text': TEXT, 'duration_seconds': 12}]
USAGE = {'model': 'gpt-fixture', 'operation': 'report', 'attempts': [], 'audio_seconds': 0}
EDITOR_USAGE = {'model': 'deepseek-fixture', 'operation': 'report_wording', 'attempts': [], 'audio_seconds': 0}


@pytest.fixture
def report(monkeypatch):
    monkeypatch.setattr(ai, '_chat', AsyncMock(return_value=({'strengths': [], 'recommendations': [
        {'title': 'Проясните срок', 'observation': 'В расшифровке указан день недели.',
         'action': 'Уточните, о какой пятнице идёт речь.', 'example': None, 'evidence_id': 's0-q1'}],
        'primary_recommendation_index': 0, 'criteria': []}, USAGE)))
    return asyncio.run(ai.analyze({}, SEGMENTS))['report']


def editorial(monkeypatch, mutate=None):
    async def reply(operation, system, data, *, model):
        assert model == 'deepseek-fixture'
        fields = [{'id': f['id'], 'text': f['text']} for f in data['fields']]
        if mutate:
            mutate(fields)
        return {'fields': fields}, EDITOR_USAGE
    monkeypatch.setenv('FEEDBACK_EDITOR_MODEL', 'deepseek-fixture')
    monkeypatch.setattr(ai, '_chat', reply)


def test_editor_preserves_assessment_and_derives_compatibility_fields(report, monkeypatch):
    original = copy.deepcopy(report)
    def change(fields):
        fields[-1]['text'] = 'Уточни, какую пятницу ты имеешь в виду.'
    editorial(monkeypatch, change)
    edited = asyncio.run(ai.reword_report(report))['report']
    assert report == original
    assert edited['recommendations'][0]['action'] != report['recommendations'][0]['action']
    assert edited['insight'] == edited['recommendations'][0]['action']
    assert edited['recommendations'][0]['text'].endswith(edited['insight'])
    for key in ['metrics', 'transcript', 'transcript_segments', 'transcript_revision', 'criteria', 'primary_recommendation_index']:
        assert edited[key] == original[key]
    for key in ['evidence', 'evidence_id', 'segment_index', 'start_char', 'end_char', 'transcript_revision', 'origin', 'example']:
        assert edited['recommendations'][0][key] == original['recommendations'][0][key]
    assert edited['provenance']['wording_editor']['model'] == 'deepseek-fixture'


@pytest.mark.parametrize('mutate', [
    lambda f: f.append(dict(f[0])),
    lambda f: f.pop(),
    lambda f: f[0].update(id='unrequested'),
    lambda f: f[0].update(text='Добавим 10 процентов'),
    lambda f: f[-1].update(text='Скажи «выдуманная цитата».'),
    lambda f: f[0].update(text='x' * 181),
    lambda f: f[0].update(max_chars=9999),
    lambda f: f[0].update(text='**Новый заголовок**'),
])
def test_invalid_editor_output_is_not_published(report, monkeypatch, mutate):
    original = copy.deepcopy(report)
    editorial(monkeypatch, mutate)
    with pytest.raises(ai.ProviderError) as exc:
        asyncio.run(ai.reword_report(report))
    assert exc.value.code == 'AI_WORDING_INVALID'
    assert exc.value.usage == EDITOR_USAGE
    assert report == original


def test_existing_report_requires_matching_revision_and_exact_evidence(report, monkeypatch):
    editorial(monkeypatch)
    report['provenance']['report_prompt_version'] = 'speech-feedback-v2.3'
    assert ai.can_reword_report({}, SEGMENTS, report)
    changed = copy.deepcopy(report);changed['recommendations'][0]['evidence'] = 'Другие слова'
    assert not ai.can_reword_report({}, SEGMENTS, changed)
    assert not ai.can_reword_report({}, [{**SEGMENTS[0], 'text': TEXT + ' Ещё мысль.'}], report)


def test_exact_readonly_cap_echo_is_ignored(report, monkeypatch):
    editorial(monkeypatch, lambda f: f[0].update(max_chars=180))
    edited = asyncio.run(ai.reword_report(report))['report']
    assert 'max_chars' not in edited['recommendations'][0]


def test_signed_number_cannot_change_during_wording(monkeypatch):
    editorial(monkeypatch, lambda f: f[0].update(text='Изменение составляет +10%'))
    with pytest.raises(ai.ProviderError):
        asyncio.run(ai._edited_fields('report', [{'id': 'field', 'text': 'Изменение составляет -10%', 'source': '', 'max_chars': 700}]))


def test_question_edit_keeps_source_binding_and_saved_text_aligned(monkeypatch):
    quote = ai._provenance(ai.build_context('questions', {}, SEGMENTS)['evidence'][1])
    old = ['Почему выбрана пятница?', 'При каком условии вы измените срок?', 'Что важно учесть при переносе?']
    original = {'questions': old, 'provenance': {'items': [{'text': q, **quote} for q in old]}, 'usage': USAGE}
    editorial(monkeypatch, lambda f: f[0].update(text='Почему ты выбрал пятницу?'))
    edited = asyncio.run(ai.reword_questions(original))
    assert original['questions'][0] == old[0]
    assert edited['questions'][0] == edited['provenance']['items'][0]['text']
    assert ai.question_provenance_matches(edited['provenance']['items'][0], edited['questions'][0], TEXT)


@pytest.mark.parametrize('bad', ['Почему пятница? Что дальше?', 'Почему пятница', 'Новый вопрос?'])
def test_question_editor_rejects_compound_incomplete_or_duplicate_questions(monkeypatch, bad):
    quote = ai._provenance(ai.build_context('questions', {}, SEGMENTS)['evidence'][1])
    old = ['Почему пятница?', 'Новый вопрос?', 'Когда это изменится?']
    response = {'questions': old, 'provenance': {'items': [{'text': q, **quote} for q in old]}, 'usage': USAGE}
    editorial(monkeypatch, lambda f: f[0].update(text=bad))
    with pytest.raises(ai.ProviderError):
        asyncio.run(ai.reword_questions(response))


@pytest.mark.parametrize('failure', [False, True])
def test_worker_reuses_existing_assessment_without_second_analysis(tmp_path, report, monkeypatch, failure):
    store = Store(tmp_path)
    report['provenance']['report_prompt_version'] = 'speech-feedback-v2.3'
    store.execute('INSERT INTO practices VALUES(?,?,?,?,?,?,?,?)', ('p', 'u', '{}', now(), 'processing', '[]', json.dumps(report), None))
    store.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)', ('s', 'p', 'speech', 0, 'speech.wav', 12, TEXT, now()))
    store.execute('INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)', ('j', 'p', 'report', 'pending', 'queued', now()))
    editorial(monkeypatch)
    analyze = AsyncMock();monkeypatch.setattr(ai, 'analyze', analyze)
    if failure:
        error = ai.ProviderError('AI_WORDING_INVALID', 'Не удалось подготовить текст.');error.usage = EDITOR_USAGE
        monkeypatch.setattr(ai, 'reword_report', AsyncMock(side_effect=error))
    asyncio.run(process(store, store.claim_job()))
    analyze.assert_not_awaited()
    assert len(store.all('SELECT * FROM usage')) == 1
    saved = json.loads(store.one('SELECT report FROM practices WHERE id="p"')['report'])
    assert saved == report if failure else saved['provenance']['wording_editor']['status'] == 'applied'
    assert store.one('SELECT transcript FROM segments WHERE id="s"')['transcript'] == TEXT


@pytest.mark.parametrize('failure', [False, True])
def test_worker_accounts_for_both_stages_on_success_and_failure(tmp_path, report, monkeypatch, failure):
    store = Store(tmp_path)
    store.execute('INSERT INTO practices VALUES(?,?,?,?,?,?,?,?)', ('p', 'u', '{}', now(), 'processing', '[]', None, None))
    store.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)', ('s', 'p', 'speech', 0, 'speech.wav', 12, TEXT, now()))
    store.execute('INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)', ('j', 'p', 'report', 'pending', 'queued', now()))
    editorial(monkeypatch)
    monkeypatch.setattr(ai, 'analyze', AsyncMock(return_value={'report': report, 'usage': USAGE}))
    if failure:
        error = ai.ProviderError('AI_WORDING_INVALID', 'Не удалось подготовить текст.');error.usage = EDITOR_USAGE
        monkeypatch.setattr(ai, 'reword_report', AsyncMock(side_effect=error))
    asyncio.run(process(store, store.claim_job()))
    assert [json.loads(u['data'])['model'] for u in store.all('SELECT data FROM usage ORDER BY created')] == ['gpt-fixture', 'deepseek-fixture']
    saved = store.one('SELECT report FROM practices WHERE id="p"')['report']
    assert saved is None if failure else json.loads(saved)['provenance']['wording_editor']['status'] == 'applied'
