"""Content-free alerts with consecutive-failure confirmation and recovery notices."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.production import NoRedirect, atomic_json, http_json, private_json


def alerts(status, now):
    result = []
    if not status['storage']['ready']:
        result.append('STORAGE_UNAVAILABLE')
    if not status['workers']['ready']:
        result.append('WORKER_UNAVAILABLE')
    if status['maintenance_age_seconds'] is not None:
        if status['maintenance_age_seconds'] > 600:
            result.append('MAINTENANCE_STUCK')
    elif any(queue['oldest_age_seconds'] > status['queue_alert_seconds'] for queue in status['queues'].values()):
        result.append('QUEUE_STALLED')
    if not status['budget']['enabled']:
        result.append('AI_PAUSED')
    if status['failures_last_15m'] >= 3 or status['http_5xx_last_15m'] >= 3 or status['provider_failures_last_15m'] >= 3:
        result.append('ERROR_RATE_HIGH')
    used, maximum = status['budget']['used'], status['budget']['limits']
    for field, key in [('attempts','AI_DAILY_ATTEMPTS'),('audio_seconds','AI_DAILY_AUDIO_SECONDS'),('input_chars','AI_DAILY_INPUT_CHARS'),('output_tokens','AI_DAILY_OUTPUT_TOKENS')]:
        if used[field] >= maximum[key] * 0.9:
            result.append('AI_BUDGET_NEAR_LIMIT')
            break
    backup = status.get('backup') or {}
    if backup.get('offsite_configured') is not True:
        result.append('OFFSITE_BACKUP_NOT_CONFIGURED')
    for field, code in [('verified_at','BACKUP_STALE'),('encrypted_at','ENCRYPTED_BACKUP_STALE'),('restore_verified_at','RESTORE_CHECK_STALE')]:
        if not isinstance(backup.get(field), (float, int)) or now - backup[field] > status['backup_max_age_seconds']:
            result.append(code)
    operation = status.get('last_operation') or {}
    if operation.get('ok') is False:
        result.append('LAST_OPERATION_FAILED')
    return sorted(set(result))


def transition(previous, current, threshold=3):
    counts = {code: previous.get('counts', {}).get(code, 0) + 1 for code in current}
    active = sorted(code for code, count in counts.items() if count >= threshold)
    before = previous.get('active', [])
    change = {'opened': sorted(set(active) - set(before)), 'resolved': sorted(set(before) - set(active))}
    return {'counts': counts, 'active': active}, change


def notify(url, change):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError('Alert webhook must use HTTPS')
    # Generic codes only; no accounts, speech, provider URLs, credentials or request bodies.
    body = json.dumps({'service': 'no-fear-stage', **change}).encode()
    request = urllib.request.Request(url, body, {'Content-Type': 'application/json'}, method='POST')
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError('Alert delivery failed')


def check(root, url, public_only=False):
    credentials = private_json(root / 'secrets.json') if (root/'secrets.json').exists() else {}
    try:
        if public_only:
            status = http_json(url.rstrip('/') + '/api/readiness')
            current = [] if status.get('ok') and not status.get('maintenance') else ['READINESS_FAILED']
        else:
            status = http_json(url.rstrip('/') + '/api/operator/status', credentials['OPERATOR_TOKEN'])
            current = alerts(status, time.time())
    except (OSError, ValueError, KeyError, RuntimeError):
        current = ['SERVICE_UNREACHABLE']
    state_path = root / 'monitor-state.json'
    previous = private_json(state_path) if state_path.exists() else {}
    state, change = transition(previous, current)
    pending = previous.get('pending_notifications', [])
    if change['opened'] or change['resolved']:
        pending.append(change)
    pending = pending[-20:]
    webhook = credentials.get('ALERT_WEBHOOK_URL')
    delivery_failed = False
    if webhook:
        remaining = []
        for message in pending[:2]:
            try:
                notify(webhook, message)
            except (OSError, RuntimeError):
                remaining.append(message)
                delivery_failed = True
        pending = remaining + pending[2:]
    else:
        # Logging is the configured sink until a private webhook is supplied.
        pending = []
    atomic_json(state_path, {**state, 'pending_notifications': pending})
    output = {'alerts': state['active'], 'observed': current, 'changes': change,
              'notification_delivery_failed': delivery_failed, 'sink': 'webhook' if webhook else 'log'}
    print(json.dumps(output))
    return 1 if state['active'] or delivery_failed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--url', required=True)
    parser.add_argument('--public-only', action='store_true', help='Independent external readiness probe without operator credentials')
    args = parser.parse_args()
    try:
        return check(args.root, args.url, args.public_only)
    except (OSError, ValueError, RuntimeError):
        print('Monitor configuration/state failed', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
