"""Operational safety failures, notification retry and retention boundaries."""
from unittest.mock import patch
import pytest
from scripts import monitor
from scripts.production import Production, atomic_json, docker, private_json
from scripts.backup import backup, verify
from server.store import Store


def test_private_configuration_and_external_probe_do_not_leak_credentials(tmp_path, capsys):
    atomic_json(tmp_path/'secrets.json', {'OPERATOR_TOKEN':'synthetic-secret', 'ALERT_WEBHOOK_URL':'https://notify.test/private'})
    with patch.object(monitor, 'http_json', side_effect=OSError('synthetic-private-detail')) as get, patch.object(monitor, 'notify', side_effect=OSError('synthetic-private-detail')):
        for _ in range(3):
            monitor.check(tmp_path, 'https://public.test', public_only=True)
        assert get.call_args.args == ('https://public.test/api/readiness',)
        assert not get.call_args.kwargs
    saved = private_json(tmp_path/'monitor-state.json')
    assert saved['active'] == ['SERVICE_UNREACHABLE']
    assert len(saved['pending_notifications']) == 1
    messages=[]
    with patch.object(monitor, 'http_json', return_value={'ok':True,'maintenance':False}), patch.object(monitor, 'notify', side_effect=lambda url,change: messages.append(change)):
        assert monitor.check(tmp_path,'https://public.test',public_only=True)==0
    assert messages==[{'opened':['SERVICE_UNREACHABLE'],'resolved':[]},{'opened':[],'resolved':['SERVICE_UNREACHABLE']}]
    output=capsys.readouterr().out
    assert 'synthetic-secret' not in output and 'synthetic-private-detail' not in output and '/private' not in output
    assert not private_json(tmp_path/'monitor-state.json')['pending_notifications']
    (tmp_path/'secrets.json').chmod(0o644)
    with pytest.raises(RuntimeError,match='private'):
        private_json(tmp_path/'secrets.json')


def test_notifications_are_bounded_to_timer_deadline(tmp_path):
    atomic_json(tmp_path/'secrets.json',{'ALERT_WEBHOOK_URL':'https://notify.test'})
    backlog=[{'opened':[f'CODE_{i}'],'resolved':[]} for i in range(10)]
    atomic_json(tmp_path/'monitor-state.json',{'counts':{},'active':[],'pending_notifications':backlog})
    with patch.object(monitor,'http_json',return_value={'ok':True}), patch.object(monitor,'notify') as notify:
        monitor.check(tmp_path,'https://public.test',public_only=True)
    assert notify.call_count==2
    assert private_json(tmp_path/'monitor-state.json')['pending_notifications']==backlog[2:]


def test_public_monitor_observes_maintenance(tmp_path):
    with patch.object(monitor,'http_json',return_value={'ok':True,'maintenance':True}):
        for _ in range(3):
            result=monitor.check(tmp_path,'https://public.test',public_only=True)
    assert result==1 and private_json(tmp_path/'monitor-state.json')['active']==['READINESS_FAILED']


def test_docker_diagnostics_are_not_printed():
    from subprocess import CompletedProcess
    with patch('scripts.production.subprocess.run',return_value=CompletedProcess([],1,'synthetic-secret','private-url-and-key')):
        with pytest.raises(RuntimeError) as failure:
            docker(['version'])
    assert 'synthetic-secret' not in str(failure.value) and 'private-url' not in str(failure.value)


def test_release_preflight_never_enters_maintenance_on_foreign_image(tmp_path):
    manager=Production(tmp_path/'root')
    with patch.object(manager,'configuration',return_value=({},{})), patch.object(manager,'inspect_image',side_effect=RuntimeError('Incompatible image')), patch.object(manager,'set_maintenance') as maintenance:
        with pytest.raises(RuntimeError,match='Incompatible'):
            manager.release('foreign-image')
        maintenance.assert_not_called()


def test_retention_never_removes_unrelated_directories_or_symlinks(tmp_path):
    manager=Production(tmp_path/'root')
    source=Store(tmp_path/'fixture')
    manager.snapshots.mkdir()
    for i in range(10):
        backup(source.directory,manager.snapshots/f'{100+i}-abcdef')
    unrelated=manager.snapshots/'participant-files'
    unrelated.mkdir(); (unrelated/'keep').write_text('synthetic')
    (manager.snapshots/'999-abcdef').symlink_to(unrelated,target_is_directory=True)
    manager.prune_local_snapshots()
    kept=sorted(path.name for path in manager.snapshots.iterdir() if path.name.startswith('10'))
    assert kept==[f'{i}-abcdef' for i in range(103,110)]
    assert (unrelated/'keep').exists() and (manager.snapshots/'999-abcdef').is_symlink()
    for item in kept:
        verify(manager.snapshots/item)


def test_backup_detects_tampering_and_refuses_symlink_source(tmp_path):
    source=Store(tmp_path/'fixture'); saved=tmp_path/'saved';backup(source.directory,saved)
    (saved/'pilot.sqlite3').write_bytes(b'synthetic-corruption')
    with pytest.raises(ValueError,match='checksum'):
        verify(saved)
    link=tmp_path/'link';link.symlink_to(source.directory,target_is_directory=True)
    with pytest.raises(ValueError,match='symlink'):
        backup(link,tmp_path/'new')


def test_failed_offline_copy_resumes_same_data_before_reporting_failure(tmp_path):
    manager=Production(tmp_path/'root');release={'release':'fixture','image':'fixture','config':{}}
    events=[]
    with patch.object(manager,'state',return_value={'current':release}), patch.object(manager,'set_maintenance'), patch.object(manager,'stop',side_effect=lambda:events.append('stop')), patch.object(manager,'snapshot',side_effect=OSError('disk-full')), patch.object(manager,'container',return_value=None), patch.object(manager,'start',side_effect=lambda r:events.append('start')), patch.object(manager,'wait_ready',side_effect=lambda r:events.append('ready')), patch.object(manager,'activate',side_effect=lambda r:events.append('activate')), patch.object(manager,'encrypted_backup') as encrypt:
        with pytest.raises(OSError,match='disk-full'):
            manager.scheduled_backup()
        encrypt.assert_not_called()
    assert events==['stop','start','ready','activate']
