"""Reconcile reported gateway prices; never send a generation or infer a tariff."""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import time
from urllib.parse import urlsplit

import httpx
from .analytics_events import record

FIELDS = ('request_id', 'spend', 'model', 'prompt_tokens', 'completion_tokens', 'startTime', 'endTime')


def amount(value):
    try:
        return float(value) if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


def epoch(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
    except (ValueError, TypeError, AttributeError, OverflowError, OSError):
        return None


def model_name(value):
    return str(value).rsplit('/', 1)[-1].lower()


def reconcile(db, ledger, *, apply=True):
    """Match unique request IDs or model/tokens inside durable attempt intervals."""
    ledger = [{k:r.get(k) for k in FIELDS} for r in ledger if isinstance(r,dict)]
    ledger = [r for r in ledger if isinstance(r['request_id'],str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',r['request_id']) and amount(r['spend']) is not None]
    counts = defaultdict(int)
    for r in ledger:counts[r['request_id']] += 1
    ledger = [r for r in ledger if counts[r['request_id']] == 1]
    by_request = {r['request_id']:r for r in ledger}
    by_model = defaultdict(list)
    for r in ledger:by_model[model_name(r['model'])].append(r)
    starts = defaultdict(list); finished = {}; existing = {}; bound = {}
    for e in db.execute("SELECT event_id,kind,occurred,data FROM analytics_events WHERE kind IN ('provider_attempt_started','provider_attempt_finished','provider_cost_recorded')"):
        data=json.loads(e['data']);aid=data.get('attempt_id')
        if e['kind']=='provider_attempt_started':starts[(data.get('job_id'),data.get('operation'))].append((e['occurred'],aid))
        elif e['kind']=='provider_attempt_finished':finished[aid]=e['occurred']
        else:
            existing[e['event_id']]=data
            if data.get('provider_request_id'):bound[data['provider_request_id']]=e['event_id']
    for values in starts.values():values.sort()
    proposals=[];unmatched=0
    rows=db.execute('''SELECT u.id,u.job_id,u.user_id,u.created,u.data,coalesce(j.practice_id,l.practice_id) practice_id
                       FROM usage u LEFT JOIN jobs j ON j.id=u.job_id LEFT JOIN live_chunks l ON l.id=u.job_id
                       WHERE coalesce(j.practice_id,l.practice_id) IS NOT NULL ORDER BY u.created,u.id''').fetchall()
    previous={}
    for row in rows:
        usage=json.loads(row['data']);operation=usage.get('operation');key=(row['job_id'],operation)
        attempts=usage.get('attempts') or [usage]
        candidates=[r for r in starts[key] if previous.get(key,0)<r[0]<=row['created']]
        # Recovery can leave an older unaccounted attempt. It stays unknown.
        ordered=candidates[-len(attempts):] if len(candidates)>=len(attempts) else []
        previous[key]=row['created']
        for index,attempt in enumerate(attempts):
            aid=attempt.get('attempt_id') or (ordered[index][1] if ordered else None)
            event_id='cost:'+aid if aid else 'cost:usage:'+row['id']+':'+str(index)
            saved=existing.get(event_id,{})
            if amount(saved.get('gateway_cost')) is not None and saved.get('provider_request_id') in by_request:continue
            request_id=attempt.get('provider_request_id')
            matches=[]
            if request_id and request_id in by_request:
                matches=[by_request[request_id]]
            elif aid and ordered and aid in finished:
                start=ordered[index][0];end=finished[aid]
                for item in by_model[model_name(usage.get('model'))]:
                    a=epoch(item['startTime']);b=epoch(item['endTime'])
                    if a is None or b is None or not start-.15<=a<=b<=end+.15:continue
                    if any(attempt.get(local) is not None and attempt[local]!=item[remote] for local,remote in [('input_tokens','prompt_tokens'),('output_tokens','completion_tokens')]):continue
                    matches.append(item)
            if len(matches)!=1:unmatched+=1;continue
            item=matches[0]
            if amount(saved.get('gateway_cost')) is not None and not math.isclose(saved['gateway_cost'],item['spend'],rel_tol=1e-9,abs_tol=1e-9):
                unmatched+=1;continue
            if item['request_id'] in bound and bound[item['request_id']]!=event_id:unmatched+=1;continue
            proposals.append((event_id,row,item,aid,index))
    degrees=defaultdict(int)
    for _,_,item,_,_ in proposals:degrees[item['request_id']]+=1
    accepted=[p for p in proposals if degrees[p[2]['request_id']]==1]
    if apply:
        for event_id,row,item,aid,index in accepted:
            value=existing.get(event_id,{})|{'attempt_id':aid,'job_id':row['job_id'],'operation':json.loads(row['data']).get('operation'),
                'gateway_cost':amount(item['spend']),'cost_unit':'gateway_unit','provider_request_id':item['request_id'],
                'price_source':'provider_spend_log','usage_id':row['id'],'usage_attempt_index':index}
            if event_id in existing:db.execute('UPDATE analytics_events SET data=? WHERE event_id=?',(json.dumps(value),event_id))
            else:record(db,'provider_cost_recorded',row['user_id'],row['practice_id'],value,event_id=event_id)
    return {'matched':len(accepted),'unmatched':unmatched+len(proposals)-len(accepted),'recovered_cost':sum(p[2]['spend'] for p in accepted)}


async def sync_costs(store):
    """Owner reads refresh the existing key's ledger at most once per 30 seconds."""
    if os.getenv('APP_ENV')!='production':return
    key=os.getenv('LLM_API_KEY','');base=os.getenv('LLM_BASE_URL','').rstrip('/').removesuffix('/v1')
    parsed=urlsplit(base)
    if not key or parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:return
    moment=time.time()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        last=db.execute("SELECT value FROM analytics_meta WHERE key='cost_sync_at'").fetchone()
        if last and moment-float(last[0])<30:return
        db.execute("INSERT OR REPLACE INTO analytics_meta VALUES('cost_sync_at',?)",(str(moment),))
    try:
        async with asyncio.timeout(6):
            async with httpx.AsyncClient(timeout=5.5,follow_redirects=False) as client:
                async with client.stream('GET',base+'/spend/logs',headers={'Authorization':'Bearer '+key},params={'api_key':hashlib.sha256(key.encode()).hexdigest()}) as response:
                    response.raise_for_status();raw=bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw)>8*1024*1024:return
                payload=json.loads(raw)
        rows=payload if isinstance(payload,list) else payload.get('data',[]) if isinstance(payload,dict) else []
        if not isinstance(rows,list) or len(rows)>10000:return
        def save():
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                return reconcile(db,rows)
        await asyncio.to_thread(save)
    except (httpx.HTTPError,TimeoutError,ValueError,TypeError,KeyError):
        # The current known prices survive unavailable/late gateway accounting.
        return
