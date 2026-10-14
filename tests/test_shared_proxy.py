"""Protect unrelated TLS domains and retain the last valid certificate."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import subprocess
import pytest


def hook():
    path=Path(__file__).resolve().parent.parent/'deploy/renew-haproxy-certificate.py'
    spec=importlib.util.spec_from_file_location('nfs_certificate_hook',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_hook_does_not_touch_other_projects(monkeypatch):
    module=hook();monkeypatch.setenv('RENEWED_LINEAGE','/etc/letsencrypt/live/unrelated.example')
    with patch.object(module.subprocess,'run') as command:
        module.main()
    command.assert_not_called()


def test_invalid_certificate_publication_keeps_previous_pem(tmp_path,monkeypatch):
    module=hook();source=tmp_path/'lineage';source.mkdir()
    (source/'fullchain.pem').write_bytes(b'synthetic-invalid-chain')
    (source/'privkey.pem').write_bytes(b'synthetic-invalid-key')
    target=tmp_path/'certificate.pem';target.write_bytes(b'previous-valid-fixture')
    monkeypatch.setattr(module,'NFS_CERT_LINEAGE',str(source))
    monkeypatch.setattr(module,'NFS_CERT_TARGET',str(target))
    monkeypatch.setenv('RENEWED_LINEAGE',str(source))
    with patch.object(module.subprocess,'run',side_effect=subprocess.CalledProcessError(1,'haproxy')) as command:
        with pytest.raises(RuntimeError,match='previous certificate preserved'):
            module.main()
    assert target.read_bytes()==b'previous-valid-fixture'
    assert target.stat().st_mode&0o077==0
    assert command.call_count==1


def nginx_hook():
    path = Path(__file__).resolve().parent.parent / 'deploy/renew-shared-nginx-certificate.py'
    spec = importlib.util.spec_from_file_location('nfs_nginx_certificate_hook', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shared_nginx_hook_ignores_other_lineages(monkeypatch):
    module = nginx_hook()
    monkeypatch.setenv('RENEWED_LINEAGE', '/etc/letsencrypt/live/unrelated.example')
    with patch.object(module.subprocess, 'run') as command, patch.object(module.os, 'chown') as chown:
        assert module.renew('/etc/no-fear-stage/letsencrypt/live/pilot.example', 'edge', 981) is False
    command.assert_not_called()
    chown.assert_not_called()


@pytest.mark.parametrize('valid', [False, True])
def test_shared_nginx_hook_validates_before_reload_and_keeps_pem_files(tmp_path, monkeypatch, valid):
    module = nginx_hook()
    lineage = tmp_path / 'live' / 'pilot.example'
    archive = tmp_path / 'archive' / 'pilot.example'
    lineage.mkdir(parents=True)
    archive.mkdir(parents=True)
    key = archive / 'privkey2.pem'
    key.write_bytes(b'synthetic-renewed-key')
    previous = archive / 'privkey1.pem'
    previous.write_bytes(b'synthetic-previous-key')
    (lineage / 'privkey.pem').symlink_to(key)
    monkeypatch.setenv('RENEWED_LINEAGE', str(lineage))
    failure = None if valid else subprocess.CalledProcessError(1, 'nginx')
    with patch.object(module.os, 'chown'), patch.object(module.subprocess, 'run', side_effect=failure) as command:
        if valid:
            assert module.renew(lineage, 'edge', 981) is True
        else:
            with pytest.raises(subprocess.CalledProcessError):
                module.renew(lineage, 'edge', 981)
    assert command.call_args_list[0].args[0] == ['docker', 'exec', 'edge', 'nginx', '-t']
    assert command.call_count == (2 if valid else 1)
    assert previous.read_bytes() == b'synthetic-previous-key'
    assert key.read_bytes() == b'synthetic-renewed-key'
    assert key.stat().st_mode & 0o777 == 0o640
