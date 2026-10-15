"""Opt-in real Docker acceptance with disposable data and no external AI calls.

Build current/previous images as described in docs/operations.md, then run this
file with Python 3.12. It only manages uniquely named, root-labelled fixtures.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import secrets
import sys
import tempfile
import subprocess
import tarfile
import os
from unittest.mock import patch
from http.cookies import SimpleCookie
import wave

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from scripts.production import Production, atomic_json, docker, http_json, private_json, RESTIC_IMAGE
from server.store import Store


def wav_bytes():
    raw = io.BytesIO()
    with wave.open(raw, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\x00\x01' * 16000)
    return raw.getvalue()


def desktop_restic(arguments, **kwargs):
    """Exercise Linux Restic on Linux storage: macOS bind reads fail in Go here.

    Only disposable acceptance snapshots use this bridge. Production runs on a
    Linux host and uses its normal bind mounts without this test adapter.
    """
    source_mount = next((value for value in arguments if value.startswith('type=bind,source=') and ',target=/snapshot,readonly' in value), None)
    if sys.platform != 'darwin' or RESTIC_IMAGE not in arguments or not source_mount:
        return docker(arguments, **kwargs)
    source = Path(source_mount.split('source=', 1)[1].split(',target=', 1)[0])
    volume = 'nfs-qa-restic-' + secrets.token_hex(5)
    docker(['volume', 'create', volume])
    try:
        with tempfile.TemporaryFile() as archive:
            with tarfile.open(fileobj=archive, mode='w') as output:
                output.add(source, arcname='.')
            archive.seek(0)
            copied = subprocess.run(['docker','run','--rm','-i','--entrypoint','sh','--mount',f'type=volume,source={volume},target=/snapshot',RESTIC_IMAGE,'-c',f'tar -xf - -C /snapshot && chown -R {os.getuid()}:{os.getgid()} /snapshot'],stdin=archive,capture_output=True)
            if copied.returncode:
                raise RuntimeError('Disposable Linux snapshot staging failed')
        translated = [f'type=volume,source={volume},target=/snapshot,readonly' if value == source_mount else value for value in arguments]
        return docker(translated, **kwargs)
    finally:
        docker(['volume','rm',volume], optional=True)


def run(previous_image, current_image, faulty_image, port):
    checks = {}
    names = []
    networks = []
    with tempfile.TemporaryDirectory(prefix='nfs-ops-acceptance-') as temporary:
        root = Path(temporary) / 'deployment'
        name = 'nfs-qa-' + secrets.token_hex(5)
        manager = Production(root, name, port, wait_seconds=15)
        names.append(name)
        networks.append(name+'-private')
        try:
            with manager.locked():
                manager.bootstrap()
                config = private_json(root/'runtime.json')
                config['AI_ENABLED']='0'  # Real provider traffic is forbidden in this acceptance.
                atomic_json(root/'runtime.json',config)
                credentials = private_json(root/'secrets.json')
                credentials['LLM_API_KEY']='synthetic-local-fixture-key'
                atomic_json(root/'secrets.json',credentials)
                manager.release(previous_image)
                current = manager.state()['current']
                record = manager.container()
                assert record['HostConfig']['ReadonlyRootfs'] is True
                assert record['HostConfig']['Memory'] == 1073741824
                assert 'ALL' in record['HostConfig']['CapDrop']
                assert record['Config']['User'].split(':')[0] != '0'
                assert all(binding['HostIp']=='127.0.0.1' for bindings in record['NetworkSettings']['Ports'].values() if bindings for binding in bindings)
                checks['hardened_container']=True
                client=httpx.Client(base_url=manager.url,timeout=15)
                result=client.post('/api/auth/register',json={'email':'ops-fixture@example.test','name':'Operational fixture','password':'SyntheticOpsPassword123','role':'other','consent':True})
                assert result.status_code==200
                cookies=SimpleCookie(result.headers['set-cookie'])
                headers={'Cookie':'nfs_session='+cookies['nfs_session'].value,'X-CSRF-Token':result.json()['csrf_token']}
                user_id=result.json()['user']['id']
                def create_recording(key):
                    response=client.post('/api/practices',headers=headers,json={'scenario':'speech','topic':'Synthetic operational acceptance','duration':1,'questions':False,'criteria':''})
                    assert response.status_code==200
                    practice=response.json()['id']
                    saved=client.post(f'/api/practices/{practice}/segments',headers=headers,data={'kind':'speech','index':'0','client_key':key},files={'file':('fixture.wav',wav_bytes(),'audio/wav')})
                    assert saved.status_code==200
                    return practice,saved.json()['media_url']
                first,first_media=create_recording('a'*32)
                # Active SQLite access must stay in the container's kernel/VFS (also on Docker Desktop).
                reservation="import os; from server.store import Store; from server.limits import provider_scope,reserve_attempt; s=Store(os.environ['DATA_DIR']); os.environ['AI_ENABLED']='1'; "
                reservation += "exec(\"with provider_scope(s," + repr(user_id) + ", 'local-reservation-fixture'):\\n reserve_attempt('fixture',input_chars=10,output_tokens=10)\")"
                docker(['exec',name,'python','-c',reservation])
                manager.set_ai(False)
                before_hash=hashlib.sha256(client.get(first_media,headers=headers).content).hexdigest()
                def assert_data(practices):
                    response=client.get('/api/practices',headers=headers)
                    if response.status_code!=200:
                        raise AssertionError('Business API not active: '+str(response.status_code)+' '+response.json().get('error',{}).get('code','unknown'))
                    assert response.json()['total']==practices
                    assert hashlib.sha256(client.get(first_media,headers=headers).content).hexdigest()==before_hash
                    count=docker(['exec',name,'python','-c',"import os;from server.store import Store;s=Store(os.environ['DATA_DIR']);print(s.one('SELECT COUNT(*) AS n FROM ai_attempts')['n'])"])
                    assert count=='1'
                    pause=docker(['exec',name,'python','-c',"import os;from server.store import Store;s=Store(os.environ['DATA_DIR']);print(s.one(\"SELECT value FROM operational_state WHERE key='ai_enabled'\")['value'])"])
                    assert pause=='false'
                original_wait=manager.wait_ready
                def maintenance_gate(release):
                    original_wait(release)
                    assert client.get('/api/auth/me').status_code==503
                    assert client.post('/api/practices',headers=headers,json={}).status_code==503
                manager.wait_ready=maintenance_gate
                manager.release(current_image)
                manager.wait_ready=original_wait
                assert_data(1)
                second,_=create_recording('b'*32)
                manager.release(rollback=True)
                assert_data(2)  # Code rollback must preserve post-deployment user writes.
                checks['deploy_and_code_rollback_preserve_recordings_and_budget']=True
                checks['operator_pause_survives_release_and_rollback']=True
                manager.wait_seconds=3
                try:
                    manager.release(faulty_image)
                    raise AssertionError('Faulty release unexpectedly activated')
                except RuntimeError as error:
                    assert 'previous release and verified data recovered' in str(error)
                assert_data(2)
                assert http_json(manager.url+'/api/readiness')['maintenance'] is False
                checks['failed_candidate_automatically_restored_previous_release']=True
                manager.wait_seconds=15
                manager.restic(['init'])
                with patch('scripts.production.docker', side_effect=desktop_restic):
                    result=manager.scheduled_backup()
                assert result['encrypted_restore_verified']
                assert_data(2)
                checks['encrypted_backup_full_check_and_restore']=True
                status=http_json(manager.url+'/api/operator/status',credentials['OPERATOR_TOKEN'])
                assert status['backup']['encrypted_at'] and status['workers']['ready']
                assert status['backup']['offsite_configured'] is False
                checks['local_repository_does_not_claim_offsite']=True
                duplicate=Production(root,name+'-duplicate',port+1,wait_seconds=3)
                names.append(duplicate.name)
                networks.append(duplicate.name+'-private')
                duplicate.start(manager.state()['current'])
                try:
                    duplicate.wait_ready(manager.state()['current'])
                    raise AssertionError('Second application acquired the same data')
                except RuntimeError:
                    pass
                assert http_json(manager.url+'/api/readiness')['ok']
                checks['second_instance_rejected']=True
                duplicate.stop()
                docker(['rm',duplicate.name],optional=True)
                # Simulate a controller interruption after maintenance/stopping the service.
                manager.set_maintenance()
                manager.stop()
                manager.resume()
                assert_data(2)
                checks['interrupted_operation_resume_preserves_data']=True
                dr=Production(Path(temporary)/'disaster-recovery',name+'-dr',port+2)
                dr.bootstrap()
                atomic_json(dr.root/'runtime.json',config)
                atomic_json(dr.root/'secrets.json',{**credentials,'RESTIC_REPOSITORY':str(root/'encrypted-backups')})
                dr.restore_encrypted(result['snapshot_id'])
                assert Store(dr.data).one('SELECT COUNT(*) AS n FROM practices')['n']==2
                assert Store(dr.data).one('SELECT COUNT(*) AS n FROM ai_attempts')['n']==1
                checks['disaster_restore_to_new_root']=True
                client.close()
        finally:
            for container_name in names:
                docker(['stop','--time','15',container_name],optional=True)
                docker(['rm',container_name],optional=True)
            for network in networks:
                docker(['network','rm',network],optional=True)
    return checks


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-image',required=True)
    parser.add_argument('--current-image',required=True)
    parser.add_argument('--faulty-image',required=True)
    parser.add_argument('--port',type=int,default=19086)
    args=parser.parse_args()
    print(json.dumps(run(args.previous_image,args.current_image,args.faulty_image,args.port),indent=2))
