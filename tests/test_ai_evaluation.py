"""Evaluation integrity, budget and missing-label checks; no network or holdout content."""
import asyncio
from copy import deepcopy
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import evaluate_ai as evaluation
from server import ai, limits
from server.store import Store


class EvaluationTests(unittest.TestCase):
    def test_authored_corpus_split_and_baseline_integrity(self):
        result = evaluation.audit()
        self.assertEqual(result['split_counts'], {'development': 40, 'calibration': 20, 'acceptance': 60})
        self.assertFalse(result['acceptance_content_loaded'])
        self.assertIn('not measured', result['semantic_validation'])

    def test_holdout_never_opened_without_measured_gate(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('Must not inspect holdout')):
            with self.assertRaisesRegex(ValueError, 'locked'):
                evaluation.load_cases('acceptance')
        with self.assertRaisesRegex(ValueError, 'Proposed gates'):
            evaluation.load_cases('acceptance', evaluation.DATASET / 'proposed-gates.json')

    def test_baseline_probes_are_offline_and_do_not_claim_quality(self):
        result = evaluation.mechanical_baseline()
        self.assertEqual(result['provider_calls'], 0)
        self.assertFalse(result['semantic_quality_measured'])
        values = {p['probe']: p['accepted'] for p in result['probes']}
        self.assertTrue(values['invented_freestanding_insight'])
        self.assertTrue(values['unrequested_criteria'])
        self.assertFalse(values['empty_findings'])
        self.assertFalse(values['invalid_evidence_id'])

    def test_work_cap_preserves_reserved_unknown_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'data')
            ledger = evaluation.ExistingLedger(store.directory)
            budget = evaluation.RunBudget(ledger, 'eval-test', 1, 200, 100, limits.reserve_attempt)
            with limits.provider_scope(ledger, 'eval-user', 'eval-test'):
                reservation = budget('report', 0, 100, 50)
                self.assertIsNotNone(reservation)
                # First outcome stays unknown; second may not transmit or bypass the cap.
                with self.assertRaisesRegex(limits.LimitError, 'hard work cap'):
                    budget('report', 0, 1, 1)
                with self.assertRaises(limits.LimitError):
                    budget('ASR', 1, 0, 0)
            row = ledger.one('SELECT COUNT(*) AS n FROM ai_attempts WHERE job_id=?', ('eval-test',))
            self.assertEqual(row['n'], 1)

    def test_existing_ledger_never_initializes_missing_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'does not initialize'):
                evaluation.ExistingLedger(directory)
            self.assertFalse((Path(directory) / 'pilot.sqlite3').exists())

    def test_private_output_preflight_precedes_provider(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'data')
            public = Path(directory) / 'public'; public.mkdir(mode=0o755); public.chmod(0o755)
            opts = SimpleNamespace(live=True, max_attempts=2, max_input_chars=120000, max_output_tokens=6000,
                                   case_ids='dev-002-library', include_questions=False, data_dir=store.directory,
                                   output=public / 'paid.json')
            mocked = AsyncMock()
            with patch.dict(os.environ, {'LLM_API_KEY': 'test-only-not-a-provider-key', 'LLM_MAX_ATTEMPTS': '1'}), patch.object(ai, 'analyze', mocked):
                with self.assertRaisesRegex(ValueError, 'private'):
                    asyncio.run(evaluation.provider_run(opts))
            mocked.assert_not_awaited()
            self.assertEqual(public.stat().st_mode & 0o777, 0o755)
            self.assertFalse(opts.output.exists())

    def test_quote_membership_does_not_establish_semantics(self):
        case = evaluation.load_cases()[0]
        segment = case['input']['segments'][0]
        # Deliberately contradictory interpretation with perfectly valid provenance.
        item = {'title': 'Неправда', 'observation': 'Кэш не сохраняет результат.', 'evidence': segment['text'],
                'segment_index': 0, 'origin': 'speech', 'start_char': 0, 'end_char': len(segment['text']),
                'transcript_revision': segment['transcript_sha256']}
        report = {'schema_version': 2, 'strengths': [item], 'recommendations': [], 'criteria': [],
                  'primary_recommendation_index': None, 'insight': None}
        self.assertEqual(evaluation.provenance_errors(report, case), [])
        for bad_start in (False, -1, 0.0):
            bad = deepcopy(report); bad['strengths'][0]['start_char'] = bad_start
            self.assertIn('span_mismatch', evaluation.provenance_errors(bad, case))
        bad = deepcopy(report); bad['insight'] = 'Выдуманный самостоятельный совет'
        self.assertIn('unbound_primary_action', evaluation.provenance_errors(bad, case))
        bad = deepcopy(report); bad['strengths'][0]['transcript_revision'] = 'wrong'
        self.assertIn('revision_mismatch', evaluation.provenance_errors(bad, case))

    def test_blind_report_has_one_shared_shape_and_no_generator_identity(self):
        old = {'insight': 'Действие', 'strengths': [{'title': 'Заголовок', 'text': 'Наблюдение', 'evidence': 'Цитата', 'segment_index': 0}], 'recommendations': [], 'criteria': [], 'transcript': 'Текст'}
        new = {**old, 'schema_version': 2, 'provenance': {'chat_model': 'secret-generator-label'},
               'primary_recommendation_index': None, 'transcript_segments': [],
               'strengths': [{'title': 'Заголовок', 'text': 'Наблюдение', 'observation': 'Наблюдение',
                              'evidence': 'Цитата', 'segment_index': 0, 'evidence_id': 's0-q0', 'start_char': 0}]}
        self.assertEqual(evaluation.reviewer_report(old), evaluation.reviewer_report(new))
        self.assertNotIn('secret-generator-label', json.dumps(evaluation.reviewer_report(new)))

    def test_only_complete_pairs_are_counted_and_ratings_are_blank(self):
        artifacts = [{'case_id': 'dev-002-library', 'variant': 'baseline', 'result': {'report': {}}},
                     {'case_id': 'dev-002-library', 'variant': 'candidate', 'result': {'report': {}}},
                     {'case_id': 'dev-004-quiet-evenings', 'variant': 'baseline', 'result': {'report': {}}}]
        with tempfile.TemporaryDirectory() as directory:
            result = evaluation.blind(artifacts, directory)
            self.assertEqual(result['independent_case_pairs'], 1)
            rows = evaluation.read_json(Path(directory) / 'ratings-blank.json')
            summary = evaluation.rating_summary(rows)
            self.assertEqual(summary['independent_reviewers'], 0)
            self.assertEqual(summary['rated_case_count'], 0)
            self.assertIsNone(summary['dimensions']['grounding']['weighted_kappa'])
            for name in ('review-packets.json', 'ratings-blank.json', 'coordinator-key.json'):
                self.assertEqual((Path(directory) / name).stat().st_mode & 0o777, 0o600)

    def test_ordinal_bool_and_float_are_rejected(self):
        for value in (True, 1.0, -1, 4):
            with self.assertRaises(ValueError):
                evaluation.weighted_agreement([(value, 1)])
        exact = evaluation.weighted_agreement([(0, 0), (1, 1), (2, 2), (3, 3)])
        self.assertEqual(exact['weighted_kappa'], 1)
        self.assertIsNone(evaluation.weighted_agreement([(3, 3)])['weighted_kappa'])

    def test_confusion_reports_false_negatives_and_unknown_denominators(self):
        result = evaluation.confusion([(True, True), (True, False), (False, True), (False, False)])
        self.assertEqual(result['recall'], .5)
        self.assertEqual(result['precision'], .5)
        self.assertIsNone(evaluation.confusion([])['recall'])
        usage = evaluation.usage_summary([{'wall_latency_ms': 10, 'status': 'failed', 'usage': None},
                                          {'wall_latency_ms': 30, 'status': 'succeeded', 'result': {'usage': {'input_tokens': 40, 'output_tokens': 10}}}])
        self.assertIsNone(usage['input_tokens'])
        self.assertEqual(usage['unknown_usage_tasks'], 1)
        self.assertIsNone(usage['currency'])

    def test_seeded_challenges_have_reversed_views_without_quality_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            result = evaluation.challenge_packets(directory)
            self.assertEqual(result['paired_families'], 20)
            self.assertEqual(result['order_views'], 40)
            summary = evaluation.challenge_score(evaluation.read_json(Path(directory) / 'challenge-ratings-blank.json'),
                                                   evaluation.read_json(Path(directory) / 'challenge-coordinator-key.json'))
            self.assertIsNone(summary['seeded_choice_rate'])
            self.assertFalse(summary['semantic_report_quality_measured'])

    def test_preference_clusters_reversed_views_by_case(self):
        rows = [{'reviewer_id': 'r1', 'view_id': 'forward', 'case_id': 'dev-example', 'preference': 'A'},
                {'reviewer_id': 'r1', 'view_id': 'reverse', 'case_id': 'dev-example', 'preference': 'B'}]
        key = [{'view_id': 'forward', 'A': 'candidate', 'B': 'baseline'},
               {'view_id': 'reverse', 'A': 'baseline', 'B': 'candidate'}]
        result = evaluation.compare_preferences(rows, key)
        self.assertEqual(result['case_count'], 1)
        self.assertEqual(result['candidate_preference_with_ties'], 1)
        self.assertIsNone(result['case_bootstrap_95_interval'])
        self.assertFalse(result['quality_superiority_claim'])

    def test_mixed_report_question_replay_keeps_denominators(self):
        case = evaluation.load_cases()[0]
        source = case['input']['segments'][0]
        questions = ['Что хранится в кэше?', 'Когда используется результат?', 'Как связан запрос с результатом?']
        items = [{'text': q, 'evidence': source['text'], 'segment_index': 0, 'origin': 'speech',
                  'start_char': 0, 'end_char': len(source['text']), 'transcript_revision': source['transcript_sha256']} for q in questions]
        artifacts = [{'case_id':case['case_id'],'variant':'baseline','operation':'questions', 'result':{'questions':questions}},
                     {'case_id':case['case_id'],'variant':'candidate','operation':'questions', 'result':{'questions':questions,'provenance':{'items':items}}}]
        result = evaluation.replay(artifacts)
        self.assertEqual(result['denominator'],2)
        self.assertEqual(result['mechanical_passes'],2)
        self.assertFalse(result['semantic_quality_measured'])
        bad = deepcopy(artifacts); bad[1]['result']['provenance']['items'][0]['text']='Другой вопрос'
        self.assertIn('question_text_binding',evaluation.replay(bad)['checks'][1]['errors'])

    def test_provider_draft_retained_before_failed_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory)/'data')
            opts = SimpleNamespace(live=True,max_attempts=1,max_input_chars=120000,max_output_tokens=3000,
                                   case_ids='dev-002-library',variants='candidate',include_questions=False,
                                   data_dir=store.directory,output=Path(directory)/'run.json')
            invalid_draft={'strengths':[], 'recommendations':[]}  # Missing closed v2 keys.
            async def fake_chat(operation,system,data):
                limits.reserve_attempt(operation,0,100,50)
                return invalid_draft,{'model':'mocked-only','attempts':[]}
            with patch.dict(os.environ,{'LLM_API_KEY':'test-only-not-a-provider-key','LLM_MAX_ATTEMPTS':'1'}), patch.object(ai,'_chat',fake_chat):
                result=asyncio.run(evaluation.provider_run(opts))
            self.assertEqual(result['attempts'],1)
            artifact=evaluation.read_json(opts.output)['artifacts'][0]
            self.assertEqual(artifact['error_code'],'AI_UNGROUNDED_REPORT')
            self.assertEqual(artifact['parsed_provider_draft'],invalid_draft)
            self.assertIn('request_context',artifact)
            self.assertEqual(artifact['system_prompt_sha256'],hashlib.sha256(artifact['system_prompt'].encode()).hexdigest())
            self.assertIn('feedback_prompts',artifact['source_sha256'])
            self.assertEqual(opts.output.stat().st_mode & 0o777,0o600)

    def test_gate_freeze_rejects_no_humans_or_injected_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            proposal=deepcopy(evaluation.read_json(evaluation.DATASET/'proposed-gates.json'))
            proposal['latency_and_work_budgets']={'max_wall_latency_ms':5000,'max_attempts':6}
            for name,value in [('proposal.json',proposal),('provider.json',{'artifacts':[]}),('ratings.json',[]),('key.json',[])]:
                evaluation.private_json(folder/name,value)
            with self.assertRaisesRegex(ValueError,'real-provider baseline'):
                evaluation.freeze_gates(folder/'proposal.json',folder/'provider.json',folder/'ratings.json',folder/'key.json',folder/'frozen.json')
            evaluation.private_json(folder/'provider.json',{'artifacts':[{'mode':'real_text_provider','case_id':'dev-002-library','variant':'baseline','operation':'report','status':'succeeded','result':{'report':{'transcript':'Synthetic'}}}]})
            with self.assertRaisesRegex(ValueError,'Two independent'):
                evaluation.freeze_gates(folder/'proposal.json',folder/'provider.json',folder/'ratings.json',folder/'key.json',folder/'frozen.json')
            self.assertFalse((folder/'frozen.json').exists())

    def test_live_requires_one_attempt_retry_and_no_calls_by_default(self):
        opts = SimpleNamespace(live=False)
        with self.assertRaisesRegex(ValueError, '--live'):
            asyncio.run(evaluation.provider_run(opts))
        self.assertEqual(len(evaluation.provider_tasks(['dev-002-library','dev-004-quiet-evenings'], True)), 6)
