import asyncio
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import time
import uuid
from unittest.mock import patch

import httpx
from server import limits
from server.analytics_costs import reconcile,sync_costs
from tests.test_analytics import setup,fixture_practice


def attempt(store,user,pid,*,price=None,at=None):
    at=at or time.time()-10
    job=store.one('SELECT id FROM jobs WHERE practice_id=?',(pid,))['id']
    with limits.provider_scope(store,user,job):
        reservation=limits.reserve_attempt('report');limits.finish_attempt(reservation,200,2000,price)
    aid=reservation[1]
    store.execute("UPDATE analytics_events SET occurred=? WHERE kind='provider_attempt_started' AND json_extract(data,'$.attempt_id')=?",(at,aid))
    store.execute("UPDATE analytics_events SET occurred=? WHERE kind='provider_attempt_finished' AND json_extract(data,'$.attempt_id')=?",(at+2,aid))
    store.usage({'id':job,'user_id':user},{'model':'gpt-5.4','operation':'report','attempts':[{'attempt_id':aid,'input_tokens':100,'output_tokens':40}]})
    iso=lambda value:datetime.fromtimestamp(value,timezone.utc).isoformat()
    return {'request_id':uuid.uuid4().hex,'model':'openai/openai/gpt-5.4','spend':.5,'prompt_tokens':100,'completion_tokens':40,'startTime':iso(at+.1),'endTime':iso(at+1.9)},aid


def test_reconcile_recovers_unknown_price_and_is_idempotent(setup):
    app,owner,_,_,user,*_=setup;s=app.state.store;pid,_=fixture_practice(s,user)
    row,aid=attempt(s,user,pid)
    with s.connect() as db:
        assert reconcile(db,[row],apply=False)['matched']==1
    assert owner.get('/api/admin/analytics/report').json()['overview']['economy']['total'] is None
    with s.connect() as db:assert reconcile(db,[row])['matched']==1
    with s.connect() as db:assert reconcile(db,[row])['matched']==0
    o=owner.get('/api/admin/analytics/report').json()['overview']['economy']
    assert o['total']==o['known_total']==.5 and o['priced_attempts']==1
    value=json.loads(s.one('SELECT data FROM analytics_events WHERE event_id=?',('cost:'+aid,))['data'])
    assert value['price_source']=='provider_spend_log' and value['provider_request_id']==row['request_id']


def test_reconcile_refuses_ambiguous_or_mismatched_rows(setup):
    app,_,_,_,user,*_=setup;s=app.state.store;pid,_=fixture_practice(s,user)
    row,_=attempt(s,user,pid)
    with s.connect() as db:
        assert reconcile(db,[row,row|{'request_id':uuid.uuid4().hex}])['matched']==0
        assert reconcile(db,[row|{'prompt_tokens':101}])['matched']==0
        assert reconcile(db,[row|{'model':'unrelated-model'}])['matched']==0
        assert reconcile(db,[row|{'spend':float('nan')}])['matched']==0
        assert reconcile(db,[row|{'spend':-1}])['matched']==0


def test_request_id_recovers_price_without_timestamp_heuristic(setup):
    app,owner,_,_,user,*_=setup;s=app.state.store;pid,_=fixture_practice(s,user)
    row,aid=attempt(s,user,pid)
    with s.connect() as db:
        usage=db.execute('SELECT id,data FROM usage WHERE user_id=?',(user,)).fetchone()
        value=json.loads(usage['data']);value['attempts'][0]['provider_request_id']=row['request_id']
        db.execute('UPDATE usage SET data=? WHERE id=?',(json.dumps(value),usage['id']))
        assert reconcile(db,[row|{'startTime':None,'endTime':None,'spend':0}])['matched']==1
        assert reconcile(db,[row|{'spend':0}])['matched']==0
    assert owner.get('/api/admin/analytics/report').json()['overview']['economy']['total']==0


def test_reconcile_never_charges_one_vendor_call_to_two_practices(setup):
    app,_,_,_,user,*_=setup;s=app.state.store
    a,_=fixture_practice(s,user);b,_=fixture_practice(s,user);at=time.time()-10
    row,_=attempt(s,user,a,at=at);attempt(s,user,b,at=at)
    with s.connect() as db:assert reconcile(db,[row])['matched']==0


def test_reconcile_keeps_header_price_and_known_zero(setup):
    app,owner,_,_,user,*_=setup;s=app.state.store;pid,_=fixture_practice(s,user)
    row,_=attempt(s,user,pid,price=0)
    with s.connect() as db:assert reconcile(db,[row])['matched']==0
    assert owner.get('/api/admin/analytics/report').json()['overview']['economy']['total']==0


def test_partial_cost_averages_remain_known_lower_bounds(setup):
    app,owner,_,_,user,*_=setup;s=app.state.store
    first,_=fixture_practice(s,user);second,_=fixture_practice(s,user)
    attempt(s,user,first,price=.5);attempt(s,user,second)
    o=owner.get('/api/admin/analytics/report').json()['overview']['economy']
    assert o['total'] is None and o['per_practice'] is None
    assert o['known_total']==.5 and o['known_per_practice']==.25 and o['known_per_user']==.5


def test_cost_sync_is_scoped_get_cached_and_keeps_prices_on_failure(setup,monkeypatch):
    app,owner,other,_,user,*_=setup;s=app.state.store;pid,_=fixture_practice(s,user)
    row,_=attempt(s,user,pid)
    monkeypatch.setenv('APP_ENV','production');monkeypatch.setenv('LLM_BASE_URL','https://provider.test/v1');monkeypatch.setenv('LLM_API_KEY','synthetic-test-key')
    requests=[];original=httpx.AsyncClient
    def handler(request):
        requests.append(request)
        assert request.method=='GET' and request.url.path=='/spend/logs'
        assert request.url.params['api_key']!='synthetic-test-key'
        return httpx.Response(200,json=[row])
    with patch('server.analytics_costs.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(handler),**kw)):
        assert other.get('/api/admin/analytics/report').status_code==403
        assert not requests
        assert owner.get('/api/admin/analytics/report').status_code==200
        assert not requests  # Token dashboards do not depend on a billing network request.
        asyncio.run(sync_costs(s))
        assert owner.get('/api/admin/analytics/report').json()['overview']['economy']['total']==.5
        asyncio.run(sync_costs(s));assert len(requests)==1
    s.execute("DELETE FROM analytics_meta WHERE key='cost_sync_at'")
    with patch('server.analytics_costs.httpx.AsyncClient',side_effect=lambda **kw:original(transport=httpx.MockTransport(lambda r:httpx.Response(503)),**kw)):
        asyncio.run(sync_costs(s))
    monkeypatch.setenv('APP_ENV','development')
    assert owner.get('/api/admin/analytics/report').json()['overview']['economy']['total']==.5
