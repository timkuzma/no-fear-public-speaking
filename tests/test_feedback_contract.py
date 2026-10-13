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


@pytest.mark.parametrize('example', feedback_prompts.REPORT_EXAMPLES)
def test_application_owned_full_json_examples_validate(example, monkeypatch):
    # Prompt examples must use the actual compiler, including canonical evidence IDs,
    # exact quote spans and original criterion IDs, rather than an obsolete schema.
    inputs = example['input']
    source = max((span['text'] for span in inputs['evidence']), key=len)
    criteria = '; '.join(item['text'] for item in inputs['requested_criteria'])
    provider = AsyncMock(return_value=(example['output'], USAGE))
    monkeypatch.setattr(ai, '_chat', provider)
    report = asyncio.run(ai.analyze({'criteria': criteria}, [
        {'index': 0, 'kind': 'speech', 'text': source, 'duration_seconds': 10,
         'asr_quality': inputs.get('asr_quality')}]))['report']
    assert report['primary_recommendation_index'] == example['output']['primary_recommendation_index']
    for item in report['strengths'] + report['recommendations']:
        assert item['evidence'] == source[item['start_char']:item['end_char']]



def test_unreviewed_rewrite_is_withheld_everywhere_but_raw_draft_is_unchanged(monkeypatch):
    # An exploratory provider draft invented these causal benefits. A valid quote
    # doesn't establish either one, so neither public example nor compatibility text
    # may reproduce them. This guards one field; it is not semantic entailment testing.
    invented = 'Это позволит экономить время и даст возможность пользоваться книгами после уроков.'
    output = draft()
    output['recommendations'][0]['example'] = invented
    original = json.loads(json.dumps(output))
    report = run(output, monkeypatch)
    assert report['recommendations'][0]['example'] is None
    assert invented not in json.dumps(report, ensure_ascii=False)
    assert report['recommendations'][0]['text'] == ' '.join([
        output['recommendations'][0]['observation'], output['recommendations'][0]['action']])
    assert report['insight'] == output['recommendations'][0]['action']
    assert report['transcript'] == TEXT
    assert report['provenance']['publisher_policy'] == 'withhold_unreviewed_rewrites-v1'
    assert output == original
    assert output['recommendations'][0]['example'] == invented


@pytest.mark.parametrize('raw', ['', 'x' * (feedback_prompts.CAPS['example'] + 1), [], 12])
def test_withholding_does_not_accept_malformed_raw_example(raw, monkeypatch):
    output = draft()
    output['recommendations'][0]['example'] = raw
    with pytest.raises(ai.ProviderError) as failure:
        run(output, monkeypatch)
    assert failure.value.code == 'AI_UNGROUNDED_REPORT'



def test_one_requested_criterion_keeps_independent_findings(monkeypatch):
    example = feedback_prompts.REPORT_EXAMPLES[-1]
    provider = AsyncMock(return_value=(example['output'], USAGE))
    monkeypatch.setattr(ai, '_chat', provider)
    source = example['input']['evidence'][-1]['text']
    report = asyncio.run(ai.analyze({'criteria': 'На слова паразиты'}, [
        {'index': 0, 'kind': 'speech', 'text': source, 'duration_seconds': 15}]))['report']
    assert len(report['criteria']) == 1
    assert len(report['strengths']) == len(report['recommendations']) == 1
    assert report['recommendations'][0]['evidence'] == example['input']['evidence'][1]['text']
    assert report['insight'] == report['recommendations'][0]['action']
    assert report['provenance']['coaching_context_version'] == 'speech-coaching-v1'


@pytest.mark.parametrize('field,value', [
    ('observation', "В речи есть 'друзья' и 'то есть'."),
    ('action', 'Произнесите «Совершенно новый факт».')])
def test_inline_quotation_must_belong_to_selected_evidence(monkeypatch, field, value):
    output = draft()
    output['recommendations'][0][field] = value
    with pytest.raises(ai.ProviderError) as error:
        run(output, monkeypatch)
    assert error.value.code == 'AI_UNGROUNDED_REPORT'


def test_inline_original_words_are_valid_without_changing_source(monkeypatch):
    output = draft()
    output['recommendations'][0]['observation'] = 'В этой фразе назван «Новый срок».'
    output['recommendations'][0]['action'] = 'Уточните слово «пятница» при следующей попытке.'
    report = run(output, monkeypatch)
    assert report['recommendations'][0]['evidence'] == 'Новый срок — пятница.'



def test_compound_question_cannot_start_a_double_task(monkeypatch):
    provider = AsyncMock(return_value=({'questions':[
        {'text':'Почему выбрана пятница? Как это повлияет на встречу?', 'evidence_id':'s0-q1'},
        {'text':'Какие обстоятельства важны для нового срока?', 'evidence_id':'s0-q1'},
        {'text':'При каком условии вы изменили бы срок?', 'evidence_id':'s0-q1'}]},USAGE))
    monkeypatch.setattr(ai,'_chat',provider)
    with pytest.raises(ai.ProviderError) as error:
        asyncio.run(ai.generate_questions({},TEXT))
    assert error.value.code == 'AI_INVALID_RESPONSE'


def test_question_cannot_quote_another_evidence_span(monkeypatch):
    provider = AsyncMock(return_value=({'questions': [
        {'text': 'Что означает «Новый срок» для встречи?', 'evidence_id': 's0-q0'},
        {'text': 'Какие обстоятельства важны для нового срока?', 'evidence_id': 's0-q1'},
        {'text': 'При каком условии вы изменили бы срок?', 'evidence_id': 's0-q1'}]}, USAGE))
    monkeypatch.setattr(ai, '_chat', provider)
    with pytest.raises(ai.ProviderError) as error:
        asyncio.run(ai.generate_questions({}, TEXT))
    assert error.value.code == 'AI_INVALID_RESPONSE'
