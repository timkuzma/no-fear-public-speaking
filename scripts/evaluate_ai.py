"""Offline speech-feedback evaluation. Provider access is an explicit, bounded opt-in.

Author expectations, injected outputs, human ratings and live outputs stay separate.
No result of this script certifies semantic correctness merely from evidence IDs.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import statistics
import stat
import sys
import time
from unittest.mock import AsyncMock, patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATASET = ROOT / 'evals/speech-feedback'
DIMENSIONS = ('grounding', 'relevance', 'actionability', 'fact_preservation', 'prioritization', 'genre_fit', 'clarity_tone')
FAILURES = ('invented_fact', 'unsupported_modality', 'injection_execution', 'wrong_source', 'imposed_criterion')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if stat.S_IMODE(path.parent.stat().st_mode) & 0o077:
        raise ValueError('Evaluation output directory must already be private (0700)')
    # Outputs can contain test transcripts and provider responses; never world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def verify_baseline():
    folder = DATASET / 'baseline'
    manifest = read_json(folder / 'manifest.json')
    for name, expected in manifest['files_sha256'].items():
        if digest(folder / name) != expected:
            raise ValueError('Frozen baseline source hash mismatch: ' + name)
    return manifest


def acceptance_authorized(gates=None):
    if gates is None:
        raise ValueError('Acceptance is locked: baseline human measurement and frozen gates required')
    value = read_json(gates)
    baseline = value.get('baseline_measurement') or {}
    if (value.get('status') != 'frozen_after_measured_baseline' or
            baseline.get('provider_reports', 0) < 1 or baseline.get('human_reviewed_reports', 0) < 1 or
            baseline.get('independent_reviewers', 0) < 2):
        raise ValueError('Proposed gates cannot unlock acceptance; real baseline and two reviewers are required')
    for key in ('provider_artifact', 'human_ratings', 'blinding_key'):
        evidence = value.get('measurement_artifacts', {}).get(key, {})
        if not evidence.get('path') or not evidence.get('sha256') or digest(evidence['path']) != evidence['sha256']:
            raise ValueError('Frozen gates require matching private baseline/reviewer evidence artifacts')
    return value


def freeze_gates(proposal, provider_artifact, ratings_file, blinding_key, output):
    """Freeze operator-reviewed gates only after real baseline and reviewer data exist."""
    gates = read_json(proposal)
    if not isinstance(gates.get('latency_and_work_budgets'),dict) or not gates['latency_and_work_budgets']:
        raise ValueError('Operator must set measured latency/work budgets before freezing gates')
    provider = read_json(provider_artifact)
    artifacts = provider.get('artifacts',[]) if isinstance(provider,dict) else []
    baseline_reports = [a for a in artifacts if a.get('mode')=='real_text_provider' and a.get('variant')=='baseline' and
                        a.get('operation')=='report' and a.get('status')=='succeeded' and a.get('result',{}).get('report')]
    if not baseline_reports:
        raise ValueError('A successful real-provider baseline report is required; injected fixtures do not count')
    ratings = read_json(ratings_file)
    keys = {k['view_id']: k for k in read_json(blinding_key)}
    rated = {}
    baseline_ids = {a['case_id'] for a in baseline_reports}
    for row in ratings:
        if not row.get('reviewer_id') or row['case_id'] not in baseline_ids: continue
        mapping = keys.get(row['view_id'],{})
        label = next((k for k in ('A','B') if mapping.get(k)=='baseline'),None)
        if label is None: continue
        dimensions = row[label]['dimensions']
        failures = row[label]['critical_failures']
        # Both reviewers must assess baseline grounding/actionability and all critical flags.
        for d in ('grounding','actionability'):
            value = dimensions.get(d)
            if type(value) is not int or value not in range(4): break
        else:
            if all(type(failures.get(f)) is bool for f in FAILURES):
                rated.setdefault(row['case_id'],set()).add(row['reviewer_id'])
    complete = {c: reviewers for c,reviewers in rated.items() if len(reviewers)>=2}
    if not complete:
        raise ValueError('Two independent completed human baseline ratings are required; blanks or abstentions do not unlock holdout')
    gates['status']='frozen_after_measured_baseline'
    gates['baseline_measurement']={'provider_reports':len(baseline_reports),'human_reviewed_reports':len(complete),
                                 'independent_reviewers':len(set(r for rows in complete.values() for r in rows)),
                                 'baseline_id':verify_baseline()['baseline_id']}
    gates['measurement_artifacts']={k:{'path':str(Path(path).resolve()),'sha256':digest(path)} for k,path in
                                   [('provider_artifact',provider_artifact),('human_ratings',ratings_file),('blinding_key',blinding_key)]}
    gates['acceptance_authorized']=True
    gates['qualification']='Frozen operational thresholds after measured baseline; not achieved quality or scientific standards. Operator attests reviewer independence; software cannot prove human identity.'
    private_json(output,gates)
    return {'status':gates['status'],'baseline_measurement':gates['baseline_measurement'],'output':str(output),
            'quality_acceptance_passed':False}


def load_cases(split='development', gates=None):
    if split == 'acceptance':
        acceptance_authorized(gates)
    manifest = read_json(DATASET / 'manifest.json')
    item = manifest['splits'][split]
    path = DATASET / item['path']
    if digest(path) != item['sha256']:
        raise ValueError('Corpus hash differs from frozen manifest: ' + split)
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    if len(rows) != item['count']:
        raise ValueError('Corpus count mismatch')
    return rows


def audit():
    """Verify locked file bytes/count metadata without loading acceptance content."""
    baseline = verify_baseline()
    manifest = read_json(DATASET / 'manifest.json')
    ids, families = set(), set()
    for split, item in manifest['splits'].items():
        if digest(DATASET / item['path']) != item['sha256']:
            raise ValueError('Corpus hash mismatch: ' + split)
        if len(item['case_ids']) != item['count'] or len(set(item['families'])) != item['count']:
            raise ValueError('Duplicate case or family in ' + split)
        if ids.intersection(item['case_ids']) or families.intersection(item['families']):
            raise ValueError('Case/family leakage between splits')
        ids.update(item['case_ids']); families.update(item['families'])
    for split in ('development', 'calibration'):
        for case in load_cases(split):
            if case['annotations']['annotation_status'] != 'author_expectations_not_human_gold':
                raise ValueError('Synthetic annotation status must be explicit')
            for span in case['annotations']['evidence_spans']:
                source = next(s for s in case['input']['segments'] if s['index'] == span['segment_index'])
                if source['text'][span['start']:span['end']] != span['text']:
                    raise ValueError('Annotation span mismatch')
                if hashlib.sha256(source['text'].encode()).hexdigest() != span['transcript_sha256']:
                    raise ValueError('Annotation transcript hash mismatch')
    return {'baseline_id': baseline['baseline_id'], 'split_counts': {k: v['count'] for k, v in manifest['splits'].items()},
            'family_overlap': 0, 'acceptance_content_loaded': False, 'source_type': manifest['source_type'],
            'semantic_validation': 'not measured; author expectations are not human gold'}


def baseline_module():
    verify_baseline()
    spec = importlib.util.spec_from_file_location('server.eval_frozen_baseline', DATASET / 'baseline/server/ai.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mechanical_baseline():
    """Replay known probes into the original validator, with NO network or model."""
    module = baseline_module()
    segments = [{'index': 0, 'kind': 'speech', 'text': 'Кэш хранит результат. Повторный запрос берёт его из кэша.', 'duration_seconds': 15}]
    good = {'insight': 'Вы уже повысили продажи на 80 процентов.',
            'strengths': [{'title': 'Сохранён результат', 'text': 'Описано хранение результата.', 'evidence_id': 's0-q0'}],
            'recommendations': [{'title': 'Уточнить ссылку', 'text': 'Заменить его на результат.', 'evidence_id': 's0-q0'}], 'criteria': []}
    probes = [('invented_freestanding_insight', good),
              ('empty_findings', {**good, 'strengths': [], 'recommendations': []}),
              ('invalid_evidence_id', {**good, 'recommendations': [{**good['recommendations'][0], 'evidence_id': 'missing'}]}),
              ('unrequested_criteria', {**good, 'criteria': [{'criterion_id': 'never_selected', 'status': 'met', 'evidence_id': 's0-q0'}]})]
    async def execute():
        output = []
        for name, payload in probes:
            with patch.object(module, '_chat', AsyncMock(return_value=(payload, {'model': 'injected-fixture', 'attempts': []}))):
                try:
                    result = await module.analyze({}, segments)
                    output.append({'probe': name, 'accepted': True, 'criteria_count': len(result['report']['criteria'])})
                except module.ProviderError as error:
                    output.append({'probe': name, 'accepted': False, 'error_code': error.code})
        return output
    return {'mode': 'injected_offline_baseline', 'provider_calls': 0, 'human_ratings': 0,
            'semantic_quality_measured': False, 'baseline': verify_baseline()['baseline_id'], 'probes': asyncio.run(execute())}


def provenance_errors(report, case):
    """Exact source membership/hash/binding only; deliberately no entailment grade."""
    errors = []
    sources = {s['index']: s for s in case['input']['segments']}
    for collection in ('strengths', 'recommendations', 'criteria'):
        for item in report.get(collection, []):
            quote = item.get('evidence', '')
            if not quote:
                if collection != 'criteria' or item.get('status') != 'unknown':
                    errors.append('missing_evidence')
                continue
            index = item.get('segment_index')
            source = sources.get(index)
            if source is None:
                errors.append('unknown_segment'); continue
            if quote not in source['text']:
                errors.append('quote_not_in_source')
            if report.get('schema_version') == 2:
                start, end = item.get('start_char'), item.get('end_char')
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source['text']) or source['text'][start:end] != quote:
                    errors.append('span_mismatch')
                expected = hashlib.sha256(source['text'].encode('utf-8')).hexdigest()
                if item.get('transcript_revision') != expected:
                    errors.append('revision_mismatch')
                if item.get('origin') != source['kind']:
                    errors.append('origin_mismatch')
    if report.get('schema_version') == 2:
        primary = report.get('primary_recommendation_index')
        recs = report.get('recommendations', [])
        if primary is not None:
            if not isinstance(primary, int) or isinstance(primary, bool) or not 0 <= primary < len(recs):
                errors.append('primary_index_invalid')
            elif report.get('insight') != recs[primary].get('action'):
                errors.append('unbound_primary_action')
        elif report.get('insight') is not None:
            errors.append('unbound_primary_action')
    if not case['input']['config']['criteria'] and report.get('criteria'):
        errors.append('unselected_criteria')
    return sorted(set(errors))


def question_errors(result, case):
    questions = result.get('questions')
    if not isinstance(questions,list) or len(questions)!=3 or any(not isinstance(q,str) or not 8<=len(q)<=600 for q in questions):
        return ['invalid_question_contract']
    if len({q.casefold() for q in questions})!=3:
        return ['duplicate_question_strings']
    provenance = result.get('provenance')
    if provenance is None:
        return []  # Legacy: no new provenance exists; do not pretend to reconstruct it.
    items = provenance.get('items',[])
    if len(items)!=len(questions):
        return ['question_provenance_count']
    errors=provenance_errors({'schema_version':2,'strengths':items,'recommendations':[], 'criteria':[],
                              'primary_recommendation_index':None,'insight':None},case)
    for question,item in zip(questions,items):
        if item.get('text')!=question: errors.append('question_text_binding')
        if item.get('segment_index')!=0 or item.get('origin')!='speech':errors.append('question_wrong_origin')
    return sorted(set(errors))


def replay(artifacts, split='development', gates=None):
    cases = {c['case_id']: c for c in load_cases(split, gates)}
    result = []
    for item in artifacts:
        case = cases.get(item['case_id'])
        if case is None:
            raise ValueError('Artifact case does not belong to requested split')
        payload = item.get('result', {})
        report = payload.get('report')
        if item.get('operation')=='questions':
            errors = question_errors(payload,case)
        else:
            errors = provenance_errors(report, case) if report else ['no_report']
        result.append({'case_id': item['case_id'], 'variant': item['variant'], 'operation':item.get('operation','report'), 'errors': errors})
    return {'checks': result, 'mechanical_passes': sum(not i['errors'] for i in result), 'denominator': len(result),
            'semantic_quality_measured': False, 'quality_claim': 'Only structural provenance was checked'}


class ExistingLedger:
    """Use existing container SQLite only; never invoke schema creation/migrations."""
    def __init__(self, directory):
        self.path = Path(directory) / 'pilot.sqlite3'
        if not self.path.is_file():
            raise ValueError('Existing private ledger required; this script does not initialize one')
        with self.connect() as db:
            if db.execute("SELECT name FROM sqlite_master WHERE name='ai_attempts'").fetchone() is None:
                raise ValueError('Existing durable ai_attempts table required')
    @contextmanager
    def connect(self):
        db = sqlite3.connect('file:' + str(self.path.resolve()) + '?mode=rw', uri=True, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()
    def one(self, sql, args=()):
        with self.connect() as db:
            row = db.execute(sql, args).fetchone()
            return dict(row) if row else None
    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).rowcount


class RunBudget:
    def __init__(self, ledger, run_id, max_attempts, max_input_chars, max_output_tokens, reserve):
        self.ledger, self.run_id, self.reserve = ledger, run_id, reserve
        self.max_attempts, self.max_input_chars, self.max_output_tokens = max_attempts, max_input_chars, max_output_tokens
    def __call__(self, operation, audio_seconds=0, input_chars=0, output_tokens=0):
        from server import limits
        used = self.ledger.one('SELECT COUNT(*) AS n,COALESCE(SUM(input_chars),0) AS chars,COALESCE(SUM(output_tokens),0) AS tokens FROM ai_attempts WHERE job_id=?', (self.run_id,))
        if (audio_seconds != 0 or used['n'] + 1 > self.max_attempts or
                used['chars'] + input_chars > self.max_input_chars or used['tokens'] + output_tokens > self.max_output_tokens):
            raise limits.LimitError('EVAL_RUN_LIMIT', 'Evaluation hard work cap reached before transmission')
        # The maintained reservation checks global/user caps, rate limit and pause too.
        return self.reserve(operation, audio_seconds, input_chars, output_tokens)


def provider_tasks(case_ids, questions=False, variants=('baseline', 'candidate')):
    tasks = [(case_id, variant, 'report') for case_id in case_ids for variant in variants]
    if questions:
        tasks.extend((case_ids[0], variant, 'questions') for variant in variants)
    return tasks


async def provider_run(options):
    from server import ai, limits
    if not options.live:
        raise ValueError('Provider calls require --live')
    if not 1 <= options.max_attempts <= 6:
        raise ValueError('Hard limit: 1–6 HTTP attempts per evaluation run')
    if not 1 <= options.max_input_chars <= 300000 or not 1 <= options.max_output_tokens <= 18000:
        raise ValueError('Explicit bounded input/output work caps required')
    if os.getenv('LLM_MAX_ATTEMPTS') != '1':
        raise ValueError('Set LLM_MAX_ATTEMPTS=1; evaluation does not silently change retry policy')
    if not os.getenv('LLM_API_KEY'):
        raise ValueError('Provider credential must be supplied privately by environment')
    cases = {c['case_id']: c for c in load_cases('development')}
    ids = options.case_ids.split(',')
    if len(set(ids)) != len(ids) or any(c not in cases for c in ids):
        raise ValueError('Use distinct development case IDs')
    variants = getattr(options, 'variants', 'baseline,candidate').split(',')
    if len(set(variants)) != len(variants) or any(v not in ('baseline','candidate') for v in variants):
        raise ValueError('Choose baseline,candidate or an explicit nonduplicate subset')
    tasks = provider_tasks(ids, options.include_questions, variants)
    if len(tasks) > options.max_attempts:
        raise ValueError('Planned tasks exceed hard attempt cap')
    ledger = ExistingLedger(options.data_dir)
    run_id = 'eval-' + uuid.uuid4().hex
    frozen = baseline_module()
    if options.output.exists():
        raise ValueError('Choose a new evaluation output path; do not overwrite a previous run')
    private_json(options.output, {'run_id': run_id, 'complete': False, 'artifacts': []})
    budget = RunBudget(ledger, run_id, options.max_attempts, options.max_input_chars, options.max_output_tokens, limits.reserve_attempt)
    results = []
    # Empty explicit user identity is forbidden; an eval-specific identity stays in ledger.
    with patch.object(limits, 'reserve_attempt', budget), limits.provider_scope(ledger, 'evaluation-private', run_id):
        for case_id, variant, operation in tasks:
            module = frozen if variant == 'baseline' else ai
            case = cases[case_id]
            began = time.monotonic()
            item = {'case_id': case_id, 'variant': variant, 'operation': operation, 'mode': 'real_text_provider',
                    'source_sha256': {'ai': digest(DATASET / 'baseline/server/ai.py' if variant=='baseline' else ROOT / 'server/ai.py')},
                    'prompt_versions': {'prompt': module.PROMPT_VERSION}}
            if variant=='candidate':
                from server import feedback_prompts
                item['source_sha256']['feedback_prompts'] = digest(ROOT / 'server/feedback_prompts.py')
                item['prompt_versions'].update(questions=feedback_prompts.QUESTIONS_VERSION,report=feedback_prompts.REPORT_VERSION,context=feedback_prompts.CONTEXT_VERSION,rubric=feedback_prompts.RUBRIC_VERSION)
            original_chat = module._chat
            async def capture_chat(chat_operation, system, data):
                # Keep request context and parsed draft privately, before downstream validation.
                item['request_context'] = data
                item['system_prompt'] = system
                item['system_prompt_sha256'] = hashlib.sha256(system.encode('utf-8')).hexdigest()
                private_json(options.output, {'run_id': run_id, 'complete': False, 'artifacts': [*results, item]})
                draft, chat_usage = await original_chat(chat_operation, system, data)
                item['parsed_provider_draft'] = draft
                item['draft_usage'] = chat_usage
                private_json(options.output, {'run_id': run_id, 'complete': False, 'artifacts': [*results, item]})
                return draft, chat_usage
            try:
                with patch.object(module, '_chat', capture_chat):
                    if operation == 'report':
                        item['result'] = await module.analyze(case['input']['config'], case['input']['segments'])
                    else:
                        item['result'] = await module.generate_questions(case['input']['config'], case['input']['segments'][0]['text'])
                item['status'] = 'succeeded'
            except module.ProviderError as error:
                item.update(status='failed', error_code=error.code, usage=getattr(error, 'usage', None))
            except Exception:
                # Never serialize exception details which might contain credentials/endpoints.
                item.update(status='failed', error_code='EVAL_INTERNAL_ERROR')
            item['wall_latency_ms'] = round((time.monotonic() - began) * 1000)
            results.append(item)
            private_json(options.output, {'run_id': run_id, 'complete': False, 'artifacts': results})
    usage = ledger.one('SELECT COUNT(*) AS attempts,COALESCE(SUM(input_chars),0) AS reserved_input_chars,COALESCE(SUM(output_tokens),0) AS reserved_output_tokens FROM ai_attempts WHERE job_id=?', (run_id,))
    output = {'run_id': run_id, 'complete': True, 'baseline': verify_baseline(),
              'candidate_source_sha256': {'server/ai.py': digest(ROOT / 'server/ai.py'), 'server/feedback_prompts.py': digest(ROOT / 'server/feedback_prompts.py')},
              'dataset_version': read_json(DATASET / 'manifest.json')['dataset_version'], 'split': 'development',
              'hard_caps': {'attempts': options.max_attempts, 'input_chars': options.max_input_chars, 'output_tokens': options.max_output_tokens},
              'ledger': usage, 'billing_currency': None, 'actual_billing': None, 'response_model_identity': 'unavailable; usage.model is a configured alias, not an immutable provider revision',
              'human_ratings': 0, 'semantic_quality_measured': False, 'artifacts': results}
    private_json(options.output, output)
    return {'output': str(options.output), 'attempts': usage['attempts'], 'successes': sum(x['status'] == 'succeeded' for x in results), 'human_review': 'pending'}


def blind(artifacts, destination, seed=7):
    """Emit anonymous pairs/blank ratings; identity key stays coordinator-private."""
    grouped = {}
    for item in artifacts:
        if item.get('status', 'succeeded') != 'succeeded' or item.get('operation', 'report') != 'report':
            continue
        grouped.setdefault(item['case_id'], {})[item['variant']] = item['result']['report']
    cases = {c['case_id']: c for c in load_cases('development') + load_cases('calibration')}
    rng = random.Random(seed)
    packets, keys, blanks = [], [], []
    for case_id, variants in grouped.items():
        if set(variants) != {'baseline', 'candidate'}:
            continue
        if case_id not in cases:
            raise ValueError('Blinding unknown or locked case is not authorized')
        labels = ['baseline', 'candidate']; rng.shuffle(labels)
        pair_id = uuid.uuid4().hex[:12]
        # Reverse order is another view of SAME clustered case, not extra independent n.
        for reversed_order in (False, True):
            order = labels[::-1] if reversed_order else labels
            view_id = pair_id + ('-reverse' if reversed_order else '-forward')
            packets.append({'pair_id': pair_id, 'view_id': view_id, 'case_id': case_id, 'input': cases[case_id]['input'],
                            'A': reviewer_report(variants[order[0]]), 'B': reviewer_report(variants[order[1]])})
            keys.append({'view_id': view_id, 'A': order[0], 'B': order[1]})
            blanks.append({'pair_id': pair_id, 'view_id': view_id, 'case_id': case_id, 'reviewer_id': '', 'preference': None,
                           'A': {'dimensions': {d: None for d in DIMENSIONS}, 'critical_failures': {f: None for f in FAILURES}, 'reasons': [], 'claim_assessments': [], 'rewrite_checks': [], 'criterion_checks': []},
                           'B': {'dimensions': {d: None for d in DIMENSIONS}, 'critical_failures': {f: None for f in FAILURES}, 'reasons': [], 'claim_assessments': [], 'rewrite_checks': [], 'criterion_checks': []}})
    destination = Path(destination)
    private_json(destination / 'review-packets.json', packets)
    private_json(destination / 'ratings-blank.json', blanks)
    private_json(destination / 'coordinator-key.json', keys)
    return {'independent_case_pairs': len(packets)//2, 'review_views': len(packets), 'ratings_filled': 0}


def reviewer_report(report):
    """Same presentation for legacy and v2: minimize schema/version identification.

    This hides labels, not behavior: a null focus still honestly appears empty.
    Reviewers must not guess generator identity; residual stylistic bias remains.
    """
    def finding(item):
        body = item.get('text', '')
        if report.get('schema_version') == 2:
            body = '\n'.join(v for v in (item.get('observation'), item.get('action'),
                                          'Возможная формулировка: ' + item['example'] if item.get('example') else None) if v)
        return {'title': item.get('title', ''), 'body': body, 'quote': item.get('evidence', ''),
                'source_segment_index': item.get('segment_index')}
    return {'main_focus': report.get('insight'),
            'strengths': [finding(i) for i in report.get('strengths', [])],
            'recommendations': [finding(i) for i in report.get('recommendations', [])],
            'criteria': [{'label': i.get('criterion'), 'status': i.get('status'), 'reason': i.get('reason', ''),
                          'quote': i.get('evidence', '')} for i in report.get('criteria', [])],
            'transcript': report.get('transcript', '')}


def strip_identity(value):
    if isinstance(value, list):
        return [strip_identity(v) for v in value]
    if isinstance(value, dict):
        return {k: strip_identity(v) for k, v in value.items() if k not in ('schema_version', 'provenance', 'usage', 'prompt_version', 'model', 'asr_model', 'transcript_revision')}
    return value


def weighted_agreement(pairs):
    if not pairs:
        return {'n': 0, 'exact': None, 'weighted_kappa': None}
    if any(type(a) is not int or type(b) is not int or a not in range(4) or b not in range(4) for a, b in pairs):
        raise ValueError('Ordinal ratings must be integers 0–3')
    n = len(pairs)
    observed = sum(1 - abs(a-b)/3 for a, b in pairs)/n
    pa = [sum(a == i for a, _ in pairs)/n for i in range(4)]
    pb = [sum(b == j for _, b in pairs)/n for j in range(4)]
    expected = sum(pa[i]*pb[j]*(1-abs(i-j)/3) for i in range(4) for j in range(4))
    return {'n': n, 'exact': sum(a == b for a,b in pairs)/n, 'weighted_kappa': (observed-expected)/(1-expected) if expected < 1 else None,
            'weighting': 'linear distance / 3; undefined with degenerate marginals'}


def confusion(pairs):
    if any(type(a) is not bool or type(b) is not bool for a,b in pairs):
        raise ValueError('Failure labels must be boolean, not confidence scores')
    tp = sum(a and b for a,b in pairs); fp = sum(not a and b for a,b in pairs)
    fn = sum(a and not b for a,b in pairs); tn = sum(not a and not b for a,b in pairs)
    return {'n': len(pairs), 'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn, 'precision': tp/(tp+fp) if tp+fp else None,
            'recall': tp/(tp+fn) if tp+fn else None, 'exact': (tp+tn)/len(pairs) if pairs else None,
            'reference': 'Reviewer 1 is comparison reference, not automatically ground truth'}


def rating_summary(ratings):
    grouped = {}
    for row in ratings:
        if not row.get('reviewer_id'):
            continue
        key = (row['view_id'], row['case_id'])
        if row['reviewer_id'] in grouped.setdefault(key, {}):
            raise ValueError('Duplicate reviewer/view rating')
        grouped[key][row['reviewer_id']] = row
    dimensions = {}; failures = {}
    reviewers = set(r for rows in grouped.values() for r in rows)
    if len(reviewers) > 2:
        raise ValueError('Choose two reviewers explicitly; do not select a flattering subset')
    for dimension in DIMENSIONS:
        pairs = []
        for rows in grouped.values():
            if len(rows) != 2: continue
            a,b = [rows[r] for r in sorted(rows)]
            for label in ('A','B'):
                x,y = a[label]['dimensions'].get(dimension), b[label]['dimensions'].get(dimension)
                if x not in (None, 'not_assessable') and y not in (None, 'not_assessable'): pairs.append((x,y))
        dimensions[dimension] = weighted_agreement(pairs)
    for failure in FAILURES:
        pairs = []
        for rows in grouped.values():
            if len(rows) != 2: continue
            a,b = [rows[r] for r in sorted(rows)]
            for label in ('A','B'):
                x,y = a[label]['critical_failures'].get(failure),b[label]['critical_failures'].get(failure)
                if x not in (None, 'not_assessable') and y not in (None, 'not_assessable'):pairs.append((x,y))
        failures[failure] = confusion(pairs)
    missing = {d: {'unfilled': sum(row[label]['dimensions'].get(d) is None for rows in grouped.values() for row in rows.values() for label in ('A','B')), 'not_assessable': sum(row[label]['dimensions'].get(d) == 'not_assessable' for rows in grouped.values() for row in rows.values() for label in ('A','B'))} for d in DIMENSIONS}
    return {'independent_reviewers': len(reviewers), 'rated_case_count': len({k[1] for k in grouped}), 'missing_dimensions': missing,
            'dimensions': dimensions, 'failure_comparisons': failures,
            'warning': 'Reverse views are correlated; agreements are diagnostics, not independent quality sample size. No blank is interpreted as pass.'}


def challenge_packets(destination, seed=11):
    manifest = read_json(DATASET / 'manifest.json')['challenge_pairs']
    if digest(DATASET / manifest['path']) != manifest['sha256']:
        raise ValueError('Challenge pair hash mismatch')
    pairs = [json.loads(line) for line in (DATASET / manifest['path']).read_text(encoding='utf-8').splitlines()]
    cases = {c['case_id']: c for c in load_cases('development')}
    rng = random.Random(seed)
    packets, blanks, key = [], [], []
    for pair in pairs:
        order = ['grounded','fluent_but_wrong']; rng.shuffle(order)
        for reverse in (False,True):
            labels = order[::-1] if reverse else order
            view = pair['pair_id'] + ('-reverse' if reverse else '-forward')
            packets.append({'view_id': view, 'pair_id': pair['pair_id'], 'case_id': pair['case_id'],
                            'input': cases[pair['case_id']]['input'],
                            'A': pair['options'][labels[0]]['feedback'], 'B': pair['options'][labels[1]]['feedback']})
            good = 'A' if labels[0] == 'grounded' else 'B'
            key.append({'view_id': view, 'pair_id': pair['pair_id'], 'grounded_choice': good,
                        'expected_failures': {label: pair['options'][name]['expected_critical_failures'] for label,name in zip(('A','B'),labels)}})
            blanks.append({'view_id': view, 'pair_id': pair['pair_id'], 'reviewer_id': '', 'choice': None,
                           'predicted_failures': {'A': {f: None for f in FAILURES}, 'B': {f: None for f in FAILURES}}, 'reason': ''})
    destination = Path(destination)
    private_json(destination / 'challenge-packets.json', packets)
    private_json(destination / 'challenge-ratings-blank.json', blanks)
    private_json(destination / 'challenge-coordinator-key.json', key)
    return {'paired_families': len(pairs), 'order_views': len(packets), 'human_or_model_decisions': 0,
            'expected_labels': 'Author seeded failures, not adjudicated human gold'}


def challenge_score(ratings, key):
    keys = {k['view_id']: k for k in key}
    scored, outcomes, failures = [], {}, {f: [] for f in FAILURES}
    seen = set()
    for row in ratings:
        if not row.get('reviewer_id'): continue
        identifier = (row['reviewer_id'],row['view_id'])
        if identifier in seen: raise ValueError('Duplicate challenge decision')
        seen.add(identifier)
        reference = keys[row['view_id']]
        choice = row.get('choice')
        if choice not in (None,'A','B','tie','not_assessable'): raise ValueError('Invalid choice')
        if choice in ('A','B'):
            scored.append(choice == reference['grounded_choice'])
            outcomes.setdefault((row['reviewer_id'],reference['pair_id']),[]).append(choice == reference['grounded_choice'])
        for label in ('A','B'):
            for failure in FAILURES:
                prediction = row.get('predicted_failures',{}).get(label,{}).get(failure)
                if prediction not in (None,'not_assessable'):
                    failures[failure].append((failure in reference['expected_failures'][label],prediction))
    complete = [v for v in outcomes.values() if len(v)==2]
    return {'decision_denominator':len(scored), 'correct_seeded_choices':sum(scored),
            'seeded_choice_rate':sum(scored)/len(scored) if scored else None,
            'reversal_pairs_assessed':len(complete), 'reversal_consistency':sum(a==b for a,b in complete)/len(complete) if complete else None,
            'failure_detection':{f:{**confusion(pairs),'reference':'Author-seeded challenge label, not adjudicated human ground truth'} for f,pairs in failures.items()},
            'semantic_report_quality_measured':False,
            'qualification':'Diagnostic against author-seeded labels; reversed views are paired and not independent speeches'}


def compare_preferences(ratings, key, seed=19):
    keys={k['view_id']:k for k in key}
    cases={};seen=set()
    for row in ratings:
        preference=row.get('preference')
        if not row.get('reviewer_id') or preference in (None,'not_assessable'):continue
        if preference not in ('A','B','tie'):raise ValueError('Invalid preference')
        identity=(row['reviewer_id'],row['view_id'])
        if identity in seen:raise ValueError('Duplicate preference')
        seen.add(identity)
        mapping=keys[row['view_id']]
        value=.5 if preference=='tie' else float(mapping[preference]=='candidate')
        cases.setdefault(row['case_id'],[]).append(value)
    means=[statistics.mean(values) for values in cases.values()]
    if not means:return {'case_count':0,'candidate_preference_with_ties':None,'case_bootstrap_95_interval':None,'quality_superiority_claim':False}
    rng=random.Random(seed)
    samples=sorted(statistics.mean(rng.choices(means,k=len(means))) for _ in range(2000)) if len(means)>1 else []
    return {'case_count':len(means),'rating_views':sum(map(len,cases.values())),
            'candidate_preference_with_ties':statistics.mean(means),
            'case_bootstrap_95_interval':[samples[49],samples[1949]] if samples else None,
            'quality_superiority_claim':False,
            'qualification':'Exploratory resampling across synthetic case families; averages reverse views/reviewers within case. Not a production population interval or automatic gate.'}


def usage_summary(artifacts):
    latencies = sorted(a['wall_latency_ms'] for a in artifacts if 'wall_latency_ms' in a)
    usage = [a.get('result', {}).get('usage') or a.get('usage') for a in artifacts]
    def sum_known(field):
        values = [u.get(field) if isinstance(u, dict) else None for u in usage]
        return sum(values) if values and all(isinstance(x,(int,float)) for x in values) else None
    return {'tasks': len(artifacts), 'failures': sum(a.get('status')=='failed' for a in artifacts),
            'latency_p50_ms': statistics.median(latencies) if latencies else None,
            'latency_p95_ms': latencies[max(0, math.ceil(.95*len(latencies))-1)] if latencies else None,
            'input_tokens': sum_known('input_tokens'), 'output_tokens': sum_known('output_tokens'),
            'unknown_usage_tasks': sum(u is None or u.get('input_tokens') is None or u.get('output_tokens') is None for u in usage),
            'actual_billing': None, 'currency': None, 'semantic_quality_measured': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('audit')
    p = sub.add_parser('baseline-mechanical'); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('freeze-gates'); p.add_argument('--proposal',type=Path,required=True); p.add_argument('--provider-artifact',type=Path,required=True); p.add_argument('--ratings',type=Path,required=True); p.add_argument('--key',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    p = sub.add_parser('replay'); p.add_argument('--artifacts', type=Path, required=True); p.add_argument('--split', choices=('development','calibration','acceptance'), default='development'); p.add_argument('--gates', type=Path)
    p = sub.add_parser('provider'); p.add_argument('--live', action='store_true'); p.add_argument('--data-dir', type=Path, required=True); p.add_argument('--case-ids', required=True); p.add_argument('--variants', default='baseline,candidate'); p.add_argument('--include-questions', action='store_true'); p.add_argument('--max-attempts', type=int, default=6); p.add_argument('--max-input-chars', type=int, default=120000); p.add_argument('--max-output-tokens', type=int, default=18000); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('blind'); p.add_argument('--artifacts', type=Path, required=True); p.add_argument('--destination', type=Path, required=True); p.add_argument('--seed', type=int, default=7)
    p = sub.add_parser('ratings'); p.add_argument('--ratings', type=Path, required=True)
    p = sub.add_parser('challenge-packets'); p.add_argument('--destination', type=Path, required=True)
    p = sub.add_parser('challenge-score'); p.add_argument('--ratings', type=Path, required=True); p.add_argument('--key', type=Path, required=True)
    p = sub.add_parser('compare'); p.add_argument('--ratings', type=Path, required=True); p.add_argument('--key', type=Path, required=True)
    p = sub.add_parser('usage'); p.add_argument('--artifacts', type=Path, required=True)
    opts = parser.parse_args()
    if opts.command=='audit': value=audit()
    elif opts.command=='baseline-mechanical': value=mechanical_baseline(); private_json(opts.output,value)
    elif opts.command=='provider': value=asyncio.run(provider_run(opts))
    elif opts.command=='freeze-gates': value=freeze_gates(opts.proposal,opts.provider_artifact,opts.ratings,opts.key,opts.output)
    elif opts.command=='ratings': value=rating_summary(read_json(opts.ratings))
    elif opts.command=='challenge-packets': value=challenge_packets(opts.destination)
    elif opts.command=='challenge-score': value=challenge_score(read_json(opts.ratings),read_json(opts.key))
    elif opts.command=='compare': value=compare_preferences(read_json(opts.ratings),read_json(opts.key))
    else:
        payload=read_json(opts.artifacts); artifacts=payload.get('artifacts',[]) if isinstance(payload,dict) else payload
        if opts.command=='replay':value=replay(artifacts,opts.split,opts.gates)
        elif opts.command=='blind':value=blind(artifacts,opts.destination,opts.seed)
        else:value=usage_summary(artifacts)
    print(json.dumps(value,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
