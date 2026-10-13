#!/usr/bin/env python3
"""Certbot deploy hook for this application's shared HAProxy TLS listener.

Install mode 0700 in /etc/letsencrypt/renewal-hooks/deploy/. Supply the exact
lineage with NFS_CERT_LINEAGE below when installing. Never log PEM contents.
"""
import os
from pathlib import Path
import subprocess
import tempfile

NFS_CERT_LINEAGE = '/etc/letsencrypt/live/pilot.example.org'
NFS_CERT_TARGET = '/etc/haproxy/certs/no-fear-stage.pem'


def publish(target, content):
    fd, temporary = tempfile.mkstemp(prefix='.no-fear-stage-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    if os.environ.get('RENEWED_LINEAGE') != NFS_CERT_LINEAGE:
        return
    source, target = Path(NFS_CERT_LINEAGE), Path(NFS_CERT_TARGET)
    previous = target.read_bytes()
    replacement = (source/'fullchain.pem').read_bytes() + (source/'privkey.pem').read_bytes()
    publish(target, replacement)
    try:
        subprocess.run(['haproxy', '-c', '-f', '/etc/haproxy/haproxy.cfg'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['systemctl', 'reload', 'haproxy'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        publish(target, previous)
        raise RuntimeError('Certificate publication failed; previous certificate preserved') from None


if __name__ == '__main__':
    main()
