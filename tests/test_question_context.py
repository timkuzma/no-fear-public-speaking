"""Persisted audience questions provide context, never evidence of spoken words."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from server import ai
from server.store import Store, now
from server.worker import process


QUESTIONS = [
    'Кто будет пользоваться библиотекой?',
    'Какие расходы потребуется оценить?',
    'Как вы будете проверять спрос?',
]
SPEECH = 'Мы хотим открыть библиотеку рядом со школой.'
ANSWER = 'Там ученики смогут готовиться к урокам.'
USAGE = {'model': 'fixture', 'input_tokens': 10, 'output_tokens': 5,
         'audio_seconds': 0, 'latency_ms': 1, 'operation': 'report'}


def response():
    return {
        'primary_recommendation_index': 0,
        'strengths': [{'title': 'Понятна аудитория', 'observation': 'Названы ученики.',
                       'evidence_id': 's1-q0'}],
        'recommendations': [{'title': 'Уточните совместную подготовку', 'observation': 'Польза обозначена кратко.',
                             'action': 'Поясните, как ученики будут готовиться вместе.', 'example': None,
                             'evidence_id': 's1-q0'}],
        'criteria': [],
    }


def segments():
    return [
        {'index': 0, 'kind': 'speech', 'text': SPEECH, 'duration_seconds': 10},
        {'index': 1, 'kind': 'answer', 'text': ANSWER, 'duration_seconds': 5,
         'question': QUESTIONS[0]},
    ]


def test_worker_maps_persisted_questions_by_answer_index(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.execute('INSERT INTO practices(id,user_id,config,created,questions) VALUES(?,?,?,?,?)',
                  ('practice', 'user', json.dumps({'questions': True}), now(), json.dumps(QUESTIONS)))
    # Insert in a different order so list position cannot substitute for segment index.
    for index in (3, 0, 2, 1):
        store.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',
                      (f'segment-{index}', 'practice', 'speech' if index == 0 else 'answer',
                       index, f'{index}.wav', 5, SPEECH if index == 0 else ANSWER, now()))
    store.execute('INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)',
                  ('job', 'practice', 'report', 'pending', 'queued', now()))
    analyzer = AsyncMock(return_value={'report': {'demo': False}, 'usage': USAGE})
    transcriber = AsyncMock()
    monkeypatch.setattr(ai, 'analyze', analyzer)
    monkeypatch.setattr(ai, 'transcribe', transcriber)

    asyncio.run(process(store, store.claim_job()))

    assert store.one('SELECT status FROM jobs WHERE id=?', ('job',))['status'] == 'succeeded'
    prepared = analyzer.await_args.args[1]
    assert 'question' not in prepared[0]
    assert [item['index'] for item in prepared] == [0, 1, 2, 3]
    assert [item['question'] for item in prepared[1:]] == QUESTIONS
    transcriber.assert_not_awaited()


def test_report_payload_keeps_questions_out_of_spoken_evidence_and_metrics(monkeypatch):
    provider = AsyncMock(return_value=(response(), USAGE))
    monkeypatch.setattr(ai, '_chat', provider)

    result = asyncio.run(ai.analyze({}, segments()))

    payload = provider.await_args.args[2]
    assert payload['saved_questions'][0]['text'] == QUESTIONS[0]
    assert 'question' not in payload['segments'][1]
    assert [quote['text'] for quote in payload['evidence']] == [SPEECH, ANSWER]
    assert result['report']['transcript'] == SPEECH + '\n\n' + ANSWER
    assert result['report']['strengths'][0]['evidence'] == ANSWER
    assert result['report']['metrics'][1]['text'] == '13 слов'


def test_question_text_cannot_be_used_as_spoken_evidence(monkeypatch):
    output = response()
    output['strengths'][0] = {'title': 'Пример', 'text': 'Обоснование.',
                              'evidence': QUESTIONS[0], 'segment_index': 1}
    monkeypatch.setattr(ai, '_chat', AsyncMock(return_value=(output, USAGE)))

    with pytest.raises(ai.ProviderError) as failure:
        asyncio.run(ai.analyze({}, segments()))

    assert failure.value.code == 'AI_UNGROUNDED_REPORT'


@pytest.mark.parametrize('question', ['', ' ' * 4, 'x' * 601, None, 12, {'text': 'Вопрос?'}])
def test_invalid_question_context_is_rejected_before_provider_call(question, monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr(ai, '_chat', provider)
    input_segments = segments()
    input_segments[1]['question'] = question

    with pytest.raises(ai.ProviderError) as failure:
        asyncio.run(ai.analyze({}, input_segments))

    assert failure.value.code == 'AI_INPUT_INVALID'
    provider.assert_not_awaited()
