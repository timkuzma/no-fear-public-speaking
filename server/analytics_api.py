"""Owner-only analytics, evidence and bounded imports. No operator secret reaches the browser."""
import asyncio
import csv
import hashlib
import io
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import time
import uuid
import zipfile
from datetime import datetime,timedelta
from decimal import Decimal,InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request,HTTPException
from fastapi.responses import FileResponse,Response,JSONResponse
from . import analytics_events as ev
from .analytics_metrics import calculate,period,ZONE


def reject(code,message,status=422):raise HTTPException(status,detail={'code':code,'message':message})


def is_owner(store,user_id):
    if os.getenv('ANALYTICS_ADMIN_ENABLED','1')=='0':return False
    return bool(store.one('SELECT user_id FROM admin_memberships WHERE user_id=? AND revoked IS NULL',(user_id,)))


def safe_csv(rows):
    if not rows:return '\ufeff'
    output=io.StringIO();keys=list(rows[0]);writer=csv.DictWriter(output,fieldnames=keys);writer.writeheader()
    for row in rows:
        values={}
        for k in keys:
            v=row.get(k)
            if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False)
            if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')):v="'"+v
            values[k]=v
        writer.writerow(values)
    return '\ufeff'+output.getvalue()


def audit(store,actor,kind,data=None,practice=None):
    with store.connect() as db:ev.record(db,kind,actor,practice,data)


def identity(store,request,actor=None,touch=None):
    moment=time.time();visitor=request.cookies.get('nfs_visitor','')
    if not ev.ID_RE.fullmatch(visitor):visitor=uuid.uuid4().hex
    supplied=request.cookies.get('nfs_visit','')
    session=store.one('SELECT * FROM analytics_sessions WHERE id=? AND visitor_id=?',(supplied,visitor))
    if not session or session['last_activity']<moment-1800 or (session['actor_id'] is not None and session['actor_id']!=actor):
        session={'id':uuid.uuid4().hex,'visitor_id':visitor,'actor_id':actor,'created':moment,'last_activity':moment,'entry_route':'landing','touch_id':None}
        store.execute('INSERT INTO analytics_sessions VALUES(?,?,?,?,?,?,?)',tuple(session.values()))
    else:store.execute('UPDATE analytics_sessions SET last_activity=?,actor_id=coalesce(actor_id,?) WHERE id=?',(moment,actor,session['id']))
    if touch and not session['touch_id']:
        fields={k:str(touch.get(k,'')).strip()[:200] for k in ('source','medium','campaign','campaign_id','content','term','referrer_host')}
        if any('@' in v or '\n' in v for v in fields.values()):reject('ATTRIBUTION_INVALID','Метки не должны содержать личные данные.')
        fields['source']=fields['source'].lower() or 'direct';fields['medium']=fields['medium'].lower() or 'none'
        fields['referrer_host']=re.sub(r'[^a-zA-Z0-9.:-]','',fields['referrer_host'])[:200]
        tid=uuid.uuid4().hex
        with store.connect() as db:
            db.execute('INSERT OR IGNORE INTO acquisition_touches VALUES(?,?,?,?,?,?,?,?,?,?)',(tid,session['id'],moment,*fields.values()))
            db.execute('UPDATE analytics_sessions SET touch_id=? WHERE id=?',(tid,session['id']))
        session['touch_id']=tid
    return visitor,session['id']


def bind_registration(store,request,user_id):
    visitor,session_id=identity(store,request,user_id)
    with store.connect() as db:
        recent=db.execute('''SELECT t.* FROM acquisition_touches t JOIN analytics_sessions s ON s.id=t.session_id
          WHERE s.visitor_id=? AND (s.actor_id IS NULL OR s.actor_id=?) AND t.created>=? ORDER BY t.created DESC''',(visitor,user_id,time.time()-30*86400)).fetchall()
        chosen=next((t for t in recent if t['source'] not in ('direct','unknown')),recent[0] if recent else None)
        first=db.execute('''SELECT t.id FROM acquisition_touches t JOIN analytics_sessions s ON s.id=t.session_id
          WHERE s.visitor_id=? AND (s.actor_id IS NULL OR s.actor_id=?) ORDER BY t.created LIMIT 1''',(visitor,user_id)).fetchone()
        db.execute('INSERT OR IGNORE INTO account_attribution VALUES(?,?,?,?)',(user_id,chosen['id'] if chosen else None,first['id'] if first else None,'last-nondirect-30d-v1'))
        db.execute('UPDATE analytics_events SET session_id=?,visitor_id=? WHERE event_id=?',(session_id,visitor,'registration:'+user_id))
        db.execute('UPDATE analytics_events SET actor_id=? WHERE session_id=? AND actor_id IS NULL AND kind IN (\'registration_viewed\',\'registration_submitted\')',(user_id,session_id))
    return visitor,session_id


def cookies(response,visitor,session_id,production):
    for name,value,age in [('nfs_visitor',visitor,180*86400),('nfs_visit',session_id,1800)]:
        response.set_cookie(name,value,max_age=age,httponly=True,secure=production,samesite='lax',path='/')


def marketing(db,start,end,filters=None):
    filters=filters or {}
    a=datetime.fromtimestamp(start,ZONE).date().isoformat();b=datetime.fromtimestamp(end,ZONE).date().isoformat()
    items=[dict(r) for r in db.execute('SELECT * FROM marketing_stats WHERE active=1 AND day>=? AND day<? ORDER BY day,campaign_id',(a,b))]
    items=[r for r in items if (not filters.get('source') or r['platform']==filters['source']) and (not filters.get('campaign') or r['campaign_id']==filters['campaign'])]
    groups={}
    for r in items:
        key=(r['platform'],r['account'],r['campaign_id'],r['currency'],r['tax_mode'],r['timezone'])
        g=groups.setdefault(key,{'platform':r['platform'],'account':r['account'],'campaign_id':r['campaign_id'],'campaign':r['campaign_name'],'currency':r['currency'],'tax_mode':r['tax_mode'],'timezone':r['timezone'],'impressions':0,'clicks':0,'spend':Decimal(0),'days':set(),'registrations':0,'activated':0,'mature':end+37*86400<=time.time()})
        g['impressions']+=r['impressions'];g['clicks']+=r['clicks'];g['spend']+=Decimal(r['spend']);g['days'].add(r['day'])
    conversions=db.execute('''SELECT u.id,u.created,t.created touch_at,t.campaign_id,t.source,
      (SELECT MIN(j.finished) FROM jobs j JOIN practices p ON p.id=j.practice_id WHERE p.user_id=u.id AND j.kind='report' AND j.status='succeeded') first_report
      FROM users u JOIN account_attribution a ON a.account_id=u.id JOIN acquisition_touches t ON t.id=CASE WHEN ?='first' THEN a.first_touch_id ELSE a.touch_id END
      LEFT JOIN account_classifications c ON c.user_id=u.id WHERE t.created>=? AND t.created<? AND coalesce(c.classification,'participant') NOT IN ('staff','test')''',(filters.get('source_model','last'),start,end)).fetchall()
    for c in conversions:
        if not 0<=c['created']-c['touch_at']<=30*86400:continue
        candidates=[g for g in groups.values() if g['campaign_id']==c['campaign_id'] and g['platform']==c['source']]
        # No guessed cross-account/currency allocation. Ambiguity stays unlinked.
        if len(candidates)!=1:continue
        g=candidates[0]
        if datetime.fromtimestamp(c['touch_at'],ZONE).date().isoformat() not in g['days']:continue
        g['registrations']+=1
        if c['first_report'] and 0<=c['first_report']-c['created']<=7*86400:g['activated']+=1
    output=[]
    for g in groups.values():
        spend=float(g['spend']);g['days']=len(g['days']);g['spend']=spend
        g['ctr']=g['clicks']/g['impressions']*100 if g['impressions'] else None
        g['cpc']=spend/g['clicks'] if g['clicks'] else None;g['cpm']=spend/g['impressions']*1000 if g['impressions'] else None
        g['cost_registration']=spend/g['registrations'] if g['registrations'] else None;g['cost_activation']=spend/g['activated'] if g['activated'] else None
        if any(filters.get(k) for k in ('scenario','questions','duration','role','report_version','actor_id')):
            g['cost_registration']=None;g['cost_activation']=None;g['segment_cost_unavailable']=True
        output.append(g)
    creatives={}
    for r in items:
        key=(r['platform'],r['account'],r['campaign_id'],r['creative_id'],r['currency'],r['tax_mode'],r['timezone'])
        g=creatives.setdefault(key,{'platform':r['platform'],'account':r['account'],'campaign_id':r['campaign_id'],'creative_id':r['creative_id'],'currency':r['currency'],'tax_mode':r['tax_mode'],'impressions':0,'clicks':0,'spend':Decimal(0)})
        g['impressions']+=r['impressions'];g['clicks']+=r['clicks'];g['spend']+=Decimal(r['spend'])
    creative_items=[]
    for g in creatives.values():
        g['spend']=float(g['spend']);g['ctr']=g['clicks']/g['impressions']*100 if g['impressions'] else None
        g['cpc']=g['spend']/g['clicks'] if g['clicks'] else None;g['cpm']=g['spend']/g['impressions']*1000 if g['impressions'] else None
        creative_items.append(g)
    return {'batch_ids':sorted({r['batch_id'] for r in items}),'creative_items':creative_items,'items':output,'coverage':'uploaded_days_only','model':'first-observed-touch-v1' if filters.get('source_model')=='first' else 'last-nondirect-30d-v1','maturity_days':37,'budget_available':bool(items)}


def install(app,store,auth,check_origin,practice_json):
    calculation_slots=asyncio.Semaphore(2)
    def owner(request,mutate=False):
        user=auth(request,mutate)
        check_origin(request)
        if not is_owner(store,user['id']):reject('ADMIN_REQUIRED','Доступ к аналитике не предоставлен.',403)
        return user

    async def report(query):
        def read():
            with store.connect() as db:
                deadline=time.monotonic()+18
                db.set_progress_handler(lambda:int(time.monotonic()>deadline),10000)
                db.execute('BEGIN');data=calculate(db,query);data['marketing']=marketing(db,data['period']['from'],data['period']['to'],data['filters']);return data
        try:
            async with calculation_slots:
                return await asyncio.wait_for(asyncio.to_thread(read),20)
        except (ValueError,TypeError,OverflowError):reject('FILTER_INVALID','Проверь период и фильтры.')
        except sqlite3.OperationalError:reject('ANALYTICS_BUSY','Расчёт временно недоступен. Сократи период и повтори.',503)
        except asyncio.TimeoutError:reject('ANALYTICS_TIMEOUT','Расчёт занимает слишком много времени. Сократи период.',503)

    @app.post('/api/analytics/events')
    async def ingest(request:Request):
        check_origin(request)
        if os.getenv('ANALYTICS_CLIENT_ENABLED','1')=='0':return JSONResponse({'accepted':[],'duplicates':[],'rejected':[],'disabled':True})
        if request.headers.get('origin') is None and request.headers.get('sec-fetch-site')=='cross-site':reject('ORIGIN_DENIED','Запрос отклонён.',403)
        raw=await request.body()
        if len(raw)>65536:reject('EVENT_BATCH_TOO_LARGE','Слишком большой пакет событий.',413)
        try:body=json.loads(raw)
        except (ValueError,UnicodeError):reject('EVENT_INVALID','Некорректный пакет событий.')
        entries=body.get('events') if isinstance(body,dict) else None
        if not isinstance(entries,list) or not 1<=len(entries)<=50:reject('EVENT_INVALID','Пакет должен содержать от 1 до 50 событий.')
        try:user=auth(request)
        except HTTPException:user=None
        actor=user['id'] if user else None
        visitor,session_id=identity(store,request,actor,body.get('touch'))
        remote=hashlib.sha256((request.client.host if request.client else 'unknown').encode()).hexdigest()
        if store.limited('analytics-ip:'+remote,1200,300):reject('EVENT_LIMIT','Слишком много пакетов событий.',429)
        if store.limited('analytics:'+visitor,120,300):reject('EVENT_LIMIT','Слишком много пакетов событий.',429)
        accepted=[];duplicates=[];rejected=[]
        with store.connect() as db:
            for event in entries:
                eid=event.get('id') if isinstance(event,dict) else None
                try:
                    if not isinstance(event,dict) or not isinstance(eid,str) or not ev.ID_RE.fullmatch(eid) or event.get('kind') not in ev.CLIENT_EVENTS or event.get('schema_version',1)!=1:raise ValueError()
                    practice=event.get('practice_id')
                    if event['kind'] not in ('page_viewed','landing_cta_clicked','registration_viewed','registration_submitted','registration_failed') and not actor:raise ValueError()
                    if practice and (not actor or not ev.ID_RE.fullmatch(practice) or not db.execute('SELECT 1 FROM practices WHERE id=? AND user_id=?',(practice,actor)).fetchone()):raise ValueError()
                    # Queued events must never become another logged-in person's events.
                    if event.get('actor_context') not in (None,actor):raise ValueError()
                    data=ev.clean_data(event.get('data',{}))
                    version=data.get('report_version_id')
                    if event['kind'] in ('report_viewed','report_engaged'):
                        if not practice or not version or not db.execute("SELECT 1 FROM jobs WHERE id=? AND practice_id=? AND kind='report' AND status='succeeded'",(version,practice)).fetchone():raise ValueError()
                    if db.execute('SELECT 1 FROM analytics_events WHERE event_id=?',(eid,)).fetchone():duplicates.append(eid);continue
                    occurred=float(event.get('occurred',time.time()))
                    if not time.time()-86400<=occurred<=time.time()+60:occurred=time.time()
                    ev.record(db,event['kind'],actor,practice,data,event_id=eid,origin='client_observed',visitor=visitor,session=session_id,occurred=occurred)
                    accepted.append(eid)
                except (ValueError,TypeError,OverflowError):rejected.append(eid)
        response=JSONResponse({'accepted':accepted,'duplicates':duplicates,'rejected':rejected})
        cookies(response,visitor,session_id,app.state.production);return response

    @app.get('/api/admin/analytics/report')
    async def analytics(request:Request):
        owner(request);data=await report(dict(request.query_params))
        counts={}
        for a in data['accounts']:counts[a['source']]=counts.get(a['source'],0)+1
        data['accounts_by_source']=counts
        def choices():
            sources=store.all("SELECT source FROM acquisition_touches UNION SELECT platform source FROM marketing_stats UNION SELECT 'unknown' source ORDER BY source LIMIT 200")
            campaigns=store.all("SELECT id,MAX(name) name FROM (SELECT coalesce(nullif(campaign_id,''),campaign) id,campaign name FROM acquisition_touches UNION ALL SELECT campaign_id id,campaign_name name FROM marketing_stats) WHERE id<>'' GROUP BY id ORDER BY name,id LIMIT 500")
            return {'sources':[r['source'] for r in sources],'campaigns':campaigns}
        data['filter_options']=await asyncio.to_thread(choices)
        data.pop('practices',None);data.pop('accounts',None);data.pop('account_roster',None);data.pop('active_account_ids',None);data.pop('observed_memberships',None)
        return data

    @app.get('/api/admin/analytics/accounts')
    async def accounts(request:Request,kind:str='registrations',offset:int=0,limit:int=50):
        owner(request);data=await report(dict(request.query_params))
        items=data['accounts'] if kind=='registrations' else [a for a in data['account_roster'] if a['id'] in data['active_account_ids']]
        items.sort(key=lambda a:(a['created'],a['id']),reverse=True)
        return {'items':items[max(0,offset):max(0,offset)+min(100,max(1,limit))],'total':len(items)}

    @app.get('/api/admin/analytics/practices')
    async def practices(request:Request,offset:int=0,limit:int=50,stage:str=''):
        owner(request);data=await report(dict(request.query_params));items=data['practices']
        if stage in data['observed_memberships']:
            ids=set(data['observed_memberships'][stage]);items=[r for r in items if r['id'] in ids]
        elif stage in ('completed','failed'):
            items=[r for r in items if r['complete' if stage=='completed' else 'failures']]
        items.sort(key=lambda r:(r['created'],r['id']),reverse=True)
        return {'items':items[max(0,offset):max(0,offset)+min(100,max(1,limit))],'total':len(items),'as_of':data['as_of']}

    @app.get('/api/admin/analytics/practices/{pid}')
    async def detail(pid:str,request:Request):
        user=owner(request);p=store.one('SELECT * FROM practices WHERE id=?',(pid,))
        if not p:reject('NOT_FOUND','Тренировка не найдена.',404)
        audit(store,user['id'],'admin_evidence_opened',practice=pid)
        result=practice_json(p)
        u=store.one('SELECT id,name,email,role,created FROM users WHERE id=?',(p['user_id'],));result['participant']=u
        for segment in result['segments']:
            segment['media_url']=f'/api/admin/evidence/{pid}/segments/{segment["id"]}/media'
            row=store.one('SELECT filename FROM segments WHERE id=?',(segment['id'],));segment['available']=bool(row and (store.media/row['filename']).is_file())
        def integrity():
            for segment in result['segments']:
                row=store.one('SELECT s.filename,s.created,u.sha256 FROM segments s LEFT JOIN segment_uploads u ON u.segment_id=s.id WHERE s.id=?',(segment['id'],))
                segment['upload_sha256']=row['sha256'] if row else None
                segment['saved_at']=row['created'] if row else None
                try:
                    path=store.media/row['filename']
                    with path.open('rb') as file:
                        checksum=hashlib.file_digest(file,'sha256').hexdigest()
                    segment.update(stored_sha256=checksum,bytes=path.stat().st_size)
                except OSError:segment['available']=False
        await asyncio.to_thread(integrity)
        result['versions']=[{'id':r['id'],'finished':r['finished'],'report':json.loads(r['result'])} for r in store.all("SELECT id,finished,result FROM jobs WHERE practice_id=? AND kind='report' AND status='succeeded' ORDER BY finished DESC,id DESC LIMIT 100",(pid,)) if r['result']]
        result['feedback']=store.all('SELECT rating,text,created FROM feedback WHERE practice_id=? ORDER BY created DESC LIMIT 100',(pid,))
        result['trace']=events_query({'practice_id':pid,'limit':'500','from':datetime.fromtimestamp(max(p['created'],time.time()-179*86400),ZONE).date().isoformat(),'to':(datetime.now(ZONE).date()+timedelta(days=1)).isoformat()})
        return result

    @app.get('/api/admin/evidence/{pid}/segments/{sid}/media')
    async def media(pid:str,sid:str,request:Request,download:bool=False):
        user=owner(request);row=store.one('SELECT filename FROM segments WHERE id=? AND practice_id=?',(sid,pid))
        if not row or not (store.media/row['filename']).is_file():reject('NOT_FOUND','Запись недоступна.',404)
        audit(store,user['id'],'admin_media_download' if download else 'admin_media_view',{'segment_id':sid},pid)
        return FileResponse(store.media/row['filename'],media_type=mimetypes.guess_type(row['filename'])[0] or 'application/octet-stream',filename='recording'+Path(row['filename']).suffix if download else None,content_disposition_type='attachment' if download else 'inline',headers={'Cache-Control':'no-store'})

    def events_query(query):
        a,b=period(query);clauses=['occurred>=?','occurred<?'];args=[a,b]
        for key in ('practice_id','actor_id','kind','correlation_id','request_id','origin'):
            if query.get(key):
                if key=='practice_id':
                    clauses.append('(practice_id=? OR correlation_id=? OR request_id IN (SELECT request_id FROM analytics_events WHERE practice_id=? AND request_id IS NOT NULL))');args.extend([query[key]]*3)
                elif key=='correlation_id':
                    clauses.append("(correlation_id=? OR request_id=? OR event_id=? OR json_extract(data,'$.job_id')=?)");args.extend([query[key]]*4)
                else:clauses.append(key+'=?');args.append(query[key])
        before=int(query.get('before','0'));limit=min(10000 if query.get('format') in ('csv','ndjson') else 500,max(1,int(query.get('limit','100'))))
        if query.get('technical')!='true':clauses.append("kind NOT IN ('request','provider_attempt_started','provider_attempt_finished')")
        if query.get('errors')=='true':clauses.append("(kind IN ('service_failure','capture_interrupted','segment_upload_failed','registration_failed') OR CAST(json_extract(data,'$.status') AS INTEGER)>=400 OR json_extract(data,'$.error_code') IS NOT NULL)")
        if before:clauses.append('seq<?');args.append(before)
        items=store.all('SELECT * FROM analytics_events WHERE '+' AND '.join(clauses)+' ORDER BY seq DESC LIMIT ?',(*args,limit))
        for e in items:
            e['data']=json.loads(e['data'])
            e['level']='ERROR' if e['kind'] in ('service_failure','capture_interrupted','segment_upload_failed','registration_failed') or (isinstance(e['data'].get('status'),int) and e['data']['status']>=400) or e['data'].get('error_code') else 'INFO'
            e['delayed']=e['origin']=='client_observed' and abs(e['received']-e['occurred'])>60
        return {'items':items,'next_cursor':items[-1]['seq'] if len(items)==limit else None,'coverage':{'retention_days':180,'legacy_origin':'reconstructed','client_gaps_possible':True}}

    @app.get('/api/admin/analytics/events')
    async def events(request:Request):
        user=owner(request)
        try:result=await asyncio.to_thread(events_query,dict(request.query_params))
        except (ValueError,TypeError,OverflowError):reject('FILTER_INVALID','Проверь фильтры журнала.')
        if request.query_params.get('format') in ('csv','ndjson'):
            if os.getenv('ANALYTICS_EXPORT_ENABLED','1')=='0':reject('EXPORT_PAUSED','Выгрузка временно отключена.',503)
            audit(store,user['id'],'admin_log_export')
            if request.query_params['format']=='csv':return Response(safe_csv(result['items']),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="events.csv"'})
            return Response('\n'.join(json.dumps(r,ensure_ascii=False) for r in result['items']),media_type='application/x-ndjson',headers={'Content-Disposition':'attachment; filename="events.ndjson"'})
        return result

    @app.patch('/api/admin/analytics/account-classifications/{uid}')
    async def classify(uid:str,request:Request):
        user=owner(request,True);body=await request.json();c=body.get('classification')
        if c not in ('participant','staff','test','unknown') or not store.one('SELECT 1 FROM users WHERE id=?',(uid,)):reject('CLASSIFICATION_INVALID','Проверь аккаунт и категорию.')
        with store.connect() as db:
            db.execute('INSERT INTO account_classifications VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET classification=excluded.classification,updated=excluded.updated,actor_id=excluded.actor_id',(uid,c,time.time(),user['id']))
            ev.record(db,'admin_classification_changed',user['id'],data={'subject_id':uid,'classification':c})
        return {'ok':True}

    @app.get('/api/admin/analytics/quality')
    async def quality(request:Request):
        owner(request)
        def inventory():
            missing=[r['id'] for r in store.all('SELECT id,filename FROM segments') if not (store.media/r['filename']).is_file()]
            unmatched=store.one("SELECT COUNT(*) n FROM segments s LEFT JOIN analytics_events e ON e.event_id='segment:'||s.id WHERE e.seq IS NULL")['n']
            return {'missing_media_count':len(missing),'missing_media_ids':missing[:100],'segments_without_event':unmatched,'event_count':store.one('SELECT COUNT(*) n FROM analytics_events')['n'],'retention_days':180,'aggregate_retention_months':24,'offsite_configured':False,'provider_cost_currency_known':False,'deleted_practices':store.one('SELECT COUNT(*) n FROM analytics_deleted_facts')['n'],'daily_archives':store.all('SELECT day,calculated,data FROM analytics_rollups ORDER BY day DESC LIMIT 731'),'snapshots':store.all('SELECT id,created,sha256,revoked FROM analytics_snapshots ORDER BY created DESC LIMIT 100')}
        return await asyncio.to_thread(inventory)

    @app.post('/api/admin/marketing/imports')
    async def preview(request:Request):
        user=owner(request,True);raw=await request.body()
        if len(raw)>10*1024*1024:reject('IMPORT_TOO_LARGE','Файл превышает 10 MiB.',413)
        checksum=hashlib.sha256(raw).hexdigest();old=store.one('SELECT id,status FROM marketing_batches WHERE sha256=?',(checksum,))
        if old:return old|{'duplicate':True}
        try:
            reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
            required={'date','platform','account_id','campaign_id','campaign_name','creative_id','impressions','clicks','spend','currency','source_timezone','tax_mode'}
            if not reader.fieldnames or not required<=set(reader.fieldnames):raise ValueError('Не хватает обязательных колонок.')
            rows=[];keys=set()
            for index,r in enumerate(reader,2):
                if index>50001:raise ValueError('Слишком много строк.')
                r={k:r.get(k,'') for k in required}
                datetime.strptime(r['date'],'%Y-%m-%d')
                if r['source_timezone']!='Europe/Moscow':raise ValueError('Первая версия принимает дни Europe/Moscow; подготовь выгрузку в этом часовом поясе.')
                if not re.fullmatch('[A-Z]{3}',r['currency']) or r['tax_mode'] not in ('included','excluded','unknown'):raise ValueError('Проверь валюту и tax_mode.')
                impressions=int(r['impressions']);clicks=int(r['clicks']);spend=Decimal(r['spend'])
                if min(impressions,clicks)<0 or not spend.is_finite() or spend<0 or spend>Decimal('1000000000000'):raise ValueError('Отрицательные или некорректные показатели.')
                if any(len(str(v))>200 or '\x00' in str(v) for v in r.values()):raise ValueError('Слишком длинное значение.')
                key=tuple(r[k] for k in ('date','platform','account_id','campaign_id','creative_id','currency','tax_mode'))
                if key in keys:raise ValueError('Дублирование строки.')
                keys.add(key);rows.append(r|{'impressions':impressions,'clicks':clicks,'spend':str(spend)})
            if not rows:raise ValueError('Файл пуст.')
            grains={}
            for r in rows:grains.setdefault((r['date'],r['platform'],r['account_id'],r['campaign_id']),set()).add(bool(r['creative_id']))
            if any(len(g)>1 for g in grains.values()):raise ValueError('Нельзя смешивать кампанию целиком и отдельные объявления.')
        except (ValueError,InvalidOperation,UnicodeError,TypeError) as exc:
            message=str(exc)
            prefixes=('Не хватает','Первая версия','Проверь валюту','Отрицательные','Слишком','Дублирование','Нельзя смешивать','Файл пуст')
            reject('IMPORT_INVALID',message if isinstance(exc,ValueError) and message.startswith(prefixes) else 'Проверь формат чисел и дат в CSV.')
        bid=uuid.uuid4().hex
        with store.connect() as db:
            db.execute('INSERT INTO marketing_batches VALUES(?,?,?,?,?,?)',(bid,time.time(),user['id'],checksum,json.dumps(rows,ensure_ascii=False),'preview'))
            ev.record(db,'admin_import_preview',user['id'],data={'batch_id':bid,'rows':len(rows),'sha256':checksum})
        replacing=sum(store.one('SELECT COUNT(*) n FROM marketing_stats WHERE active=1 AND day=? AND platform=? AND account=? AND campaign_id=?',key)['n'] for key in {(r['date'],r['platform'],r['account_id'],r['campaign_id']) for r in rows})
        return {'id':bid,'status':'preview','replacing_active_rows':replacing,'rows':len(rows),'currencies':sorted({r['currency'] for r in rows}),'preview':rows[:10],'sha256':checksum}

    @app.post('/api/admin/marketing/imports/{bid}/confirm')
    async def confirm(bid:str,request:Request):
        user=owner(request,True)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');batch=db.execute('SELECT * FROM marketing_batches WHERE id=?',(bid,)).fetchone()
            if not batch:reject('NOT_FOUND','Импорт не найден.',404)
            if batch['status']=='confirmed':return {'ok':True,'replay':True}
            if batch['status']!='preview':reject('IMPORT_STATE','Импорт уже отменён.',409)
            rows=json.loads(batch['data'])
            for r in rows:
                db.execute('UPDATE marketing_stats SET active=0 WHERE active=1 AND day=? AND platform=? AND account=? AND campaign_id=?',(r['date'],r['platform'],r['account_id'],r['campaign_id']))
            for r in rows:
                db.execute('INSERT INTO marketing_stats VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,bid,r['date'],r['platform'],r['account_id'],r['campaign_id'],r['campaign_name'],r['creative_id'],r['impressions'],r['clicks'],r['spend'],r['currency'],r['tax_mode'],r['source_timezone'],1))
            db.execute("UPDATE marketing_batches SET status='confirmed' WHERE id=?",(bid,));ev.record(db,'admin_import_confirmed',user['id'],data={'batch_id':bid,'rows':len(rows)})
        return {'ok':True}

    @app.post('/api/admin/marketing/imports/{bid}/rollback')
    async def rollback(bid:str,request:Request):
        user=owner(request,True)
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE');batch=db.execute('SELECT * FROM marketing_batches WHERE id=?',(bid,)).fetchone()
            if not batch:reject('NOT_FOUND','Импорт не найден.',404)
            if batch['status']=='rolled_back':return {'ok':True,'replay':True}
            keys=db.execute('SELECT DISTINCT day,platform,account,campaign_id FROM marketing_stats WHERE batch_id=? AND active=1',(bid,)).fetchall()
            db.execute('UPDATE marketing_stats SET active=0 WHERE batch_id=?',(bid,));db.execute("UPDATE marketing_batches SET status='rolled_back' WHERE id=?",(bid,))
            for k in keys:
                prior=db.execute("SELECT s.batch_id FROM marketing_stats s JOIN marketing_batches b ON b.id=s.batch_id WHERE b.status='confirmed' AND s.day=? AND s.platform=? AND s.account=? AND s.campaign_id=? ORDER BY b.created DESC LIMIT 1",tuple(k)).fetchone()
                if prior:db.execute('UPDATE marketing_stats SET active=1 WHERE batch_id=? AND day=? AND platform=? AND account=? AND campaign_id=?',(prior[0],*tuple(k)))
            ev.record(db,'admin_import_rolled_back',user['id'],data={'batch_id':bid})
        return {'ok':True}

    @app.get('/api/admin/marketing/imports')
    async def batches(request:Request):
        owner(request);return {'items':store.all('SELECT id,created,status,sha256 FROM marketing_batches ORDER BY created DESC LIMIT 100')}

    @app.post('/api/admin/analytics/snapshots')
    async def snapshot(request:Request):
        user=owner(request,True)
        if os.getenv('ANALYTICS_EXPORT_ENABLED','1')=='0':reject('EXPORT_PAUSED','Подготовка срезов временно отключена.',503)
        body=await request.json()
        if not isinstance(body,dict) or not isinstance(body.get('filters',{}),dict):reject('FILTER_INVALID','Проверь фильтры среза.')
        data=await report(body.get('filters',{}))
        if len(data['practices'])>10000:reject('SNAPSHOT_LIMIT','В срез можно включить до 10 000 тренировок. Сократи период.',422)
        # Private owner export: pseudonymous entity IDs, no speech, names or email.
        data['methodology']={'version':ev.VERSION,'release':os.getenv('APP_RELEASE','local'),'activation_days':7,'practice_window_hours':data['filters']['window_hours'],'attribution_days':30,'ad_maturity_days':37,'dau_activity':'server-confirmed segment saved','report_view':'client observed; legacy GET excluded','deleted_evidence':'not recoverable','bot_identity':'not certified','pricing':'unknown currency; no estimated AI costs'}
        raw=json.dumps(data,ensure_ascii=False,sort_keys=True);sid=uuid.uuid4().hex;checksum=hashlib.sha256(raw.encode()).hexdigest()
        with store.connect() as db:
            db.execute('INSERT INTO analytics_snapshots VALUES(?,?,?,?,?,NULL)',(sid,time.time(),user['id'],raw,checksum))
            ev.record(db,'admin_snapshot_created',user['id'],data={'snapshot_id':sid,'sha256':checksum})
        return {'id':sid,'sha256':checksum,'as_of':data['as_of']}

    @app.get('/api/admin/analytics/snapshots/{sid}')
    async def export_snapshot(sid:str,request:Request,format:str='json'):
        user=owner(request)
        if os.getenv('ANALYTICS_EXPORT_ENABLED','1')=='0':reject('EXPORT_PAUSED','Выгрузка срезов временно отключена.',503)
        row=store.one('SELECT * FROM analytics_snapshots WHERE id=? AND revoked IS NULL',(sid,))
        if not row:reject('NOT_FOUND','Срез недоступен.',404)
        audit(store,user['id'],'admin_snapshot_export',{'snapshot_id':sid,'format':format})
        data=json.loads(row['data'])
        if format=='json':return data|{'snapshot_id':sid,'sha256':row['sha256']}
        if format=='csv':return Response(safe_csv(data['practices']),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="practices.csv"'})
        if format!='zip':reject('FORMAT_INVALID','Выбери json, csv или zip.')
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            files={'analytics.json':row['data'].encode(),'practices.csv':safe_csv(data['practices']).encode(),'accounts.csv':safe_csv(data['accounts']).encode(),'events-methodology.json':json.dumps(data['methodology'],ensure_ascii=False,indent=2).encode(),'summary.html':('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Аналитика конкурса</title><h1>Сцена без страха: срез использования</h1><p>UTC as_of: '+str(data['as_of'])+'</p><pre>'+__import__('html').escape(json.dumps(data['summary'],ensure_ascii=False,indent=2))+'</pre><p>Подробные данные и методика — в analytics.json. Это закрытый пакет с псевдонимами, не публичная выгрузка.</p></html>').encode()}
            manifest={'snapshot_id':sid,'as_of':data['as_of'],'sha256':row['sha256'],'files':{name:hashlib.sha256(content).hexdigest() for name,content in files.items()}}
            for name,content in files.items():archive.writestr(name,content)
            archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        return Response(output.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="contest-analytics.zip"'})
