"""Exact entity-level calculations; absence of client history is never a zero success."""
import json
import statistics
import time
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from .analytics_events import VERSION

ZONE=ZoneInfo('Europe/Moscow')


def period(query):
    end=(datetime.now(ZONE).date()+timedelta(days=1)).isoformat()
    start=(datetime.now(ZONE).date()-timedelta(days=29)).isoformat()
    a=datetime.combine(date.fromisoformat(query.get('from',start)),datetime.min.time(),ZONE)
    b=datetime.combine(date.fromisoformat(query.get('to',end)),datetime.min.time(),ZONE)
    if a.hour or b.hour or not 0<(b-a).total_seconds()<=366*86400:
        raise ValueError('Выбери период от 1 до 366 дней.')
    return a.timestamp(),b.timestamp()


def filters(query):
    result={k:query.get(k,'') for k in ('source','campaign','scenario','questions','duration','classification','mode','actor_id','role','report_version','source_model')}
    if result['scenario'] not in ('','speech','defense','free') or result['questions'] not in ('','true','false') or result['mode'] not in ('','events','cohort') or result['duration'] not in ('','short','medium','long','extended'):
        raise ValueError('Недопустимый фильтр.')
    if result['source_model'] not in ('','last','first'):raise ValueError('Invalid attribution model')
    result['source_model']=result['source_model'] or 'last'
    result['mode']=result['mode'] or 'cohort'
    result['include_staff']=query.get('include_staff')=='true'
    result['window_hours']=int(query.get('window_hours','24'))
    if result['window_hours'] not in (24,72,168):raise ValueError('Недопустимое окно завершения.')
    return result


def base_rows(db,source_model="last"):
    return db.execute("""WITH saved AS (
      SELECT practice_id,MIN(CASE WHEN kind='speech' THEN created END) speech_at,
      SUM(duration) seconds,SUM(kind='answer') answers,
      MAX(kind='answer' AND segment_index=1) answer_1,MAX(kind='answer' AND segment_index=2) answer_2,MAX(kind='answer' AND segment_index=3) answer_3,MAX(CASE WHEN kind='answer' THEN created END) last_answer_at
      FROM segments GROUP BY practice_id
    ), outcome AS (
      SELECT practice_id,MIN(CASE WHEN kind='report' AND status='succeeded' THEN finished END) report_at,
      MIN(CASE WHEN kind='questions' AND status='succeeded' THEN finished END) questions_at,
      SUM(status='failed') failures FROM jobs GROUP BY practice_id
    ), report_version AS (
      SELECT practice_id,id,coalesce(json_extract(result,'$.provenance.report_prompt_version'),'legacy') prompt_version,ROW_NUMBER() OVER(PARTITION BY practice_id ORDER BY finished DESC,id DESC) rn
      FROM jobs WHERE kind='report' AND status='succeeded'
    ), ratings AS (
      SELECT practice_id,rating,ROW_NUMBER() OVER(PARTITION BY practice_id ORDER BY created DESC,id DESC) rn FROM feedback
    ) SELECT p.id,p.user_id,p.created,p.status,p.config,s.speech_at,coalesce(s.seconds,0) seconds,
      coalesce(s.answers,0) answers,coalesce(s.answer_1,0) answer_1,coalesce(s.answer_2,0) answer_2,coalesce(s.answer_3,0) answer_3,s.last_answer_at,j.report_at,rv.id report_version_id,rv.prompt_version,j.questions_at,
      coalesce(j.failures,0) failures,r.rating,coalesce(c.classification,'participant') classification,
      coalesce(t.source,'unknown') source,coalesce(t.campaign_id,t.campaign,'') campaign,
      u.created registered_at,u.role
      FROM practices p JOIN users u ON u.id=p.user_id
      LEFT JOIN saved s ON s.practice_id=p.id LEFT JOIN outcome j ON j.practice_id=p.id
      LEFT JOIN report_version rv ON rv.practice_id=p.id AND rv.rn=1
      LEFT JOIN ratings r ON r.practice_id=p.id AND r.rn=1
      LEFT JOIN account_classifications c ON c.user_id=p.user_id
      LEFT JOIN account_attribution a ON a.account_id=p.user_id
      LEFT JOIN acquisition_touches t ON t.id=CASE WHEN ?='first' THEN a.first_touch_id ELSE a.touch_id END""",(source_model,)).fetchall()


def accepted(row,f):
    if not f['include_staff'] and row['classification'] in ('staff','test'):return False
    if f['actor_id'] and row['user_id']!=f['actor_id']:return False
    if f['role'] and row['role']!=f['role']:return False
    if f['report_version'] and row['prompt_version']!=f['report_version']:return False
    config=json.loads(row['config'])
    if f['scenario'] and config.get('scenario')!=f['scenario']:return False
    if f['questions'] and bool(config.get('questions'))!=(f['questions']=='true'):return False
    if f['source'] and row['source']!=f['source']:return False
    if f['campaign'] and row['campaign']!=f['campaign']:return False
    if f['classification'] and row['classification']!=f['classification']:return False
    duration=float(config.get('duration',0))*60
    low,high={'short':(0,60),'medium':(60,180),'long':(180,300),'extended':(300,600)}.get(f['duration'],(-1,999999))
    return low<duration<=high


def public_row(row):
    c=json.loads(row['config']);complete=bool(row['report_at'] and row['speech_at'] and (not c.get('questions') or row['answers']>=3))
    return {k:row[k] for k in ('id','user_id','created','status','speech_at','seconds','answers','answer_1','answer_2','answer_3','last_answer_at','report_at','report_version_id','questions_at','failures','rating','classification','source','campaign','registered_at','role','prompt_version')}|{
        'participant':'Участник '+row['user_id'][:8],'scenario':c.get('scenario','speech'),
        'duration_seconds':float(c.get('duration',0))*60,'questions':bool(c.get('questions')),
        'topic_present':bool(c.get('topic')),'focus_present':bool(c.get('repeat_focus')),
        'parent_practice_id':(c.get('repeat_focus') or {}).get('source_practice_id'),
        'complete':complete,'completion_at':max(row['report_at'] or 0,row['last_answer_at'] or 0,row['speech_at'] or 0) if complete else None}


def fraction(n,d):return {'numerator':n,'denominator':d,'value':round(n/d*100,2) if d else None}


def percentile(values,p):
    if not values:return None
    values=sorted(values);position=(len(values)-1)*p;lower=int(position);upper=min(lower+1,len(values)-1)
    return values[lower]+(values[upper]-values[lower])*(position-lower)


def calculate(db,query):
    start,end=period(query);f=filters(query);moment=time.time()
    db.execute('PRAGMA query_only=ON')
    rows=[public_row(r) for r in base_rows(db,f['source_model']) if accepted(r,f)]
    activity_ids={r[0] for r in db.execute("SELECT DISTINCT practice_id FROM analytics_events WHERE occurred>=? AND occurred<? AND kind IN ('segment_saved','capture_started','report_viewed','report_generated') AND practice_id IS NOT NULL",(start,end))}
    selected=[r for r in rows if start<=r['created']<end or (f['mode']=='events' and r['id'] in activity_ids)]
    uidset={r['user_id'] for r in rows}
    accounts=[dict(r) for r in db.execute('''SELECT u.id,u.created,u.role,coalesce(c.classification,'participant') classification,
      coalesce(t.source,'unknown') source,coalesce(t.campaign_id,t.campaign,'') campaign
      FROM users u LEFT JOIN account_classifications c ON c.user_id=u.id
      LEFT JOIN account_attribution a ON a.account_id=u.id LEFT JOIN acquisition_touches t ON t.id=CASE WHEN ?='first' THEN a.first_touch_id ELSE a.touch_id END''',(f['source_model'],))]
    accounts=[a for a in accounts if (f['include_staff'] or a['classification'] not in ('staff','test')) and (not f['source'] or a['source']==f['source']) and (not f['campaign'] or a['campaign']==f['campaign']) and (not f['actor_id'] or a['id']==f['actor_id']) and (not f['role'] or a['role']==f['role']) and (not f['classification'] or a['classification']==f['classification']) and (not(f['scenario'] or f['questions'] or f['duration'] or f['report_version']) or a['id'] in uidset)]
    new=[a for a in accounts if start<=a['created']<end]
    first_report={};first_speech={};speeches={}
    for r in rows:
        if r['report_at']:first_report[r['user_id']]=min(first_report.get(r['user_id'],float('inf')),r['report_at'])
        if r['speech_at']:
            first_speech[r['user_id']]=min(first_speech.get(r['user_id'],float('inf')),r['speech_at'])
            speeches.setdefault(r['user_id'],[]).append(r['speech_at'])
    mature=[a for a in new if a['created']+7*86400<=moment]
    activated=[a['id'] for a in mature if a['id'] in first_report and 0<=first_report[a['id']]-a['created']<=7*86400]
    generated=[r for r in selected if r['report_at']]
    window=f['window_hours']*3600
    matured=[r for r in selected if r['created']+window<=moment]
    timely=[r for r in matured if r['completion_at'] and r['completion_at']-r['created']<=window]
    event_clauses=["kind IN ('page_viewed','registration_viewed','registration_confirmed','capture_started','report_viewed','report_engaged','question_presented','segment_saved','landing_cta_clicked','registration_submitted','registration_failed','setup_viewed')",'occurred>=?','occurred<?'];event_args=[start,end]
    if not f['include_staff']:event_clauses.append("(actor_id IS NULL OR actor_id NOT IN (SELECT user_id FROM account_classifications WHERE classification IN ('staff','test')))")
    events=[dict(e) for e in db.execute('SELECT * FROM analytics_events WHERE '+' AND '.join(event_clauses),event_args)]
    sessions={e['session_id'] for e in events if e['kind']=='page_viewed' and e['session_id']}
    if f['source'] or f['campaign']:
        touch_sessions={r['session_id'] for r in db.execute('SELECT * FROM acquisition_touches') if (not f['source'] or r['source']==f['source']) and (not f['campaign'] or r['campaign_id']==f['campaign'])}
        sessions &=touch_sessions;events=[e for e in events if e['session_id'] in touch_sessions or e['actor_id'] in {a['id'] for a in accounts}]
    if any(f[k] for k in ('actor_id','role','scenario','questions','duration','report_version','classification')):
        account_ids={a['id'] for a in accounts}
        events=[e for e in events if e['actor_id'] in account_ids]
        sessions={e['session_id'] for e in events if e['kind']=='page_viewed' and e['session_id']}
    registration_sessions={e['session_id'] for e in events if e['kind']=='registration_viewed' and e['session_id']}
    reg_views={}
    for e in events:
        if e['kind']=='registration_viewed' and e['session_id']:reg_views[e['session_id']]=min(reg_views.get(e['session_id'],float('inf')),e['occurred'])
    mature_views={sid:at for sid,at in reg_views.items() if at+7*86400<=moment}
    confirmed=[dict(e) for e in db.execute("SELECT session_id,actor_id,occurred FROM analytics_events WHERE kind='registration_confirmed' AND occurred>=? AND occurred<?",(start,end+7*86400))]
    reg_converted={e['actor_id'] for e in confirmed if e['session_id'] in mature_views and 0<=e['occurred']-mature_views[e['session_id']]<=7*86400}
    observed_reg={e['actor_id'] for e in confirmed if e['session_id'] in reg_views and 0<=e['occurred']-reg_views[e['session_id']]<=7*86400}
    # Report views count only browser-observed rendering, never legacy GETs.
    selected_ids={r['id'] for r in selected}
    phase_events=[dict(e) for e in db.execute("SELECT kind,practice_id,data FROM analytics_events WHERE kind IN ('capture_started','report_viewed','report_engaged','question_presented','answer_started','answer_recorded') AND occurred>=? AND occurred<=?",(start,moment))] if f['mode']=='cohort' else [dict(e) for e in db.execute("SELECT kind,practice_id,data FROM analytics_events WHERE kind IN ('capture_started','report_viewed','report_engaged','question_presented','answer_started','answer_recorded') AND occurred>=? AND occurred<?",(start,end))]
    observed={kind:{e['practice_id'] for e in phase_events if e['kind']==kind and e['practice_id'] in selected_ids} for kind in ('capture_started','report_viewed','report_engaged','question_presented','answer_started','answer_recorded')}
    observed['capture_started']={e['practice_id'] for e in phase_events if e['kind']=='capture_started' and e['practice_id'] in selected_ids and json.loads(e['data']).get('segment_index')==0}
    question_rows=[r for r in selected if r['questions'] and r['speech_at']]
    question_ids={r['id'] for r in question_rows}
    memberships={'practice_created':selected_ids,'speech_saved':{r['id'] for r in selected if r['speech_at']},
      'questions_generated':{r['id'] for r in question_rows if r['questions_at']},
      'inputs_saved':{r['id'] for r in selected if r['speech_at'] and (not r['questions'] or r['answers']==3)},
      'report_generated':{r['id'] for r in generated},'feedback_submitted':{r['id'] for r in selected if r['rating'] is not None}}
    memberships.update(observed)
    questions=[]
    for i in (1,2,3):
        cell={'index':i,'base':len(question_rows),'ready':len(memberships['questions_generated'])}
        for kind,key in (('question_presented','presented'),('answer_started','started'),('answer_recorded','recorded')):
            ids={e['practice_id'] for e in phase_events if e['practice_id'] in question_ids and e['kind']==kind and json.loads(e['data']).get('question_index')==i}
            memberships[kind+'_'+str(i)]=ids;cell[key]=len(ids)
        ids={r['id'] for r in question_rows if r['answer_'+str(i)]}
        memberships['answer_saved_'+str(i)]=ids;cell['saved']=len(ids);cell['conversion']=fraction(len(ids),len(question_rows));questions.append(cell)
    steps=[('practice_created','Тренировка создана',len(selected),False),('capture_started','Запись началась',None,True),
      ('speech_saved','Речь сохранена',len(selected),False),('questions_generated','Вопросы готовы',len(question_rows),False)]
    for i in (1,2,3):
        steps.extend([(f'question_presented_{i}',f'Вопрос {i} показан',len(question_rows),True),
          (f'answer_started_{i}',f'Ответ {i} начат',len(question_rows),True),(f'answer_recorded_{i}',f'Ответ {i} записан локально',len(question_rows),True),
          (f'answer_saved_{i}',f'Ответ {i} сохранён',len(question_rows),False)])
    steps.extend([('inputs_saved','Все обязательные записи сохранены',len(selected),False),('report_generated','Разбор готов',len(memberships['inputs_saved']),False),
      ('report_viewed','Разбор показан',len(generated),True),('report_engaged','Просмотр ≥10 секунд',len(generated),True),('feedback_submitted','Оценка сохранена',len(generated),False)])
    funnel=[{'id':k,'label':label,'count':len(memberships[k]),'from_base':fraction(len(memberships[k]),len(selected)),
      'from_previous':fraction(len(memberships[k]),base) if base is not None else None,'origin':'client_observed' if client else 'server_confirmed'} for k,label,base,client in steps]
    landing_sessions={e['session_id'] for e in events if e['kind']=='page_viewed' and json.loads(e['data']).get('route_id')=='/landing' and e['session_id']}
    cta_sessions={e['session_id'] for e in events if e['kind']=='landing_cta_clicked' and e['session_id']} & landing_sessions
    submit_sessions={e['session_id'] for e in events if e['kind']=='registration_submitted' and e['session_id']} & registration_sessions
    acquisition={'landing_visits':len(landing_sessions),'cta_visits':len(cta_sessions),'cta_conversion':fraction(len(cta_sessions),len(landing_sessions)),
      'form_visits':len(registration_sessions),'direct_form_visits':len(registration_sessions-landing_sessions),'submitted_visits':len(submit_sessions),
      'submission_conversion':fraction(len(submit_sessions),len(registration_sessions)),
      'registration_errors':{code:sum(e['kind']=='registration_failed' and json.loads(e['data']).get('error_code')==code for e in events) for code in sorted({json.loads(e['data']).get('error_code','UNKNOWN') for e in events if e['kind']=='registration_failed'})}}
    intervals={'speech_saved':[], 'questions_ready':[], 'report_ready':[]}
    negative_intervals=0
    for r in selected:
        for key,a,b in (('speech_saved',r['created'],r['speech_at']),('questions_ready',r['speech_at'],r['questions_at']),
          ('report_ready',max(r['speech_at'] or 0,r.get('last_answer_at') or 0),r['report_at'])):
            if not a or not b:continue
            if b<a:negative_intervals+=1;continue
            intervals[key].append(b-a)
    timings={k:{'count':len(v),'p50_seconds':percentile(v,.5),'p90_seconds':percentile(v,.9)} for k,v in intervals.items()}
    unfinished={k:0 for k in ('no_speech','awaiting_questions','answering','awaiting_report','processing_failed')}
    for r in selected:
        if r['complete']:continue
        key='no_speech' if not r['speech_at'] else 'processing_failed' if r['failures'] else 'awaiting_questions' if r['questions'] and not r['questions_at'] else 'answering' if r['questions'] and r['answers']<3 else 'awaiting_report'
        unfinished[key]+=1
    no_questions=[r for r in selected if not r['questions'] and r['speech_at']]
    trend={}
    cursor=datetime.fromtimestamp(start,ZONE).date();last=datetime.fromtimestamp(end,ZONE).date()
    while cursor<last:
        trend[cursor.isoformat()]={'day':cursor.isoformat(),'registrations':0,'speeches':0,'reports':0,'active_accounts':set()};cursor+=timedelta(days=1)
    for a in new:trend[datetime.fromtimestamp(a['created'],ZONE).date().isoformat()]['registrations']+=1
    for r in rows:
        for at,key in ((r['speech_at'],'speeches'),(r['report_at'],'reports')):
            if at and start<=at<end:
                item=trend[datetime.fromtimestamp(at,ZONE).date().isoformat()];item[key]+=1
                if key=='speeches':item['active_accounts'].add(r['user_id'])
    trend=[{**v,'active_accounts':len(v['active_accounts'])} for v in trend.values()]
    retention=[]
    for week in sorted({(datetime.fromtimestamp(at,ZONE).date()-timedelta(days=datetime.fromtimestamp(at,ZONE).weekday())).isoformat() for at in first_speech.values() if start<=at<end}):
        cohort=[u for u,at in first_speech.items() if (datetime.fromtimestamp(at,ZONE).date()-timedelta(days=datetime.fromtimestamp(at,ZONE).weekday())).isoformat()==week and start<=at<end]
        cell={'week':week,'accounts':len(cohort)}
        for day in (1,7,30):
            mature_ids=[u for u in cohort if datetime.fromtimestamp(first_speech[u],ZONE).date()+timedelta(days=day+1)<=datetime.fromtimestamp(moment,ZONE).date()]
            kept=[u for u in mature_ids if any(datetime.fromtimestamp(at,ZONE).date()==datetime.fromtimestamp(first_speech[u],ZONE).date()+timedelta(days=day) for at in speeches[u])]
            cell['d'+str(day)]=fraction(len(kept),len(mature_ids))|{'pending':len(cohort)-len(mature_ids)}
        retention.append(cell)
    repeats={}
    for days in (7,30):
        base=[u for u,at in first_report.items() if start<=at<end and at+days*86400<=moment]
        kept=[u for u in base if any(first_report[u]<at<=first_report[u]+days*86400 for at in speeches.get(u,[]))]
        repeats[str(days)]=fraction(len(kept),len(base))|{'members':kept}
    ratings=[r['rating'] for r in selected if r['rating'] is not None]
    active={e['actor_id'] for e in events if e['kind']=='segment_saved' and e['actor_id'] in {a['id'] for a in accounts}}
    dau={n:db.execute('''SELECT COUNT(DISTINCT actor_id) FROM analytics_events WHERE kind='segment_saved' AND occurred>=? AND occurred<? AND actor_id IS NOT NULL AND (? OR actor_id NOT IN(SELECT user_id FROM account_classifications WHERE classification IN ('staff','test')))''',(moment-n*86400,moment,int(f['include_staff']))).fetchone()[0] for n in (1,7,30)}
    quality={'measurement_started_at':float(db.execute("SELECT value FROM analytics_meta WHERE key='measurement_started_at'").fetchone()[0]),'legacy_gets_are_not_views':True,
      'unknown_attribution':sum(a['source']=='unknown' for a in new),'registration_base':len(new),
      'reconstructed_events':sum(e['origin']=='reconstructed' for e in events),
      'latest_received':db.execute('SELECT MAX(received) FROM analytics_events').fetchone()[0],
      'client_late_events':sum(e['origin']=='client_observed' and abs(e['received']-e['occurred'])>60 for e in events),
      'schema_version':1,'historical_client_events_available':False}
    # One entity set drives all summary/detail/export values.
    return {'metric_definition_version':VERSION,'attribution_version':'first-observed-touch-v1' if f['source_model']=='first' else 'last-nondirect-30d-v1','timezone':'Europe/Moscow','period':{'from':start,'to':end},'filters':f,'as_of':moment,
      'source_watermark':db.execute('SELECT coalesce(MAX(seq),0) FROM analytics_events').fetchone()[0], 'coverage':quality,
      'summary':{'registrations':len(new),'practices':len(selected),'speeches':sum(bool(r['speech_at']) for r in selected),'reports':len(generated),'completed':sum(r['complete'] for r in selected),'active_accounts':len(active),'visits':len(sessions),'visitors':len({e['visitor_id'] for e in events if e['kind']=='page_viewed' and e['visitor_id']}),'dau':dau[1],'wau':dau[7],'mau':dau[30],
      'activation_7d':fraction(len(activated),len(mature))|{'pending':len(new)-len(mature),'members':activated},'completion':fraction(len(timely),len(matured))|{'pending':len(selected)-len(matured)},'registration_conversion':fraction(len(reg_converted),len(mature_views))|{'pending':len(reg_views)-len(mature_views)},'registration_observed':fraction(len(observed_reg),len(reg_views)),
      'seconds':sum(r['seconds'] for r in selected),'rating_average':statistics.mean(ratings) if ratings else None,'rating_count':len(ratings),'rating_distribution':{str(n):ratings.count(n) for n in range(1,6)},'time_to_value_p50':percentile([first_report[a['id']]-a['created'] for a in new if a['id'] in first_report and first_report[a['id']]>=a['created']],.5),'time_to_value_p90':percentile([first_report[a['id']]-a['created'] for a in new if a['id'] in first_report and first_report[a['id']]>=a['created']],.9)},
      'observed_memberships':{k:sorted(v) for k,v in memberships.items()},'acquisition':acquisition,'timings':timings,'unfinished':unfinished,'negative_intervals':negative_intervals,'funnel':funnel,'questions':questions,'no_questions':{'base':len(no_questions),'reports':sum(bool(r['report_at']) for r in no_questions)},'trend':trend,'retention':retention,'repeats':repeats,'practices':selected,'accounts':new,'account_roster':accounts,'active_account_ids':sorted(active)}
