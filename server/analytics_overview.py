"""Compact owner dashboard. Counts retain their entity grain and unknown costs."""
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Moscow')


def ratio(numerator, denominator):
    return {'numerator': numerator, 'denominator': denominator,
            'value': round(100 * numerator / denominator, 2) if denominator else None}


def practice_costs(db, practices):
    """Journal survives quota/usage pruning; missing response prices stay unknown."""
    costs = {p['id']: {'attempts': 0, 'priced_attempts': 0, 'known_cost': 0.0} for p in practices}
    starts = Counter()
    for e in db.execute("SELECT kind,practice_id,correlation_id,data FROM analytics_events WHERE kind IN ('provider_attempt_started','provider_cost_recorded')"):
        pid = e['practice_id'] or e['correlation_id']
        if pid not in costs:
            continue
        if e['kind'] == 'provider_attempt_started':
            starts[pid] += 1
        else:
            data = json.loads(e['data'])
            value = data.get('gateway_cost')
            if type(value) in (int, float) and math.isfinite(value) and value >= 0 and data.get('cost_unit') == 'gateway_unit':
                costs[pid]['priced_attempts'] += 1
                costs[pid]['known_cost'] += value
    usage_counts = Counter()
    for row in db.execute('''SELECT coalesce(j.practice_id,l.practice_id) practice_id,u.data
                            FROM usage u LEFT JOIN jobs j ON j.id=u.job_id
                            LEFT JOIN live_chunks l ON l.id=u.job_id'''):
        if row['practice_id'] in costs:
            usage_counts[row['practice_id']] += len(json.loads(row['data']).get('attempts') or [None])
    for p in practices:
        c = costs[p['id']]
        c['attempts'] = max(starts[p['id']], usage_counts[p['id']], c['priced_attempts'])
        c['complete'] = c['attempts'] > 0 and c['priced_attempts'] == c['attempts']
        c['total'] = c['known_cost'] if c['complete'] else None
        c['unit'] = 'gateway_unit'
        p['cost'] = c
    return costs


def overview(db, result, all_practices):
    start, end = result['period']['from'], result['period']['to']
    moment = result['as_of']
    cutoff = min(moment, end)
    accounts = [a for a in result['account_roster'] if a['created'] < cutoff]
    account_ids = {a['id'] for a in accounts}
    current_account_ids = {a['id'] for a in result['account_roster']}
    all_ids = {p['id'] for p in all_practices}
    rows = result['practices']
    # Creating setup alone is not a started training. Saved speech proves a start
    # even when the old browser never emitted capture_started.
    capture_ids = {e[0] for e in db.execute("SELECT DISTINCT practice_id FROM analytics_events WHERE kind='capture_started' AND json_extract(data,'$.segment_index')=0 AND occurred<=?", (moment,))}
    started = [p for p in rows if p['speech_at'] or p['id'] in capture_ids]
    counts = Counter(p['user_id'] for p in started)
    speeches_by_user = defaultdict(list)
    for p in all_practices:
        if p['speech_at']:
            speeches_by_user[p['user_id']].append((p['id'], p['speech_at']))
    costs = practice_costs(db, rows)
    for account in accounts:
        account['practices'] = counts[account['id']]
    # Confirmed saved recordings, deduplicated by owner and Moscow calendar day.
    recordings = [(r['user_id'], r['created']) for r in db.execute('SELECT p.user_id,s.created,p.id FROM segments s JOIN practices p ON p.id=s.practice_id')
                  if r['user_id'] in current_account_ids and r['id'] in all_ids]
    day_start = datetime.fromtimestamp(cutoff - .001, ZONE).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    def active(a, b):
        return {uid for uid, at in recordings if a <= at < b}
    previous = active(cutoff - 14 * 86400, cutoff - 7 * 86400)
    current = active(cutoff - 7 * 86400, cutoff)
    retained = previous & current
    daily = []
    cursor = datetime.fromtimestamp(start, ZONE)
    registrations = Counter(datetime.fromtimestamp(a['created'], ZONE).date().isoformat() for a in accounts if start <= a['created'] < end)
    active_days = defaultdict(set)
    for uid, at in recordings:
        if start <= at < cutoff:
            active_days[datetime.fromtimestamp(at, ZONE).date().isoformat()].add(uid)
    while cursor.timestamp() < end:
        key = cursor.date().isoformat()
        daily.append({'day': key, 'registered': registrations[key], 'active': len(active_days[key])})
        cursor += timedelta(days=1)
    priced = [p for p in rows if costs[p['id']]['complete']]
    charged = [p for p in rows if costs[p['id']]['attempts'] or p['report_at'] or p['questions_at'] or p['failures']]
    all_priced = bool(charged) and len(priced) == len(charged)
    total = sum(costs[p['id']]['known_cost'] for p in charged)
    payers = {p['user_id'] for p in charged}
    economy = {'unit': 'gateway_unit', 'total': total if all_priced else None,
               'known_total': total, 'practices': len(charged), 'priced_practices': len(priced), 'users': len(payers),
               'known_per_practice': total / len(charged) if charged else None,
               'known_per_user': total / len(payers) if payers else None,
               'per_practice': total / len(charged) if all_priced else None,
               'per_user': total / len(payers) if all_priced else None,
               'attempts': sum(c['attempts'] for c in costs.values()),
               'priced_attempts': sum(c['priced_attempts'] for c in costs.values())}
    # Acquisition is visit-based; training conversion is practice-based.
    # Multiplying these funnels would mix denominators.
    sessions = {r['id']: dict(r) for r in db.execute('SELECT id,actor_id,created,last_activity FROM analytics_sessions')}
    landings = {}
    auth_events = defaultdict(list)
    for e in db.execute("SELECT kind,session_id,actor_id,occurred,data FROM analytics_events WHERE kind IN ('page_viewed','registration_confirmed','login') AND occurred>=? AND occurred<?", (start, cutoff)):
        if e['kind'] == 'page_viewed' and json.loads(e['data']).get('route_id') == '/landing' and e['session_id']:
            session = sessions.get(e['session_id'], {})
            actor = e['actor_id'] or session.get('actor_id')
            if actor and actor not in account_ids:
                continue
            if any(result['filters'][k] for k in ('actor_id', 'source', 'campaign', 'role', 'classification', 'scenario', 'questions', 'duration', 'report_version')) and actor not in account_ids:
                continue
            landings[e['session_id']] = min(landings.get(e['session_id'], float('inf')), e['occurred'])
        elif e['actor_id'] in account_ids:
            auth_events[e['session_id']].append(e['occurred'])
    authenticated = {}
    for sid, at in landings.items():
        matches = [t for t in auth_events.get(sid, []) if at <= t]
        if matches:
            authenticated[sid] = min(matches)
    started_ids = {p['id'] for p in started}
    launched_visits = {e['session_id'] for e in db.execute("SELECT session_id,practice_id,occurred FROM analytics_events WHERE kind='capture_started' AND json_extract(data,'$.segment_index')=0 AND occurred>=? AND occurred<?", (start, cutoff))
                       if e['session_id'] in authenticated and e['practice_id'] in started_ids and e['occurred'] >= authenticated[e['session_id']]}
    acquisition = [
        {'label': 'Просмотр лендинга', 'count': len(landings), 'conversion': None},
        {'label': 'Регистрация или вход', 'count': len(authenticated), 'conversion': ratio(len(authenticated), len(landings))},
        {'label': 'Запуск тренировки', 'count': len(launched_visits), 'conversion': ratio(len(launched_visits), len(authenticated))}]
    def step(label, group, base):
        return {'label': label, 'count': len(group), 'conversion': ratio(len(group), len(base))}
    speech_ids = {p['id'] for p in started if p['speech_at']}
    training = [step('Запуск тренировки', started_ids, started_ids), step('Выступление сохранено', speech_ids, started_ids)]
    previous_ids = {p['id'] for p in started if p['questions'] and p['id'] in speech_ids}
    for index in (1, 2, 3):
        ids = {p['id'] for p in started if p['id'] in previous_ids and p['answer_' + str(index)]}
        training.append(step('Ответ на вопрос ' + str(index), ids, previous_ids))
        previous_ids = ids
    eligible = previous_ids | {p['id'] for p in started if not p['questions'] and p['id'] in speech_ids}
    reports = {p['id'] for p in started if p['id'] in eligible and p['report_at']}
    viewed = reports & set(result['observed_memberships']['report_viewed'])
    view_times = {r['practice_id']: r['at'] for r in db.execute("SELECT practice_id,MIN(occurred) at FROM analytics_events WHERE kind='report_viewed' GROUP BY practice_id")}
    repeated = {p['id'] for p in started if p['id'] in viewed and any(max(p['report_at'],view_times[p['id']]) < at <= moment and pid != p['id'] for pid, at in speeches_by_user[p['user_id']])}
    training.extend([step('Отчёт получен', reports, eligible), step('Отчёт просмотрен', viewed, reports), step('Повторная тренировка', repeated, viewed)])
    result['overview'] = {'definition_version': 'owner-overview-v1', 'accounts': len(accounts), 'started_practices': len(started),
                          'average_per_user': len(started) / len(accounts) if accounts else None,
                          'average_per_trainee': len(started) / len(counts) if counts else None,
                          'trainees': len(counts), 'dau': len(active(day_start, cutoff)),
                          'dau_day': datetime.fromtimestamp(day_start, ZONE).date().isoformat(),
                          'last_hour': len(active(moment - 3600, moment)),
                          'retention_7d': ratio(len(retained), len(previous)),
                          'churn_7d': ratio(len(previous - current), len(previous)),
                          'activity_until': cutoff, 'daily': daily, 'economy': economy,
                          'acquisition_funnel': acquisition, 'training_funnel': training,
                          'questions_disabled': sum(not p['questions'] for p in started)}
    return result
