import json
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from server.analytics_view import configure, ACCESS, PREFIX, COOKIE, PASSWORDS
from tests.test_analytics import setup, fixture_practice

PASSWORD = 'SyntheticViewerPassword2026!'
HEADERS = {'Origin': 'http://testserver'}
PATH = '/api/analytics-view'


def login(client, password=PASSWORD, **kwargs):
    return client.post(PATH+'/session', json={'password': password}, headers=HEADERS, **kwargs)


def test_viewer_has_full_read_access_without_owner_or_mutation_rights(setup):
    app, owner, _, _, user, *_ = setup; store=app.state.store
    pid,sid=fixture_practice(store, user); configure(store, PASSWORD)
    viewer=TestClient(app)
    for path in ['/report','/accounts','/practices','/practices/'+pid,'/export',f'/evidence/{pid}/segments/{sid}/media']:
        assert viewer.get(PATH+path).status_code==401
    assert login(viewer,'wrong-password').status_code==401
    response=login(viewer); assert response.status_code==200
    assert 'httponly' in response.headers['set-cookie'].lower()
    assert 'samesite=strict' in response.headers['set-cookie'].lower()
    assert 'Path=/api/analytics-view' in response.headers['set-cookie']
    result=viewer.get(PATH+'/report'); assert result.status_code==200
    assert result.headers['cache-control']=='no-store'
    assert result.headers['cross-origin-resource-policy']=='same-origin'
    expected=owner.get('/api/admin/analytics/report').json()['overview']
    assert result.json()['overview']['llm_tokens']==expected['llm_tokens']
    assert result.json()['overview']['accounts']==expected['accounts']
    for url in ['/api/admin/analytics/report','/api/admin/analytics/accounts','/api/admin/analytics/export',
                '/api/admin/analytics/practices','/api/practices']:
        assert viewer.get(url).status_code==401
    accounts=viewer.get(PATH+'/accounts?kind=all').json()
    assert any(row['email']=='other@example.test' and row['id']==user for row in accounts['items'])
    practices=viewer.get(PATH+'/practices').json()
    assert practices['items'][0]['id']==pid
    detail=viewer.get(PATH+'/practices/'+pid).json()
    assert detail['participant']['email']=='other@example.test' and detail['versions']
    segment=detail['segments'][0]
    assert segment['id']==sid and segment['transcript']=='Synthetic source'
    assert segment['media_url'].startswith(PATH+'/evidence/')
    media=viewer.get(segment['media_url']);assert media.status_code==200 and media.content==b'fixture-media'
    assert viewer.get(segment['media_url'],headers={'Range':'bytes=0-2'}).status_code==206
    assert viewer.get(PATH+f'/evidence/{pid}/segments/'+'0'*32+'/media').status_code==404
    exported=viewer.get(PATH+'/export?dataset=accounts&format=json')
    assert exported.status_code==200 and 'other@example.test' in exported.text
    assert 'password' not in exported.text and 'csrf' not in exported.text
    assert viewer.get(PATH+'/export?dataset=all&format=zip').status_code==200
    for method,path in [('post','/report'),('patch','/accounts/'+user),('delete','/practices/'+pid),('post','/export')]:
        assert getattr(viewer,method)(PATH+path,headers=HEADERS).status_code==401
    assert viewer.post('/api/admin/analytics/snapshots',json={},headers=HEADERS).status_code==401
    assert viewer.post('/api/practices',json={},headers=HEADERS).status_code==401
    assert viewer.patch('/api/admin/analytics/account-classifications/'+user,json={'classification':'staff'},headers=HEADERS).status_code==401
    assert viewer.get(PATH+'/report?actor_id='+user).status_code==200
    assert viewer.get(PATH+'/report?include_staff=true').status_code==200
    assert viewer.get(PATH+'/report?from=bad').status_code==422
    assert viewer.get('/api/auth/me').json()['user'] is None
    config=json.loads(store.one('SELECT value FROM operational_state WHERE key=?',(ACCESS,))['value'])
    assert PASSWORD not in json.dumps(config) and config['password_hash'].startswith('$argon2')
    assert PASSWORD not in json.dumps(store.all('SELECT data FROM events'))
    app.state.production=True
    secure=TestClient(app,base_url='https://testserver').post(PATH+'/session',json={'password':PASSWORD},headers={'Origin':'https://testserver'})
    assert secure.status_code==200 and '; Secure' in secure.headers['set-cookie']


def test_logout_expiry_rotation_and_disabling_revoke_sessions(setup):
    app,*_=setup; store=app.state.store; configure(store,PASSWORD); viewer=TestClient(app)
    assert login(viewer).status_code==200
    raw=viewer.cookies.get(COOKIE)
    assert viewer.delete(PATH+'/session',headers=HEADERS).status_code==200
    viewer.cookies.set(COOKIE,raw,path=PATH)
    assert viewer.get(PATH+'/report').status_code==401  # Copying a logged-out cookie cannot resume it.
    assert login(viewer).status_code==200
    with store.connect() as db:
        db.execute("UPDATE operational_state SET value=json_set(value,'$.expires',?) WHERE key LIKE ?",(time.time()-1,PREFIX+'%'))
    assert viewer.get(PATH+'/report').status_code==401
    assert login(viewer).status_code==200
    configure(store,'DifferentSyntheticPassword2026!')
    assert viewer.get(PATH+'/report').status_code==401
    assert login(viewer).status_code==401
    assert login(viewer,'DifferentSyntheticPassword2026!').status_code==200
    configure(store)
    assert viewer.get(PATH+'/session').json()=={'enabled':False,'authenticated':False}
    assert viewer.get(PATH+'/report').status_code==404 and login(viewer).status_code==404
    assert not store.one('SELECT 1 FROM operational_state WHERE key LIKE ?',(PREFIX+'%',))


def test_cross_origin_login_and_logout_are_rejected(setup):
    app,*_=setup; configure(app.state.store,PASSWORD); viewer=TestClient(app)
    for headers in ({},{'Origin':'https://hostile.test'},{'Origin':'http://testserver','Sec-Fetch-Site':'cross-site'}):
        assert viewer.post(PATH+'/session',json={'password':PASSWORD},headers=headers).status_code==403
    assert login(viewer).status_code==200
    assert viewer.delete(PATH+'/session',headers={'Origin':'https://hostile.test'}).status_code==403
    assert viewer.get(PATH+'/report').status_code==200
    assert viewer.get(PATH+'/report',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    assert viewer.post(PATH+'/session',content='x'*2048,headers=HEADERS).status_code==422


def test_password_guess_limit_and_no_account_bypass(setup):
    app,owner,other,*_=setup; configure(app.state.store,PASSWORD); viewer=TestClient(app)
    assert owner.get(PATH+'/report').status_code==401  # Account owner also enters the separate view password.
    assert other.get(PATH+'/report').status_code==401
    for _ in range(10):assert login(viewer,'incorrect').status_code==401
    assert login(viewer).status_code==429


def test_password_rotation_during_verification_does_not_issue_old_session(setup):
    app,*_=setup; store=app.state.store; configure(store,PASSWORD); viewer=TestClient(app)
    original=PASSWORDS.verify
    def verify(saved, password):
        result=original(saved,password);configure(store,'ReplacementSyntheticPassword2026!');return result
    with patch('server.analytics_view.PASSWORDS',SimpleNamespace(verify=verify,hash=PASSWORDS.hash)):
        assert login(viewer).status_code==401
    assert not store.one('SELECT 1 FROM operational_state WHERE key LIKE ?',(PREFIX+'%',))


def test_cli_uses_existing_store_without_migration_and_disable(setup):
    app,*_=setup; store=app.state.store
    command=[sys.executable,'-m','server.cli','--data-dir',str(store.directory),'analytics-view']
    before=store.one('SELECT COUNT(*) n FROM admin_memberships')['n']
    result=subprocess.run(command+['--password-stdin'],input=PASSWORD+'\n',text=True,capture_output=True)
    assert result.returncode==0 and PASSWORD not in result.stdout+result.stderr
    assert login(TestClient(app)).status_code==200
    result=subprocess.run(command+['--disable'],text=True,capture_output=True)
    assert result.returncode==0 and not store.one('SELECT 1 FROM operational_state WHERE key=?',(ACCESS,))
    assert store.one('SELECT COUNT(*) n FROM admin_memberships')['n']==before
