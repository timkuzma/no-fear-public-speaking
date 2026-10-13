"""V2 structural checks: these do not measure semantic feedback quality."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from server import ai, feedback_prompts
from server.store import Store, now
from server.worker import process


TEXT = 'Мы перенесли встречу, потому что зал закрыт. Новый срок — пятница.'
SEGMENTS = [{'index': 0, 'kind': 'speech', 'text': TEXT, 'duration_seconds': 12}]
USAGE = {'model': 'fixture', 'operation': 'report', 'input_tokens': 10, 'output_tokens': 10,
         'attempts': [], 'audio_seconds': 0, 'latency_ms': 1}


def draft():
    return {'strengths': [], 'recommendations': [
        {'title': 'Проясните срок', 'observation': 'В расшифровке указан день недели.',
         'action': 'Уточните, о какой пятнице идёт речь, если это важно слушателю.',
         'example': None, 'evidence_id': 's0-q1'}],
        'primary_recommendation_index': 0, 'criteria': []}


def run(output, monkeypatch, config=None):
    provider = AsyncMock(return_value=(output, USAGE))
    monkeypatch.setattr(ai, '_chat', provider)
    return asyncio.run(ai.analyze(config or {}, SEGMENTS))['report']


def test_sparse_and_null_focus_are_honest(monkeypatch):
    report = run({'strengths': [], 'recommendations': [], 'primary_recommendation_index': None, 'criteria': []}, monkeypatch)
    assert report['insight'] is None
    assert report['recommendations'] == []
    assert report['strengths'] == []
    assert report['schema_version'] == 2
    assert report['provenance']['asr_model_unknown'] is True
    assert report['provenance']['asr_models'] == []


def test_primary_comes_only_from_validated_action(monkeypatch):
    output = draft()
    report = run(output, monkeypatch)
    assert report['insight'] == output['recommendations'][0]['action']
    output['primary_recommendation_index'] = None
    assert run(output, monkeypatch)['insight'] is None


@pytest.mark.parametrize('index', [True, False, -1, 1, '0', [], {}])
def test_invalid_primary_cannot_publish(index, monkeypatch):
    output = draft()
    output['primary_recommendation_index'] = index
    with pytest.raises(ai.ProviderError) as error:
        run(output, monkeypatch)
    assert error.value.code == 'AI_UNGROUNDED_REPORT'
    assert error.value.usage == USAGE


@pytest.mark.parametrize('mutation', [
    lambda d: d['recommendations'].append({**d['recommendations'][0], 'unknown': 'extra'}),
    lambda d: d.update(strengths=[{'title': 'Цель', 'observation': 'Текст', 'evidence_id': 's0-q0'}] * 3),
    lambda d: d.update(recommendations=d['recommendations'] * 4),
    lambda d: d['recommendations'][0].update(action='x' * (feedback_prompts.CAPS['action'] + 1)),
    lambda d: d['recommendations'][0].update(example=''),
    lambda d: d['recommendations'][0].update(observation=[]),
])
def test_closed_fields_counts_and_lengths(mutation, monkeypatch):
    output = draft()
    mutation(output)
    with pytest.raises(ai.ProviderError):
        run(output, monkeypatch)


def test_context_separates_spoken_answer_saved_question_and_repeat_focus(monkeypatch):
    segments = [*SEGMENTS, {'index': 1, 'kind': 'answer', 'text': 'Да, в эту пятницу.',
                           'duration_seconds': 3, 'question': 'Вы имеете в виду эту пятницу?'}]
    focus = {'source_practice_id': 'owned-source', 'recommendation_index': 0,
             'title': 'Срок', 'action': 'Проясните срок.'}
    context = ai.build_context('report', {'repeat_focus': focus}, segments)
    assert context['context']['repeat_focus'] == focus
    assert context['requested_criteria'] == []
    assert context['segments'][1]['text'] == 'Да, в эту пятницу.'
    assert 'question' not in context['segments'][1]
    assert context['saved_questions'] == [{'answer_segment_index': 1, 'text': segments[1]['question'], 'provenance': None}]
    assert all(q['text'] != segments[1]['question'] for q in context['evidence'])
    assert all(q['origin'] == ('speech' if q['segment_index'] == 0 else 'answer') for q in context['evidence'])
    assert all(s['lexical_completeness'] == 'unknown' for s in context['segments'])
    assert context['transcript_revision'] != ai.build_context('report', {}, SEGMENTS)['transcript_revision']


def seed(store):
    store.execute('INSERT INTO practices(id,user_id,config,created) VALUES(?,?,?,?)',
                  ('practice', 'user', json.dumps({'questions': True}), now()))
    store.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',
                  ('speech', 'practice', 'speech', 0, 'speech.wav', 12, TEXT, now()))
    store.execute('INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)',
                  ('questions-job', 'practice', 'questions', 'pending', 'queued', now()))


def test_questions_persist_private_provenance_and_reject_changed_source(tmp_path, monkeypatch):
    store = Store(tmp_path)
    seed(store)
    response = {'questions': [{'text': q, 'evidence_id': 's0-q0'} for q in (
        'Почему зал оказался закрыт?', 'Как закрытие зала влияет на встречу?', 'Как вы узнали о закрытии зала?')]}
    monkeypatch.setattr(ai, '_chat', AsyncMock(return_value=(response, USAGE)))
    asyncio.run(process(store, store.claim_job()))
    practice = store.one('SELECT * FROM practices WHERE id=?', ('practice',))
    provenance = json.loads(practice['question_provenance'])
    assert provenance['prompt_version'] == feedback_prompts.QUESTIONS_VERSION
    assert provenance['items'][0]['transcript_revision'] == ai.transcript_revision(TEXT)
    public_job = json.loads(store.one('SELECT result FROM jobs WHERE id=?', ('questions-job',))['result'])
    assert set(public_job) == {'questions'}
    assert isinstance(public_job['questions'][0], str)
    store.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',
                  ('answer', 'practice', 'answer', 1, 'answer.wav', 3, 'Так сообщил администратор.', now()))
    store.execute('UPDATE segments SET transcript=? WHERE id=?', ('Теперь речь о другом.', 'speech'))
    store.execute('INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)',
                  ('report-job', 'practice', 'report', 'pending', 'queued', now()))
    analyzer = AsyncMock()
    monkeypatch.setattr(ai, 'analyze', analyzer)
    asyncio.run(process(store, store.claim_job()))
    job = store.one('SELECT * FROM jobs WHERE id=?', ('report-job',))
    assert job['status'] == 'failed'
    assert json.loads(job['error'])['code'] == 'AI_INPUT_INVALID'
    analyzer.assert_not_awaited()
    assert store.one('SELECT COUNT(*) AS count FROM segments')['count'] == 2


def test_revision_checks_exact_question_span_and_hash():
    context = ai.build_context('questions', {}, SEGMENTS)
    question = 'Почему закрыт зал?'
    evidence = {'text': question, **ai._provenance(context['evidence'][0])}
    assert ai.question_provenance_matches(evidence, question, TEXT)
    for corrupted in ({**evidence, 'text': 'Другой вопрос?'}, {**evidence, 'evidence_id': 's0-q999'},
                      {**evidence, 'start_char': 1}, {**evidence, 'end_char': True},
                      {**evidence, 'transcript_revision': '0' * 64}, {**evidence, 'origin': 'answer'}):
        assert not ai.question_provenance_matches(corrupted, question, TEXT)
    assert not ai.question_provenance_matches(evidence, question, TEXT + ' ')


def test_adjacent_relation_span_stays_contiguous():
    text = 'Мне нравится этот город.\nНо именно отсюда я хочу уехать.'
    spans = ai._quote_candidates([{'index': 0, 'text': text}])
    assert [s['id'] for s in spans] == ['s0-q0', 's0-q1', 's0-p0']
    relation = spans[-1]
    assert relation['text'] == text
    assert relation['start_char'] == 0
    assert relation['end_char'] == len(text)


def test_known_capture_or_asr_doubt_survives_context_without_certifying_words(monkeypatch):
    provider = AsyncMock(return_value=({'strengths': [], 'recommendations': [], 'primary_recommendation_index': None, 'criteria': []}, USAGE))
    monkeypatch.setattr(ai, '_chat', provider)
    asyncio.run(ai.analyze({}, [{**SEGMENTS[0], 'capture_complete': False, 'asr_quality': 'uncertain'}]))
    context = provider.await_args.args[2]
    assert context['segments'][0]['capture_complete'] is False
    assert context['segments'][0]['asr_quality'] == 'uncertain'
    assert context['segments'][0]['lexical_completeness'] == 'unknown'
    complete = ai.build_context('report', {}, [{**SEGMENTS[0], 'capture_complete': True, 'asr_quality': 'reliable'}])
    assert complete['segments'][0]['lexical_completeness'] == 'unknown'
    assert complete['segments'][0]['asr_quality'] == 'unknown'
