"""Single-host release/backup controller. Only the labelled application is managed."""
import argparse
import hashlib
from contextlib import contextmanager
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.backup import backup, restore, verify
from server.locking import data_lock
from server.limits import DEFAULTS
from server.store import Store, now

APP = 'no-fear-stage'
SCHEMA = '1'
# Official restic 0.19.1 image, resolved and tested by digest.
RESTIC_IMAGE = 'restic/restic@sha256:136600b6ff6843d61d355f7f71f460a166429f35de6fd11b568fece3c9a4d510'
CONFIG_KEYS = {'ANALYTICS_ADMIN_ENABLED','ANALYTICS_CLIENT_ENABLED','ANALYTICS_EXPORT_ENABLED','APP_ORIGIN', 'LLM_BASE_URL', 'LLM_MODEL', 'FEEDBACK_EDITOR_MODEL', 'TRANSCRIPTION_MODEL', 'AI_ENABLED',
    'AI_DAILY_ATTEMPTS', 'AI_USER_DAILY_ATTEMPTS', 'AI_REQUESTS_PER_MINUTE', 'AI_DAILY_AUDIO_SECONDS',
    'AI_DAILY_INPUT_CHARS', 'AI_DAILY_OUTPUT_TOKENS', 'AI_MAX_OUTPUT_TOKENS', 'MAX_PENDING_JOBS',
    'MAX_PENDING_LIVE_CHUNKS', 'JOB_TIMEOUT_SECONDS', 'LIVE_JOB_TIMEOUT_SECONDS', 'MIN_FREE_DISK_BYTES',
    'QUEUE_ALERT_SECONDS', 'BACKUP_MAX_AGE_SECONDS', 'DAILY_JOB_LIMIT', 'DAILY_LIVE_CHUNK_LIMIT',
    'MAX_UPLOAD_BYTES', 'LLM_TIMEOUT_SECONDS', 'LLM_MAX_ATTEMPTS'}
BACKUP_ENV = {'RESTIC_REPOSITORY', 'RESTIC_PASSWORD', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
              'AWS_DEFAULT_REGION', 'AWS_SESSION_TOKEN', 'AZURE_ACCOUNT_NAME', 'AZURE_ACCOUNT_KEY',
              'B2_ACCOUNT_ID', 'B2_ACCOUNT_KEY'}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def http_json(url, token=None, timeout=5):
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password or parsed.fragment or parsed.scheme not in ('https', 'http'):
        raise RuntimeError('Invalid operational URL')
    if parsed.scheme == 'http' and parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('Operational HTTP is allowed only on loopback')
    headers = {'Authorization': 'Bearer ' + token} if token else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(1048577)
    if len(raw) > 1048576:
        raise RuntimeError('Operational response is too large')
    return json.loads(raw)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.status-')
    try:
        with os.fdopen(fd, 'w') as file:
            json.dump(value, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        if os.getuid() == 0:
            os.chown(name, path.parent.stat().st_uid, path.parent.stat().st_gid)
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def private_json(path):
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise RuntimeError('Configuration must be a private regular file (mode 0600)')
    if path.stat().st_size > 65536:
        raise RuntimeError('Configuration is too large')
    try:
        result = json.loads(path.read_text())
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (OSError, ValueError):
        raise RuntimeError('Invalid private configuration') from None


def docker(arguments, *, env=None, timeout=60, optional=False):
    try:
        result = subprocess.run(['docker', *arguments], capture_output=True, text=True,
                                timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Container command could not complete') from None
    if result.returncode:
        if optional:
            return None
        # Docker diagnostics and Restic URLs may include credentials. Never echo them.
        raise RuntimeError('Container operation failed; inspect private daemon logs')
    return result.stdout.strip()


class Production:
    def __init__(self, root, name=APP, port=9080, wait_seconds=60):
        self.root = Path(root).absolute()
        if self.root.is_symlink():
            raise RuntimeError('Deployment root must not be a symlink')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        if not re.fullmatch(r'[a-z][a-z0-9-]{2,60}', name) or not 1024 <= port <= 65535:
            raise RuntimeError('Invalid container name or loopback port')
        self.name, self.port, self.wait_seconds = name, port, wait_seconds
        self.data = self.root / 'data'
        self.snapshots = self.root / 'backups'
        self.state_path = self.root / 'release.json'
        self.url = f'http://127.0.0.1:{port}'

    @contextmanager
    def locked(self):
        with data_lock(self.root):
            yield

    def bootstrap(self):
        if (self.root / 'runtime.json').exists() or (self.root / 'secrets.json').exists():
            raise RuntimeError('Runtime configuration already exists')
        atomic_json(self.root / 'runtime.json', {'APP_ORIGIN': 'https://pilot.example.org',
                                  'LLM_BASE_URL': 'https://provider.invalid/v1', 'LLM_MODEL': 'gpt-5.4',
                                  'FEEDBACK_EDITOR_MODEL': 'deepseek-v3.2',
                    'TRANSCRIPTION_MODEL': 'whisper-large-v3'})
        atomic_json(self.root / 'secrets.json', {'LLM_API_KEY': '', 'OPERATOR_TOKEN': secrets.token_urlsafe(32),
                    'RESTIC_REPOSITORY': 'local', 'RESTIC_PASSWORD': secrets.token_urlsafe(48)})
        return {'initialized': True, 'credentials_required': True}

    def configuration(self):
        config = private_json(self.root / 'runtime.json')
        if set(config) - CONFIG_KEYS:
            raise RuntimeError('Unsupported runtime setting')
        for key, value in config.items():
            if key in DEFAULTS:
                try:
                    number = int(str(value))
                    if not DEFAULTS[key][1] <= number <= DEFAULTS[key][2]:
                        raise ValueError()
                except ValueError:
                    raise RuntimeError('Invalid production setting: ' + key) from None
            if key == 'AI_ENABLED' and str(value) not in ('0', '1'):
                raise RuntimeError('Invalid production setting: AI_ENABLED')
        for key in ('APP_ORIGIN', 'LLM_BASE_URL'):
            parsed = urllib.parse.urlsplit(str(config.get(key, '')))
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or (key == 'APP_ORIGIN' and parsed.path not in ('', '/')):
                raise RuntimeError('Production requires exact HTTPS origin and provider URL')
        credentials = private_json(self.root / 'secrets.json')
        if not isinstance(credentials.get('LLM_API_KEY'), str) or not credentials['LLM_API_KEY'].strip() or not isinstance(credentials.get('OPERATOR_TOKEN'), str) or len(credentials['OPERATOR_TOKEN']) < 24:
            raise RuntimeError('Private provider and operator credentials are required')
        return config, credentials

    def state(self):
        return private_json(self.state_path) if self.state_path.exists() else {'current': None, 'previous': None}

    def inspect_image(self, reference):
        result = json.loads(docker(['image', 'inspect', '--format', '{{json .}}', reference]))
        labels = result.get('Config', {}).get('Labels') or {}
        if labels.get('io.nfs.application') != APP or labels.get('io.nfs.schema') != SCHEMA:
            raise RuntimeError('Image application/schema labels are incompatible')
        image = result.get('Id', '')
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', image):
            raise RuntimeError('Immutable image identity is required')
        return image

    def container(self):
        raw = docker(['inspect', '--format', '{{json .}}', self.name], optional=True)
        if raw is None:
            return None
        record = json.loads(raw)
        labels = record.get('Config', {}).get('Labels') or {}
        if labels.get('io.nfs.root') != str(self.root) or labels.get('io.nfs.application') != APP:
            raise RuntimeError('Refusing to manage a container belonging to another deployment')
        return record

    def stop(self):
        record = self.container()
        if record and record['State']['Running']:
            docker(['stop', '--time', '45', self.name], timeout=60)
        if self.container() and self.container()['State']['Running']:
            raise RuntimeError('Application did not stop; backup is unsafe')

    def prepare_data(self):
        if self.data.is_symlink():
            raise RuntimeError('Private data must not be a symlink')
        self.data.mkdir(exist_ok=True, mode=0o700)
        uid, gid = (10001, 10001) if os.getuid() == 0 else (os.getuid(), os.getgid())
        if os.getuid() == 0:
            for path in [self.data, *self.data.rglob('*')]:
                if path.is_symlink():
                    raise RuntimeError('Private data contains a symlink')
                os.chown(path, uid, gid)
        return uid, gid

    def set_maintenance(self):
        self.prepare_data()
        marker = self.data / '.maintenance'
        marker.touch(mode=0o600, exist_ok=True)
        marker.chmod(0o600)
        self.prepare_data()

    def network(self):
        name = self.name + '-private'
        raw = docker(['network', 'inspect', '--format', '{{json .}}', name], optional=True)
        if raw is None:
            docker(['network', 'create', '--label', 'io.nfs.root=' + str(self.root), name])
            raw = docker(['network', 'inspect', '--format', '{{json .}}', name])
        record = json.loads(raw)
        if record.get('Labels', {}).get('io.nfs.root') != str(self.root):
            raise RuntimeError('Private network belongs to another deployment')
        gateway = record['IPAM']['Config'][0]['Gateway']
        ipaddress.ip_address(gateway)
        return name, gateway

    def start(self, release):
        config, credentials = self.configuration()
        # The selected release's nonsecret settings survive rollback; secrets use current rotation.
        config = release['config']
        uid, gid = self.prepare_data()
        network, gateway = self.network()
        if self.container():
            docker(['rm', self.name])
        arguments = ['run', '-d', '--name', self.name, '--label', 'io.nfs.application=' + APP,
                     '--label', 'io.nfs.root=' + str(self.root), '--restart', 'unless-stopped',
                     '--init', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                     '--memory', '1g', '--cpus', '2', '--pids-limit', '128', '--user', f'{uid}:{gid}',
                     '--tmpfs', '/tmp:rw,nosuid,noexec,size=268435456', '--network', network,
                     '--publish', f'127.0.0.1:{self.port}:8080',
                     '--mount', f'type=bind,source={self.data},target=/data',
                     '--log-opt', 'max-size=10m', '--log-opt', 'max-file=3']
        for key, value in {**config, 'APP_ENV': 'production', 'DATA_DIR': '/data',
                'APP_RELEASE': release['release'], 'TRUSTED_PROXY_IPS': '127.0.0.1,' + gateway}.items():
            arguments.extend(['--env', f'{key}={value}'])
        child_env = dict(os.environ)
        for key in ('LLM_API_KEY', 'OPERATOR_TOKEN'):
            child_env[key] = credentials[key]
            arguments.extend(['--env', key])  # Credentials never appear in command arguments/output.
        arguments.append(release['image'])
        docker(arguments, env=child_env)

    def wait_ready(self, release):
        deadline = time.monotonic() + self.wait_seconds
        while time.monotonic() < deadline:
            record = self.container()
            if not record or not record['State']['Running']:
                raise RuntimeError('Candidate application exited before readiness')
            try:
                ready = http_json(self.url + '/api/readiness')
                if ready.get('ok') and ready.get('release') == release['release']:
                    return
            except (OSError, ValueError, RuntimeError, urllib.error.URLError):
                pass
            time.sleep(1)
        raise RuntimeError('Candidate did not pass readiness before the deadline')

    def activate(self, release):
        (self.data / '.maintenance').unlink(missing_ok=True)
        deadline = time.monotonic() + self.wait_seconds
        while time.monotonic() < deadline:
            try:
                ready = http_json(self.url + '/api/readiness')
                if ready.get('ok') and ready.get('release') == release['release'] and ready.get('maintenance') is False:
                    return
            except (OSError, ValueError, RuntimeError, urllib.error.URLError):
                pass
            time.sleep(1)
        raise RuntimeError('Committed release did not finish activation; preserve current data and inspect/resume')

    def snapshot(self):
        if not (self.data / 'pilot.sqlite3').exists():
            return None
        self.snapshots.mkdir(exist_ok=True, mode=0o700)
        target = self.snapshots / (str(time.time_ns()) + '-' + secrets.token_hex(3))
        backup(self.data, target)
        # Every offline backup gets a complete restore rehearsal, not just a manifest read.
        with tempfile.TemporaryDirectory(dir=self.root, prefix='.restore-check-') as temporary:
            restore(target, Path(temporary) / 'data')
        return target

    def record_backup(self, **updates):
        path = self.data / '.backup-status.json'
        try:
            status = json.loads((self.root / 'backup-state.json').read_text())
        except (OSError, ValueError):
            status = {}
        status.update(updates)
        atomic_json(self.root / 'backup-state.json', status)
        atomic_json(path, status)

    def recover(self, saved, previous):
        self.stop()
        if saved:
            recovered = self.root / ('data-restored-' + secrets.token_hex(6))
            restore(saved, recovered)
            quarantine = self.root / ('failed-data-' + str(time.time_ns()))
            self.data.rename(quarantine)  # Preserve failed candidate data for investigation.
            recovered.rename(self.data)
        self.set_maintenance()
        if previous:
            self.start(previous)
            self.wait_ready(previous)
            self.record_backup(verified_at=time.time(), restore_verified_at=time.time())
            self.activate(previous)

    def release(self, reference=None, rollback=False):
        config, _ = self.configuration()
        state = self.state()
        previous = state['current']
        if rollback:
            if not state.get('previous'):
                raise RuntimeError('No previous release is recorded')
            candidate = state['previous']
            self.inspect_image(candidate['image'])
        else:
            image = self.inspect_image(reference)
            candidate = {'image': image, 'release': image.removeprefix('sha256:'), 'config': config}
        # Finish all image/network/config preflights before entering maintenance.
        self.network()
        self.container()
        self.set_maintenance()
        saved = None
        try:
            self.stop()
            saved = self.snapshot()
            self.start(candidate)
            self.wait_ready(candidate)
            if saved is None:  # First deployment has no prior database; verify its initialized data.
                self.stop()
                saved = self.snapshot()
                self.start(candidate)
                self.wait_ready(candidate)
            self.record_backup(verified_at=time.time(), restore_verified_at=time.time())
            atomic_json(self.state_path, {'current': candidate, 'previous': previous})
        except Exception:
            try:
                # A failed backup must not roll data back: restart the previous release as-is.
                self.recover(saved, previous)
            except Exception:
                raise RuntimeError('Release failed and recovery needs operator attention; maintenance remains active') from None
            raise RuntimeError('Release failed; previous release and verified data recovered' if previous else 'Initial release failed; data preserved in maintenance without a previous release') from None
        # No automatic restore may run after activation: accepted user writes must be preserved.
        self.activate(candidate)
        return {'release': candidate['release'], 'rollback': rollback, 'verified_backup': saved is not None}

    def restic(self, arguments, mounts=()):
        _, credentials = self.configuration()
        if not credentials.get('RESTIC_PASSWORD') or not credentials.get('RESTIC_REPOSITORY'):
            raise RuntimeError('Encrypted backup configuration is required')
        environment = dict(os.environ)
        command = ['run', '--rm', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--user', f'{os.getuid()}:{os.getgid()}', '--tmpfs', '/tmp:rw,nosuid,noexec,size=268435456',
                   '--env', 'RESTIC_CACHE_DIR=/tmp/cache']
        for key in BACKUP_ENV:
            if key in credentials:
                environment[key] = credentials[key]
                command.extend(['--env', key])
        if credentials['RESTIC_REPOSITORY'] == 'local' or credentials['RESTIC_REPOSITORY'].startswith('/'):
            repository = self.root / 'encrypted-backups' if credentials['RESTIC_REPOSITORY'] == 'local' else Path(credentials['RESTIC_REPOSITORY'])
            repository.mkdir(exist_ok=True, mode=0o700)
            environment['RESTIC_REPOSITORY'] = '/repository'
            command.extend(['--mount', f'type=bind,source={repository},target=/repository'])
        for source, destination, readonly in mounts:
            command.extend(['--mount', f'type=bind,source={source},target={destination}' + (',readonly' if readonly else '')])
        command.append(RESTIC_IMAGE)
        return docker([*command, *arguments], env=environment, timeout=3600)

    def encrypted_backup(self, saved):
        tag = 'deployment:' + hashlib.sha256((str(self.root) + ':' + self.name).encode()).hexdigest()[:24]
        result = self.restic(['backup', '/snapshot', '--json', '--host', APP, '--tag', tag], [(saved, '/snapshot', True)])
        summaries = [json.loads(line) for line in result.splitlines() if line.startswith('{')]
        snapshot_id = next((item['snapshot_id'] for item in summaries if item.get('message_type') == 'summary'), None)
        if not snapshot_id or not re.fullmatch(r'[a-f0-9]{8,64}', snapshot_id):
            raise RuntimeError('Encrypted backup did not return a snapshot identity')
        self.restic(['check', '--read-data'])
        with tempfile.TemporaryDirectory(dir=self.root, prefix='.encrypted-restore-') as temporary:
            self.restic(['restore', snapshot_id, '--target', '/restore'], [(Path(temporary), '/restore', False)])
            recovered = Path(temporary) / 'snapshot'
            verify(recovered)
            with tempfile.TemporaryDirectory(dir=self.root, prefix='.restore-check-') as checked:
                restore(recovered, Path(checked) / 'data')
        # Retention is scoped to this deployment, never another repository user.
        self.restic(['forget', '--host', APP, '--path', '/snapshot', '--tag', tag,
                     '--group-by', 'host,paths,tags', '--keep-daily', '7', '--keep-weekly', '4',
                     '--keep-monthly', '6', '--prune'])
        self.restic(['check', '--read-data'])
        _, credentials = self.configuration()
        self.record_backup(encrypted_at=time.time(), restore_verified_at=time.time(), offsite_configured=credentials['RESTIC_REPOSITORY'] != 'local' and not credentials['RESTIC_REPOSITORY'].startswith('/'))
        self.prune_local_snapshots()
        return snapshot_id

    def prune_local_snapshots(self):
        candidates = sorted((path for path in self.snapshots.iterdir()
            if re.fullmatch(r'[0-9]+-[a-f0-9]{6}', path.name) and path.is_dir() and not path.is_symlink()),
            key=lambda path: int(path.name.split('-')[0]), reverse=True)
        for path in candidates[7:]:
            verify(path)
            shutil.rmtree(path)

    def scheduled_backup(self):
        state = self.state()
        current = state.get('current')
        if not current:
            raise RuntimeError('No managed current release')
        self.set_maintenance()
        saved = None
        try:
            self.stop()
            saved = self.snapshot()
            if saved is None:
                raise RuntimeError('Application database is missing')
        finally:
            record = self.container()
            if not record or not record['State']['Running']:
                self.start(current)
            self.wait_ready(current)
            self.activate(current)
        self.record_backup(verified_at=time.time(), restore_verified_at=time.time())
        snapshot_id = self.encrypted_backup(saved)  # Slow repository IO occurs after service resumes.
        return {'backup_verified': True, 'encrypted_restore_verified': True, 'snapshot_id': snapshot_id}

    def restore_encrypted(self, snapshot_id):
        if self.data.exists() or self.container():
            raise RuntimeError('Disaster restore requires a new deployment root without a container or data')
        if not re.fullmatch(r'[a-f0-9]{8,64}', snapshot_id or ''):
            raise RuntimeError('An explicit encrypted snapshot identity is required')
        self.restic(['check', '--read-data'])
        with tempfile.TemporaryDirectory(dir=self.root, prefix='.disaster-restore-') as temporary:
            self.restic(['restore', snapshot_id, '--target', '/restore'], [(Path(temporary), '/restore', False)])
            recovered = Path(temporary) / 'snapshot'
            verify(recovered)
            restore(recovered, self.data)
        self.record_backup(restore_verified_at=time.time())
        return {'restored': True, 'snapshot_id': snapshot_id, 'application_started': False}

    def resume(self):
        current = self.state().get('current')
        if not current:
            raise RuntimeError('No committed release is available for recovery')
        self.inspect_image(current['image'])
        self.set_maintenance()
        self.stop()
        saved = self.snapshot()
        if saved is None:
            raise RuntimeError('Verified application data is required for resume')
        self.start(current)
        self.wait_ready(current)
        self.activate(current)
        return {'resumed': True, 'release': current['release'], 'data_preserved': True}

    def set_ai(self, enabled):
        if not (self.data / 'pilot.sqlite3').is_file():
            raise RuntimeError('Application data is required')
        record = self.container()
        if record and record['State']['Running']:
            code = "import os,json; from server.store import Store,now; s=Store(os.environ['DATA_DIR']); s.execute(\"INSERT INTO operational_state VALUES('ai_enabled',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated=excluded.updated\", (" + repr(json.dumps(enabled)) + ",now()))"
            docker(['exec', self.name, 'python', '-c', code])
        else:
            with data_lock(self.data):
                store = Store(self.data)
                store.execute("INSERT INTO operational_state VALUES('ai_enabled',?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated=excluded.updated", (json.dumps(enabled), now()))
        return {'ai_enabled_by_operator': enabled}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['init', 'deploy', 'rollback', 'backup', 'init-backup', 'restore-backup', 'resume', 'pause-ai', 'resume-ai', 'status'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--name', default=APP)
    parser.add_argument('--port', type=int, default=9080)
    parser.add_argument('--image')
    parser.add_argument('--snapshot-id')
    parser.add_argument('--wait-seconds', type=int, default=60)
    args = parser.parse_args()
    manager = Production(args.root, args.name, args.port, args.wait_seconds)
    try:
        with manager.locked():
            try:
                result = perform(manager, args)
            except (RuntimeError, OSError, ValueError):
                record_operation(manager, args.action, False)
                raise
            record_operation(manager, args.action, True)
        print(json.dumps(result))
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print('Operation failed; service/data state must be checked privately', file=sys.stderr)
        return 1
    return 0


def record_operation(manager, action, ok):
    if manager.data.exists() and action in ('deploy', 'rollback', 'backup', 'resume', 'restore-backup'):
        atomic_json(manager.data / '.operation-status.json', {'action': action, 'finished_at': time.time(), 'ok': ok})


def perform(manager, args):
    if args.action == 'init':
        result = manager.bootstrap()
    elif args.action == 'deploy':
        if not args.image:
            raise RuntimeError('Deployment requires an already-built immutable application image')
        result = manager.release(args.image)
    elif args.action == 'rollback':
        result = manager.release(rollback=True)
    elif args.action == 'backup':
        result = manager.scheduled_backup()
    elif args.action == 'init-backup':
        manager.restic(['init'])
        result = {'encrypted_repository_initialized': True}
    elif args.action == 'restore-backup':
        result = manager.restore_encrypted(args.snapshot_id)
    elif args.action == 'resume':
        result = manager.resume()
    elif args.action in ('pause-ai', 'resume-ai'):
        result = manager.set_ai(args.action == 'resume-ai')
    else:
        result = manager.state()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
