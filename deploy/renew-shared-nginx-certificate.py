"""Reload one shared edge after renewal of this application's isolated lineage."""
import argparse
import os
from pathlib import Path
import re
import subprocess


def renew(lineage, container, group_id):
    expected = Path(lineage)
    if os.environ.get('RENEWED_LINEAGE', '').rstrip('/') != str(expected).rstrip('/'):
        return False
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{1,100}', container) or group_id < 0:
        raise ValueError('Invalid edge configuration')
    archive = expected.parent.parent / 'archive' / expected.name
    key = (expected / 'privkey.pem').resolve(strict=True)
    if key.parent != archive.resolve(strict=True):
        raise ValueError('Unexpected certificate key location')
    os.chown(key, -1, group_id)
    key.chmod(0o640)
    # Certbot retains previous PEM files in its archive. Do not rewrite them;
    # failed validation leaves the running proxy's previous TLS context intact.
    for arguments in (['nginx', '-t'], ['nginx', '-s', 'reload']):
        subprocess.run(['docker', 'exec', container, *arguments], check=True,
                       capture_output=True, timeout=30)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lineage', required=True)
    parser.add_argument('--container', required=True)
    parser.add_argument('--group-id', required=True, type=int)
    args = parser.parse_args()
    try:
        changed = renew(args.lineage, args.container, args.group_id)
    except (OSError, ValueError, subprocess.SubprocessError):
        parser.exit(1, 'Certificate reload failed; previous PEM archive retained.\n')
    if changed:
        print('Certificate verified and shared proxy reloaded')


if __name__ == '__main__':
    main()
