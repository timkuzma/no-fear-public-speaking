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
