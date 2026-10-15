import hashlib
import io
import json
import time
import uuid
import zipfile
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from server.app import create_app
from server.analytics_events import grant_owner
from server.store import Store


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','development');monkeypatch.delenv('APP_ORIGIN',raising=False);monkeypatch.delenv('REQUIRE_INVITE',raising=False)
    app=create_app(tmp_path,start_worker=False);owner=TestClient(app);other=TestClient(app)
    def register(client,email):
        r=client.post('/api/auth/register',json={'email':email,'name':'Fixture','password':'TestPassword2026'});assert r.status_code==200,r.text
        return r.json()['user']['id'],{'X-CSRF-Token':r.json()['csrf_token']}
    oid,headers=register(owner,'owner@example.test');uid,other_headers=register(other,'other@example.test');grant_owner(app.state.store,'owner@example.test')
    return app,owner,other,oid,uid,headers,other_headers


def fixture_practice(store,uid,questions=False,report=True,days=14,answers=3):
    pid=uuid.uuid4().hex;at=time.time()-days*86400
    with store.connect() as db:
        db.execute('INSERT INTO practices(id,user_id,config,created) VALUES(?,?,?,?)',(pid,uid,json.dumps({'scenario':'speech','duration':3,'questions':questions}),at))
        sid=uuid.uuid4().hex;file=sid+'.wav';(store.media/file).write_bytes(b'fixture-media')
        db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',(sid,pid,'speech',0,file,42,'Synthetic source',at+10))
        if questions:
            for index in range(1,answers+1):db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,pid,'answer',index,file,10,'Synthetic answer',at+20+index))
        if report:
            jid=uuid.uuid4().hex;value={'schema_version':2,'recommendations':[],'strengths':[],'criteria':[],'provenance':{'report_prompt_version':'speech-feedback-v2.4'}}
            db.execute('INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)',(jid,pid,'report','pending','queued',at+25))
            db.execute("UPDATE jobs SET status='succeeded',stage='complete',finished=?,result=? WHERE id=?",(at+30,json.dumps(value),jid))
            db.execute("UPDATE practices SET status='ready',report=? WHERE id=?",(json.dumps(value),pid))
    return pid,sid


def test_access_is_account_bound_and_exclusive(setup):
    app,owner,other,oid,uid,h,oh=setup
    assert owner.get('/api/auth/me').json()['user']['analytics_access'] is True
    assert other.get('/api/auth/me').json()['user']['analytics_access'] is False
    assert other.get('/api/admin/analytics/report').status_code==403
    assert TestClient(app).get('/api/admin/analytics/report').status_code==401
    grant_owner(app.state.store,'other@example.test')
    assert owner.get('/api/admin/analytics/report').status_code==403
    assert other.get('/api/admin/analytics/report').status_code==200


def test_metrics_distinct_and_branches_and_refresh(setup):
    app,owner,other,oid,uid,h,oh=setup;s=app.state.store
    p1,_=fixture_practice(s,uid);p2,_=fixture_practice(s,uid,True);p3,_=fixture_practice(s,uid,True,answers=1)
    # Two report versions do not add another practice, speech or completion.
    with s.connect() as db:
        jid=uuid.uuid4().hex;db.execute('INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)',(jid,p1,'report','pending','queued',time.time()))
        db.execute("UPDATE jobs SET status='succeeded',finished=?,result='{}' WHERE id=?",(time.time(),jid))
    r=owner.get('/api/admin/analytics/report');assert r.status_code==200,r.text;d=r.json()
    assert d['summary']['practices']==3 and d['summary']['reports']==3 and d['summary']['completed']==2
    assert d['questions'][0]['saved']==2 and d['questions'][2]['saved']==1
    assert d['no_questions']=={'base':1,'reports':1}
    assert owner.get('/api/admin/analytics/practices?stage=report_generated').json()['total']==3
    s.execute("UPDATE jobs SET status='failed' WHERE id=?",(jid,))
    assert owner.get('/api/admin/analytics/report').json()['summary']['reports']==3


def test_atomic_events_rollback_and_idempotent_backfill(setup):
    app,*_=setup;s=app.state.store
    before=s.one('SELECT COUNT(*) n FROM analytics_events')['n']
    try:
        with s.connect() as db:
            db.execute("INSERT INTO practices(id,user_id,config,created) VALUES('rollback','not-existing','{}',1)")
            raise RuntimeError()
    except RuntimeError:pass
    assert s.one("SELECT 1 FROM analytics_events WHERE practice_id='rollback'")==None
    Store(s.directory)
    assert s.one('SELECT COUNT(*) n FROM analytics_events')['n']==before


def test_anonymous_utm_binding_and_duplicate_delivery(setup):
    app,*_=setup;c=TestClient(app);eid=uuid.uuid4().hex
    body={'touch':{'source':'yandex','medium':'cpc','campaign_id':'campaign1'},'events':[{'id':eid,'kind':'registration_viewed','data':{}}]}
    r=c.post('/api/analytics/events',json=body);assert r.status_code==200,r.text
    assert r.json()['accepted']==[eid]
    assert c.post('/api/analytics/events',json=body).json()['duplicates']==[eid]
    reg=c.post('/api/auth/register',json={'name':'Synthetic','email':'touch@example.test','password':'TestPassword2026'});uid=reg.json()['user']['id']
    touch=app.state.store.one('SELECT t.* FROM account_attribution a JOIN acquisition_touches t ON t.id=a.touch_id WHERE a.account_id=?',(uid,))
    assert touch['source']=='yandex' and touch['campaign_id']=='campaign1'
    assert app.state.store.one('SELECT actor_id FROM analytics_events WHERE event_id=?',(eid,))['actor_id']==uid


@pytest.mark.parametrize('kind,data',[('segment_saved',{}),('capture_started',{'transcript':'secret speech'}),('page_viewed',{'email':'private@example.test'})])
def test_forged_and_sensitive_events_rejected(setup,kind,data):
    app,owner,*_=setup;eid=uuid.uuid4().hex
    r=owner.post('/api/analytics/events',json={'events':[{'id':eid,'kind':kind,'data':data}]})
    assert r.status_code==200 and eid in r.json()['rejected']
    assert app.state.store.one('SELECT 1 FROM analytics_events WHERE event_id=?',(eid,)) is None


def test_private_media_and_audit(setup):
    app,owner,other,oid,uid,h,oh=setup;p,sid=fixture_practice(app.state.store,uid)
    url=f'/api/admin/evidence/{p}/segments/{sid}/media'
    assert other.get(url).status_code==403
    assert owner.get(f'/api/practices/{p}/segments/{sid}/media').status_code==404
    r=owner.get(url);assert r.status_code==200 and r.content==b'fixture-media'
    assert app.state.store.one("SELECT 1 FROM analytics_events WHERE kind='admin_media_view' AND actor_id=?",(oid,))
    detail=owner.get('/api/admin/analytics/practices/'+p).json();assert len(detail['versions'])==1 and detail['segments'][0]['available']


def test_get_does_not_become_visible_report(setup):
    app,owner,other,oid,uid,h,oh=setup;p,_=fixture_practice(app.state.store,uid)
    for _ in range(3):other.get('/api/practices/'+p)
    assert next(x for x in owner.get('/api/admin/analytics/report').json()['funnel'] if x['id']=='report_viewed')['count']==0
    jid=app.state.store.one("SELECT id FROM jobs WHERE practice_id=? AND kind='report'",(p,))['id']
    response=other.post('/api/analytics/events',json={'events':[{'id':uuid.uuid4().hex,'kind':'report_viewed','practice_id':p,'data':{'report_version_id':jid}}]})
    assert len(response.json()['accepted'])==1
    assert next(x for x in owner.get('/api/admin/analytics/report').json()['funnel'] if x['id']=='report_viewed')['count']==1


def csv_bytes(spend='10',currency='RUB'):
    return ('date,platform,account_id,campaign_id,campaign_name,creative_id,impressions,clicks,spend,currency,source_timezone,tax_mode\n'+datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()+f',yandex,a,c1,Campaign,,100,5,{spend},{currency},Europe/Moscow,included\n').encode()


def test_import_preview_confirm_replay_revision_rollback(setup):
    app,owner,other,oid,uid,h,oh=setup
    def load(spend):
        r=owner.post('/api/admin/marketing/imports',headers=h,content=csv_bytes(spend));assert r.status_code==200,r.text
        return r.json()['id']
    b1=load('10');assert load('10')==b1
    assert owner.get('/api/admin/analytics/report').json()['marketing']['budget_available'] is False
    assert owner.post(f'/api/admin/marketing/imports/{b1}/confirm',headers=h).status_code==200
    assert owner.post(f'/api/admin/marketing/imports/{b1}/confirm',headers=h).json()['replay']
    b2=load('20');owner.post(f'/api/admin/marketing/imports/{b2}/confirm',headers=h)
    assert owner.get('/api/admin/analytics/report').json()['marketing']['items'][0]['spend']==20
    owner.post(f'/api/admin/marketing/imports/{b2}/rollback',headers=h)
    assert owner.get('/api/admin/analytics/report').json()['marketing']['items'][0]['spend']==10
    assert other.post('/api/admin/marketing/imports',headers=oh,content=csv_bytes('30')).status_code==403
    assert owner.post('/api/admin/marketing/imports',content=csv_bytes()).status_code==403


@pytest.mark.parametrize('value',['-1','NaN','Infinity','1e100'])
def test_bad_money_rejected(setup,value):
    app,owner,other,oid,uid,h,oh=setup
    assert owner.post('/api/admin/marketing/imports',headers=h,content=csv_bytes(value)).status_code==422


def test_snapshot_consistent_export_hash_and_content_privacy(setup):
    app,owner,other,oid,uid,h,oh=setup;p,_=fixture_practice(app.state.store,uid)
    r=owner.post('/api/admin/analytics/snapshots',headers=h,json={'filters':{}});assert r.status_code==200,r.text;sid=r.json()['id']
    data=owner.get('/api/admin/analytics/snapshots/'+sid).json();assert data['summary']['practices']==len(data['practices'])==1
    archive=zipfile.ZipFile(io.BytesIO(owner.get('/api/admin/analytics/snapshots/'+sid+'?format=zip').content));manifest=json.loads(archive.read('manifest.json'))
    for name,checksum in manifest['files'].items():assert hashlib.sha256(archive.read(name)).hexdigest()==checksum
    assert 'owner@example.test' not in archive.read('analytics.json').decode() and 'Synthetic source' not in archive.read('analytics.json').decode()
    assert other.get('/api/admin/analytics/snapshots/'+sid).status_code==403


def test_classification_exclusion_and_csrf(setup):
    app,owner,other,oid,uid,h,oh=setup;fixture_practice(app.state.store,uid)
    assert owner.patch('/api/admin/analytics/account-classifications/'+uid,json={'classification':'test'}).status_code==403
    assert owner.patch('/api/admin/analytics/account-classifications/'+uid,headers=h,json={'classification':'test'}).status_code==200
    assert owner.get('/api/admin/analytics/report').json()['summary']['practices']==0
    assert owner.get('/api/admin/analytics/report?include_staff=true').json()['summary']['practices']==1


def test_delete_revokes_snapshot_and_erases_trace(setup):
    app,owner,other,oid,uid,h,oh=setup;p,sid=fixture_practice(app.state.store,uid)
    snap=owner.post('/api/admin/analytics/snapshots',headers=h,json={'filters':{}}).json()['id']
    assert other.delete('/api/practices/'+p,headers=oh).status_code==200
    assert owner.get('/api/admin/analytics/snapshots/'+snap).status_code==404
    assert app.state.store.one('SELECT 1 FROM analytics_events WHERE practice_id=?',(p,)) is None
    assert app.state.store.one('SELECT COUNT(*) n FROM analytics_deleted_facts')['n']==1
    assert owner.get(f'/api/admin/evidence/{p}/segments/{sid}/media').status_code==404


def test_rollup_and_retention_without_old_usage(setup):
    from server.analytics_archive import rollup,prune
    app,owner,other,oid,uid,h,oh=setup;fixture_practice(app.state.store,uid)
    rollup(app.state.store)
    assert app.state.store.one('SELECT 1 FROM analytics_rollups')
    app.state.store.execute('UPDATE analytics_events SET received=?',(time.time()-181*86400,))
    with app.state.store.connect() as db:prune(db)
    assert app.state.store.one('SELECT COUNT(*) n FROM analytics_events')['n']==0
    assert app.state.store.one('SELECT 1 FROM analytics_rollups')


def test_native_sql_rollback_compatibility(setup):
    import sqlite3
    app,*_=setup
    # Previous release connections do not register analytics UDFs.
    with sqlite3.connect(app.state.store.path) as db:
        db.execute('INSERT INTO practices(id,user_id,config,created) VALUES(?,?,?,?)',('old-release-fixture','synthetic','{}',time.time()))
    assert app.state.store.one("SELECT 1 FROM analytics_events WHERE event_id='practice:old-release-fixture'")


def test_ten_parallel_saves_and_replays(setup):
    import asyncio
    import httpx
    from tests_support_analytics import synthetic_wav
    app,owner,other,oid,uid,h,oh=setup
    async def run():
        async def save(n):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                response=await client.post('/api/auth/register',json={'email':f'parallel-{n}@example.test','name':'Fixture','password':'SyntheticPassword2026'})
                assert response.status_code==200,response.text
                headers={'X-CSRF-Token':response.json()['csrf_token']}
                p=(await client.post('/api/practices',headers=headers,json={'scenario':'speech','duration':1,'questions':False})).json()['id']
                args={'headers':headers,'data':{'kind':'speech','index':'0','client_key':uuid.uuid4().hex},'files':{'file':('sample.wav',synthetic_wav(),'audio/wav')}}
                first=await client.post('/api/practices/'+p+'/segments',**args)
                again=await client.post('/api/practices/'+p+'/segments',**args)
                assert first.status_code==again.status_code==200,(first.text,again.text)
                assert first.json()['id']==again.json()['id']
        await asyncio.gather(*(save(n) for n in range(10)))
    asyncio.run(run())
    assert owner.get('/api/admin/analytics/report').json()['summary']['speeches']==10
    assert app.state.store.one("SELECT COUNT(*) n FROM analytics_events WHERE kind='segment_saved'")['n']==10


def test_cross_origin_owner_read_denied(setup):
    app,owner,*_=setup
    assert owner.get('/api/admin/analytics/report',headers={'Origin':'https://another.invalid'}).status_code==403
    assert owner.get('/api/admin/analytics/report',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403


def test_first_and_registration_touch_are_separate(setup):
    app,owner,*_=setup;c=TestClient(app)
    def page(source):
        r=c.post('/api/analytics/events',json={'touch':{'source':source,'medium':'cpc','campaign_id':source+'-campaign'},'events':[{'id':uuid.uuid4().hex,'kind':'page_viewed','data':{'route_id':'/register'}}]})
        assert r.status_code==200
    page('yandex')
    app.state.store.execute('UPDATE analytics_sessions SET last_activity=?',(time.time()-2000,))
    page('vk')
    r=c.post('/api/auth/register',json={'email':'attribution@example.test','name':'Fixture','password':'SyntheticPassword2026'});assert r.status_code==200
    last=owner.get('/api/admin/analytics/report?source=vk').json()
    first=owner.get('/api/admin/analytics/report?source=yandex&source_model=first').json()
    assert last['summary']['registrations']==first['summary']['registrations']==1
    assert first['attribution_version']=='first-observed-touch-v1'
    assert owner.get('/api/admin/analytics/report?source=yandex').json()['summary']['registrations']==0


def test_question_indices_and_observed_drilldown_are_exact(setup):
    app,owner,_,_,uid,*_=setup;s=app.state.store
    pid,sid=fixture_practice(s,uid,True,answers=1)
    s.execute('UPDATE segments SET segment_index=3 WHERE practice_id=? AND kind=?',(pid,'answer'))
    d=owner.get('/api/admin/analytics/report').json()
    assert [q['saved'] for q in d['questions']]==[0,0,1]
    assert owner.get('/api/admin/analytics/practices?stage=report_engaged').json()['total']==0
    from server.analytics_events import record
    with s.connect() as db:record(db,'report_engaged',uid,pid,origin='client_observed')
    assert owner.get('/api/admin/analytics/practices?stage=report_engaged').json()['total']==1
    assert owner.get('/api/admin/analytics/report?from=2026-10-13T00:10:00').status_code==422


def test_detailed_funnel_memberships_timings_and_evidence(setup):
    from server.analytics_events import record
    app,owner,_,_,uid,*_=setup;s=app.state.store
    p1,sid=fixture_practice(s,uid,True);p2,_=fixture_practice(s,uid,True,report=False,answers=1)
    with s.connect() as db:
        for kind in ('question_presented','answer_started','answer_recorded'):
            record(db,kind,uid,p1,{'question_index':1},origin='client_observed')
        record(db,'capture_started',uid,p1,{'segment_index':0},origin='client_observed')
    d=owner.get('/api/admin/analytics/report').json()
    assert d['questions'][0]['presented']==d['questions'][0]['started']==d['questions'][0]['recorded']==1
    assert d['questions'][0]['saved']==2 and d['questions'][1]['saved']==1
    assert d['unfinished']['awaiting_questions']==1
    assert d['timings']['report_ready']['p50_seconds']==7
    for step in d['funnel']:
        listing=owner.get('/api/admin/analytics/practices',params={'stage':step['id']}).json()
        assert listing['total']==step['count'],step
    detail=owner.get('/api/admin/analytics/practices/'+p1).json()
    speech=next(v for v in detail['segments'] if v['id']==sid)
    assert speech['stored_sha256']==hashlib.sha256(b'fixture-media').hexdigest()
    assert speech['upload_sha256'] is None and speech['bytes']==13


def test_acquisition_branches_and_creative_reconciliation(setup):
    app,owner,_,oid,uid,h,*_=setup;visitor=TestClient(app)
    events=[{'id':uuid.uuid4().hex,'kind':kind,'data':data} for kind,data in [
        ('page_viewed',{'route_id':'/landing'}),('landing_cta_clicked',{'cta_id':'landing'}),
        ('registration_viewed',{}),('registration_submitted',{}),('registration_failed',{'error_code':'INVITE_REQUIRED'})]]
    assert visitor.post('/api/analytics/events',json={'events':events}).status_code==200
    d=owner.get('/api/admin/analytics/report').json()['acquisition']
    assert d['landing_visits']==d['cta_visits']==d['form_visits']==d['submitted_visits']==1
    assert d['direct_form_visits']==0 and d['registration_errors']=={'INVITE_REQUIRED':1}
    text=csv_bytes().decode();head,line=text.strip().split('\n')
    first=line.replace('Campaign,,','Campaign,creative1,')
    second=line.replace('Campaign,,','Campaign,creative2,').replace(',100,5,10,',',200,10,20,')
    bid=owner.post('/api/admin/marketing/imports',headers=h,content=(head+'\n'+first+'\n'+second+'\n').encode()).json()['id']
    assert owner.post('/api/admin/marketing/imports/'+bid+'/confirm',headers=h).status_code==200
    m=owner.get('/api/admin/analytics/report').json()['marketing']
    assert len(m['creative_items'])==2
    assert sum(c['spend'] for c in m['creative_items'])==m['items'][0]['spend']==30
    assert sum(c['impressions'] for c in m['creative_items'])==300


def test_optional_analytics_flags_do_not_block_product(setup,monkeypatch):
    app,owner,_,oid,uid,h,*_=setup
    monkeypatch.setenv('ANALYTICS_CLIENT_ENABLED','0')
    assert owner.post('/api/analytics/events',json={'events':[]}).json()['disabled'] is True
    monkeypatch.setenv('ANALYTICS_EXPORT_ENABLED','0')
    assert owner.get('/api/admin/analytics/events?format=csv').status_code==503
    assert owner.get('/api/admin/analytics/events?format=ndjson').status_code==503
    assert owner.get('/api/admin/analytics/report').status_code==200
    monkeypatch.setenv('ANALYTICS_ADMIN_ENABLED','0')
    assert owner.get('/api/admin/analytics/report').status_code==403
    assert owner.get('/api/auth/me').json()['user']['analytics_access'] is False
    assert owner.post('/api/practices',headers=h,json={'scenario':'speech','duration':1,'questions':False}).status_code==200


def test_named_filter_choices_are_private_and_come_from_observed_data(setup):
    app,owner,other,*_=setup;visitor=TestClient(app)
    payload={'touch':{'source':'vk','medium':'cpc','campaign_id':'campaign-a','campaign':'Campaign A'},'events':[{'id':uuid.uuid4().hex,'kind':'page_viewed','data':{'route_id':'/landing'}}]}
    assert visitor.post('/api/analytics/events',json=payload).status_code==200
    result=owner.get('/api/admin/analytics/report').json()['filter_options']
    assert 'vk' in result['sources'] and 'unknown' in result['sources']
    assert {'id':'campaign-a','name':'Campaign A'} in result['campaigns']
    assert 'owner@example.test' not in json.dumps(result)
    assert other.get('/api/admin/analytics/report').status_code==403


def test_compact_overview_averages_activity_and_returns(setup):
    app,owner,other,oid,uid,h,oh=setup;s=app.state.store
    # Four accounts, two have recordings; an unused setup is not a training.
    with s.connect() as db:
        for n in (1,2):
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(f'{n:032x}',f'compact-{n}@example.test','Synthetic','unused','student',0,0,time.time()-20*86400))
    fixture_practice(s,uid,days=10)
    p,_=fixture_practice(s,uid,days=0)
    fixture_practice(s,oid,days=10)
    s.execute('INSERT INTO practices(id,user_id,config,created) VALUES(?,?,?,?)',(uuid.uuid4().hex,uid,'{}',time.time()-60))
    # Multiple recordings of one person still mean one active person.
    s.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,p,'answer',1,'unused.wav',20,'Synthetic',time.time()-1))
    o=owner.get('/api/admin/analytics/report').json()['overview']
    assert o['accounts']==4 and o['started_practices']==3
    assert o['average_per_user']==.75 and o['average_per_trainee']==1.5
    assert o['last_hour']==1 and o['dau']==1
    assert o['retention_7d']=={'numerator':1,'denominator':2,'value':50}
    assert o['churn_7d']=={'numerator':1,'denominator':2,'value':50}
    assert sum(d['registered'] for d in o['daily'])==4
    assert o['daily'][-1]['active']==1
    accounts=owner.get('/api/admin/analytics/accounts?kind=all').json()
    assert accounts['total']==4 and sum(a['practices'] for a in accounts['items'])==3
    assert all(a['ip_masked'] is None and a['last_name'] is None for a in accounts['items'])


def test_compact_costs_include_retries_live_chunks_and_unknown_outcomes(setup):
    from server import limits
    app,owner,other,oid,uid,h,oh=setup;s=app.state.store
    p,_=fixture_practice(s,uid,days=1)
    jid=s.one('SELECT id FROM jobs WHERE practice_id=?',(p,))['id']
    chunk=uuid.uuid4().hex
    s.execute('INSERT INTO live_chunks(id,practice_id,session_id,chunk_index,offset_seconds,duration,filename,sha256,status,created) VALUES(?,?,?,?,?,?,?,?,?,?)',
              (chunk,p,uuid.uuid4().hex,0,0,5,'fixture.wav','abc','succeeded',time.time()))
    with limits.provider_scope(s,uid,jid):
        first=limits.reserve_attempt('report');limits.finish_attempt(first,503,20,.2)
        retry=limits.reserve_attempt('report');limits.finish_attempt(retry,200,20,.3)
    with limits.provider_scope(s,uid,chunk):
        audio=limits.reserve_attempt('transcription',5);limits.finish_attempt(audio,200,20,0)
    o=owner.get('/api/admin/analytics/report').json()['overview']['economy']
    assert o['attempts']==o['priced_attempts']==3 and o['total']==.5
    assert o['per_practice']==.5 and o['per_user']==.5
    # Quota expiry must not lose cost provenance.
    s.execute('DELETE FROM ai_attempts')
    assert owner.get('/api/admin/analytics/report').json()['overview']['economy']['total']==.5
    with limits.provider_scope(s,uid,jid):
        limits.reserve_attempt('report')  # Simulated process death / unknown outcome.
    o=owner.get('/api/admin/analytics/report').json()['overview']['economy']
    assert o['total'] is None and o['known_total']==.5 and o['attempts']==4
    row=owner.get('/api/admin/analytics/practices').json()['items'][0]
    assert row['cost']['total'] is None and row['cost']['priced_attempts']==3


def test_compact_export_access_scope_identity_and_csv_safety(setup):
    app,owner,other,oid,uid,h,oh=setup;s=app.state.store
    fixture_practice(s,uid)
    s.execute('UPDATE users SET name=? WHERE id=?',('=FORMULA()',uid))
    for dataset in ('accounts','practices','summary','daily','funnel'):
        url=f'/api/admin/analytics/export?dataset={dataset}&format=json'
        assert other.get(url).status_code==403
        assert TestClient(app).get(url).status_code==401
        r=owner.get(url);assert r.status_code==200,r.text
        assert r.json()['metadata']['cost_currency'] is None
    text=owner.get('/api/admin/analytics/export?dataset=accounts&format=csv').text
    assert "'=FORMULA()" in text and 'password' not in text and 'owner@example.test' in text
    archive=zipfile.ZipFile(io.BytesIO(owner.get('/api/admin/analytics/export?dataset=all&format=zip').content))
    assert set(archive.namelist())=={'summary.csv','accounts.csv','practices.csv','daily.csv','funnel.csv','metadata.json'}
    daily=owner.get('/api/admin/analytics/export?dataset=daily&format=json').json()['rows']
    assert daily==owner.get('/api/admin/analytics/report').json()['overview']['daily']
    snapshot=owner.post('/api/admin/analytics/snapshots',headers=h,json={}).json()['id']
    raw=owner.get('/api/admin/analytics/snapshots/'+snapshot).text
    assert '=FORMULA()' not in raw and 'owner@example.test' not in raw


def test_compact_funnel_keeps_question_branch_and_order(setup):
    app,owner,other,oid,uid,h,oh=setup;s=app.state.store
    fixture_practice(s,uid,questions=False)
    fixture_practice(s,uid,questions=True)
    p,_=fixture_practice(s,uid,questions=True,report=False,answers=0)
    # Out-of-order legacy answer cannot claim conversion through question one.
    s.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,p,'answer',2,'fixture.wav',10,'Synthetic',time.time()))
    rows=owner.get('/api/admin/analytics/report').json()['overview']['training_funnel']
    assert [r['count'] for r in rows[:6]]==[3,3,1,1,1,2]
    assert rows[2]['conversion']=={'numerator':1,'denominator':2,'value':50}
    assert rows[5]['conversion']=={'numerator':2,'denominator':2,'value':100}


def test_compact_acquisition_binds_login_to_the_observed_visit(setup):
    app,owner,other,oid,uid,h,oh=setup
    client=TestClient(app)
    landing={'id':uuid.uuid4().hex,'kind':'page_viewed','data':{'route_id':'/landing'}}
    assert client.post('/api/analytics/events',json={'events':[landing]}).status_code==200
    assert client.post('/api/auth/login',json={'email':'owner@example.test','password':'TestPassword2026'}).status_code==200
    funnel=owner.get('/api/admin/analytics/report').json()['overview']['acquisition_funnel']
    assert [r['count'] for r in funnel]==[1,1,0]
    pid,_=fixture_practice(app.state.store,oid,days=0,report=False)
    event={'id':uuid.uuid4().hex,'kind':'capture_started','practice_id':pid,'data':{'segment_index':0}}
    assert client.post('/api/analytics/events',json={'events':[event]}).status_code==200
    funnel=owner.get('/api/admin/analytics/report').json()['overview']['acquisition_funnel']
    assert [r['count'] for r in funnel]==[1,1,1]
    login=app.state.store.one("SELECT session_id FROM analytics_events WHERE kind='login' AND actor_id=?",(oid,))
    assert login['session_id']
