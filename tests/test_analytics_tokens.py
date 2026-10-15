import json

from server import limits
from tests.test_analytics import setup, fixture_practice


def usage(store, user, pid, operation, counts):
    job = store.one('SELECT id FROM jobs WHERE practice_id=?', (pid,))['id']
    attempts = []
    with limits.provider_scope(store, user, job):
        for input_count, output_count in counts:
            reservation = limits.reserve_attempt(operation)
            limits.finish_attempt(reservation, 200, 10)
            attempts.append({'attempt_id': reservation[1], 'input_tokens': input_count,
                             'output_tokens': output_count})
    data = {'model': 'synthetic-text-model', 'operation': operation, 'attempts': attempts}
    store.usage({'id': job, 'user_id': user}, data)
    return job, data


def test_text_tokens_include_retries_editor_and_deduplicate_attempts(setup):
    app, owner, _, _, user, *_ = setup; store = app.state.store
    first, _ = fixture_practice(store, user); second, _ = fixture_practice(store, user)
    job, data = usage(store, user, first, 'report', [(100, 20), (80, 10)])
    store.usage({'id': job, 'user_id': user}, data)  # Same provider attempts, not new work.
    usage(store, user, first, 'report_wording', [(40, 5)])
    usage(store, user, second, 'questions', [(20, 0)])
    usage(store, user, first, 'transcription', [(1000, 1000)])
    report = owner.get('/api/admin/analytics/report').json()
    tokens = report['overview']['llm_tokens']
    assert tokens['total'] == tokens['known_total'] == 275
    assert tokens['known_input'] == 240 and tokens['known_output'] == 35
    assert tokens['calls'] == tokens['reported_calls'] == 4
    assert tokens['per_practice'] == 137.5 and tokens['per_user'] == 275
    rows = {p['id']: p['llm_tokens'] for p in owner.get('/api/admin/analytics/practices').json()['items']}
    assert rows[first]['total'] == 255 and rows[second]['total'] == 20


def test_unknown_calls_are_lower_bounds_and_known_zero_is_exact(setup):
    app, owner, _, _, user, *_ = setup; store = app.state.store
    first, _ = fixture_practice(store, user); second, _ = fixture_practice(store, user)
    job, _ = usage(store, user, first, 'report', [(100, 20), (None, None)])
    with limits.provider_scope(store, user, job):
        limits.reserve_attempt('report')  # Interrupted before usage was saved.
    usage(store, user, second, 'report', [(0, 0)])
    report = owner.get('/api/admin/analytics/report').json(); tokens = report['overview']['llm_tokens']
    assert tokens['total'] is None and tokens['per_practice'] is None
    assert tokens['known_total'] == 120 and tokens['known_per_practice'] == 60
    assert tokens['calls'] == 4 and tokens['reported_calls'] == 2
    rows = {p['id']: p['llm_tokens'] for p in owner.get('/api/admin/analytics/practices').json()['items']}
    assert rows[second]['total'] == 0 and rows[first]['total'] is None
    store.execute('DELETE FROM ai_attempts')
    assert owner.get('/api/admin/analytics/report').json()['overview']['llm_tokens'] == tokens


def test_partial_fields_do_not_turn_invalid_counts_into_tokens(setup):
    app, owner, _, _, user, *_ = setup; store = app.state.store
    pid, _ = fixture_practice(store, user)
    usage(store, user, pid, 'report', [(100, None), (True, -2)])
    tokens = owner.get('/api/admin/analytics/report').json()['overview']['llm_tokens']
    assert tokens['total'] is None and tokens['known_total'] == 100
    assert tokens['observed_calls'] == 1 and tokens['reported_calls'] == 0


def test_token_filters_and_exports_match_visible_metrics(setup):
    app, owner, _, admin, user, *_ = setup; store = app.state.store
    first, _ = fixture_practice(store, user); second, _ = fixture_practice(store, admin)
    usage(store, user, first, 'report', [(100, 20)])
    usage(store, admin, second, 'report', [(900, 20)])
    query = '&actor_id=' + user
    visible = owner.get('/api/admin/analytics/report?actor_id=' + user).json()['overview']['llm_tokens']
    summary = owner.get('/api/admin/analytics/export?dataset=summary&format=json' + query).json()
    practices = owner.get('/api/admin/analytics/export?dataset=practices&format=json' + query).json()
    assert visible['total'] == 120 and summary['rows'][0]['llm_tokens'] == visible
    assert summary['metadata']['llm_unit'] == 'tokens'
    assert 'gateway_unit' not in json.dumps(summary) and 'economy' not in summary['rows'][0]
    assert len(practices['rows']) == 1 and practices['rows'][0]['llm_tokens']['total'] == 120
    assert 'cost' not in practices['rows'][0]
    csv = owner.get('/api/admin/analytics/export?dataset=summary&format=csv' + query).text
    assert 'llm_tokens_total' in csv and 'gateway_unit' not in csv
