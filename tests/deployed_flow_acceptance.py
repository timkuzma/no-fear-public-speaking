"""Explicit real-provider acceptance against a deployed HTTPS origin.

prepare consumes {origin, speech, answers, state} JSON on stdin.
verify consumes {state} after a process restart. Fixture state contains secrets;
keep it mode 0600 outside Git, remove its account through the operator, and
remove the file afterwards. Never use a participant's account/audio here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import time

import httpx


def success(response, status=200):
    if response.status_code != status:
        try:
            code = response.json().get('error', {}).get('code', 'HTTP_ERROR')
        except ValueError:
            code = 'HTTP_ERROR'
        raise RuntimeError(f'Acceptance failed: HTTP {response.status_code} {code}')
    return response.json()


def poll(client, job):
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        result = success(client.get('/api/jobs/'+job['id']))
        if result['status'] == 'failed':
            raise RuntimeError('AI acceptance failed: '+result['error']['code'])
        if result['status'] == 'succeeded':
            return result
        time.sleep(1)
    raise RuntimeError('AI acceptance timeout; fixture recording remains saved')


def prepare(data):
    password=secrets.token_urlsafe(24)
    email='deployment-qa-'+secrets.token_hex(8)+'@example.invalid'
    with httpx.Client(base_url=data['origin'], timeout=30, headers={'Origin':data['origin']}) as client:
        response=client.post('/api/auth/register',json={'email':email,'password':password,'name':'Проверка развёртывания','role':'other','consent':True})
        registered=success(response)
        cookie_header=response.headers['set-cookie'].lower()
        assert 'secure' in cookie_header and 'httponly' in cookie_header and 'samesite=strict' in cookie_header
        state={'origin':data['origin'],'email':email,'password':password,'user_id':registered['user']['id']}
        fd=os.open(data['state'],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as output:json.dump(state,output)
        headers={'X-CSRF-Token':success(client.get('/api/auth/me'))['csrf_token']}
        practice=success(client.post('/api/practices',headers=headers,json={'scenario':'speech','topic':'Сервис подготовки к выступлениям','duration':3,'questions':True,'criteria':''}))['id']
        state['practice']=practice
        Path(data['state']).write_text(json.dumps(state))
        path=Path(data['speech'])
        uploaded=success(client.post(f'/api/practices/{practice}/segments',headers=headers,data={'kind':'speech','index':'0','client_key':secrets.token_hex(16)},files={'file':('speech.wav',path.read_bytes(),'audio/wav')}))
        played=client.get(uploaded['media_url']);assert played.status_code==200
        digest=hashlib.sha256(played.content).hexdigest()
        anonymous=httpx.get(data['origin']+uploaded['media_url'],timeout=15)
        assert anonymous.status_code in (401,404)
        questions=poll(client,success(client.post(f'/api/practices/{practice}/jobs',headers=headers,json={'kind':'questions'})))
        assert len(questions['result']['questions'])==3
        for index,answer in enumerate(data['answers'],1):
            success(client.post(f'/api/practices/{practice}/segments',headers=headers,data={'kind':'answer','index':str(index),'client_key':secrets.token_hex(16)},files={'file':('answer.wav',Path(answer).read_bytes(),'audio/wav')}))
        poll(client,success(client.post(f'/api/practices/{practice}/jobs',headers=headers,json={'kind':'report'})))
        detail=success(client.get('/api/practices/'+practice));assert detail['status']=='ready' and len(detail['segments'])==4
        success(client.post('/api/auth/logout',headers=headers))
        assert client.get('/api/practices/'+practice).status_code==401
        login=success(client.post('/api/auth/login',json={'email':email,'password':password}))
        detail=success(client.get('/api/practices/'+practice));assert detail['report'] and detail['status']=='ready'
        state={'origin':data['origin'],'email':email,'password':password,'cookie':client.cookies.get('nfs_session'),'user_id':login['user']['id'],'practice':practice,'media':uploaded['media_url'],'digest':digest}
        Path(data['state']).write_text(json.dumps(state))
    return {'https_signup_secure_session':True,'private_recording':True,'real_questions':3,'real_answers_saved':3,'real_report':True,'logout_and_relogin_preserve_practice':True}


def verify(data):
    state=json.loads(Path(data['state']).read_text())
    with httpx.Client(base_url=state['origin'],timeout=30,headers={'Origin':state['origin']}) as client:
        # A TLS proxy's health-check hysteresis can outlast direct app readiness.
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            try:
                ready=client.get('/api/readiness')
                if ready.status_code==200 and ready.json().get('ok') and not ready.json().get('maintenance'):
                    break
            except (httpx.HTTPError,ValueError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Public origin did not recover after restart')
        client.cookies.set('nfs_session',state['cookie'])
        detail=success(client.get('/api/practices/'+state['practice']))
        assert detail['status']=='ready' and len(detail['segments'])==4 and detail['report']
        played=client.get(state['media']);assert played.status_code==200 and hashlib.sha256(played.content).hexdigest()==state['digest']
        headers={'X-CSRF-Token':success(client.get('/api/auth/me'))['csrf_token']}
        success(client.delete('/api/practices/'+state['practice'],headers=headers))
        assert client.get(state['media']).status_code==404
        success(client.post('/api/auth/logout',headers=headers))
    return {'session_and_report_survive_restart':True,'recording_bytes_survive_restart':True,'fixture_practice_deleted':True}


if __name__=='__main__':
    import sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','verify'])
    args=parser.parse_args()
    try:
        print(json.dumps((prepare if args.action=='prepare' else verify)(json.load(sys.stdin))))
    except (RuntimeError,AssertionError,httpx.HTTPError):
        print('Deployment acceptance failed; inspect fixture state and safe job error codes',file=sys.stderr)
        raise SystemExit(1)
