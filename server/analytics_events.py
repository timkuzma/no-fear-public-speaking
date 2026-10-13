"""Durable, content-free milestones. SQL triggers share the business transaction."""
import contextvars
import hashlib
import json
import os
import re
import time
import uuid

REQUEST_ID = contextvars.ContextVar('analytics_request_id', default=None)
VERSION = 'contest-metrics-v1'
CLIENT_EVENTS = {
    'page_viewed', 'landing_cta_clicked', 'registration_viewed', 'registration_submitted',
    'registration_failed', 'setup_viewed', 'device_access_result', 'capture_started',
    'capture_stopped', 'capture_interrupted', 'draft_persist_result', 'segment_upload_started',
    'segment_upload_failed', 'question_presented', 'answer_started', 'answer_recorded',
    'report_viewed', 'report_engaged', 'media_play_started', 'report_export_requested',
    'media_download_requested', 'practice_resumed', 'reauthentication_needed',
}
STRING_FIELDS = {'route_id', 'cta_id', 'flow_id', 'capture_id', 'upload_attempt_id', 'page_view_id',
                 'device_kind', 'result', 'reason', 'error_code', 'job_id', 'segment_id', 'report_version_id'}
NUMBER_FIELDS = {'segment_index', 'question_index', 'elapsed_ms', 'visible_seconds', 'client_sequence'}
BOOLEAN_FIELDS = {'camera_enabled', 'invite_required', 'draft_available'}
ID_RE = re.compile(r'^[a-f0-9]{32}$')


def clean_data(data, strict=True):
    if not isinstance(data, dict):
        raise ValueError('data must be an object')
    result = {}
    for key, value in data.items():
        if key in ('flow_id','capture_id','upload_attempt_id','page_view_id','job_id','segment_id','report_version_id'):
            if not isinstance(value,str) or not ID_RE.fullmatch(value):raise ValueError('invalid identifier')
        if key=='route_id' and value not in ('/landing','/register','/login','/reset','/app','/history','/practice'):raise ValueError('invalid route')
        if key=='error_code' and (not isinstance(value,str) or not re.fullmatch('[A-Z0-9_]{2,60}',value)):raise ValueError('invalid code')
        if key=='device_kind' and value not in ('microphone','camera'):raise ValueError('invalid device')
        if key=='result' and value not in ('success','failed','interrupted','unknown','granted','denied','unavailable','saved'):raise ValueError('invalid result')
        if key=='cta_id' and value not in ('landing','landing-hero','landing-contexts','landing-method','landing-final'):raise ValueError('invalid CTA')
        if key in ('segment_index','question_index') and (type(value) is not int or not 0<=value<=3):raise ValueError('invalid stage')
        if key in STRING_FIELDS and isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_./:-]{0,100}', value):
            result[key] = value
        elif key in NUMBER_FIELDS and type(value) in (int, float) and 0 <= value <= 86400000:
            result[key] = value
        elif key in BOOLEAN_FIELDS and type(value) is bool:
            result[key] = value
        elif strict:
            raise ValueError('unsupported event field')
    return result


def record(db, kind, actor=None, practice=None, data=None, *, event_id=None, origin='server_confirmed',
           visitor=None, session=None, occurred=None, request_id=None):
    moment = time.time()
    event_id = event_id or uuid.uuid4().hex
    db.execute('''INSERT OR IGNORE INTO analytics_events
      (event_id,kind,origin,occurred,received,actor_id,practice_id,visitor_id,session_id,request_id,correlation_id,release,data)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (event_id, kind, origin, occurred or moment, moment, actor, practice, visitor, session,
       request_id or REQUEST_ID.get(), practice or session or actor or event_id,
       os.getenv('APP_RELEASE', 'local'), json.dumps(data or {}, ensure_ascii=False)))
    return event_id


def migrate(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS analytics_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS analytics_events(
      seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,
      origin TEXT NOT NULL,occurred REAL NOT NULL,received REAL NOT NULL,actor_id TEXT,practice_id TEXT,
      visitor_id TEXT,session_id TEXT,request_id TEXT,correlation_id TEXT,release TEXT NOT NULL DEFAULT 'unknown',data TEXT NOT NULL DEFAULT '{}');
    CREATE INDEX IF NOT EXISTS analytics_kind_time ON analytics_events(kind,occurred,actor_id);
    CREATE INDEX IF NOT EXISTS analytics_received ON analytics_events(received);
    CREATE INDEX IF NOT EXISTS analytics_time_kind ON analytics_events(occurred,kind);
    CREATE INDEX IF NOT EXISTS analytics_practice ON analytics_events(practice_id,seq);
    CREATE INDEX IF NOT EXISTS analytics_request ON analytics_events(request_id);
    CREATE INDEX IF NOT EXISTS analytics_job_ref ON analytics_events(json_extract(data,'$.job_id'));
    CREATE INDEX IF NOT EXISTS analytics_actor ON analytics_events(actor_id,occurred);
    CREATE INDEX IF NOT EXISTS analytics_trace ON analytics_events(correlation_id,seq);
    CREATE TABLE IF NOT EXISTS analytics_sessions(id TEXT PRIMARY KEY,visitor_id TEXT NOT NULL,actor_id TEXT,created REAL NOT NULL,last_activity REAL NOT NULL,entry_route TEXT NOT NULL,touch_id TEXT);
    CREATE INDEX IF NOT EXISTS analytics_visitor ON analytics_sessions(visitor_id,last_activity);
    CREATE TABLE IF NOT EXISTS acquisition_touches(id TEXT PRIMARY KEY,session_id TEXT NOT NULL UNIQUE,created REAL NOT NULL,source TEXT NOT NULL,medium TEXT NOT NULL,campaign TEXT NOT NULL,campaign_id TEXT NOT NULL,content TEXT NOT NULL,term TEXT NOT NULL,referrer_host TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS account_attribution(account_id TEXT PRIMARY KEY,touch_id TEXT,first_touch_id TEXT,model TEXT NOT NULL DEFAULT 'last-nondirect-30d-v1');
    CREATE TABLE IF NOT EXISTS practice_attribution(practice_id TEXT PRIMARY KEY,touch_id TEXT);
    CREATE TABLE IF NOT EXISTS admin_memberships(user_id TEXT PRIMARY KEY,created REAL NOT NULL,revoked REAL);
    CREATE TABLE IF NOT EXISTS account_classifications(user_id TEXT PRIMARY KEY,classification TEXT NOT NULL,updated REAL NOT NULL,actor_id TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS analytics_snapshots(id TEXT PRIMARY KEY,created REAL NOT NULL,actor_id TEXT NOT NULL,data TEXT NOT NULL,sha256 TEXT NOT NULL,revoked REAL);
    CREATE TABLE IF NOT EXISTS marketing_batches(id TEXT PRIMARY KEY,created REAL NOT NULL,actor_id TEXT NOT NULL,sha256 TEXT UNIQUE NOT NULL,data TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'preview');
    CREATE TABLE IF NOT EXISTS marketing_stats(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,day TEXT NOT NULL,platform TEXT NOT NULL,account TEXT NOT NULL,campaign_id TEXT NOT NULL,campaign_name TEXT NOT NULL,creative_id TEXT NOT NULL,impressions INTEGER NOT NULL,clicks INTEGER NOT NULL,spend TEXT NOT NULL,currency TEXT NOT NULL,tax_mode TEXT NOT NULL,timezone TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
    CREATE INDEX IF NOT EXISTS marketing_active ON marketing_stats(active,day,campaign_id);
    CREATE TABLE IF NOT EXISTS analytics_rollups(day TEXT PRIMARY KEY,calculated REAL NOT NULL,watermark INTEGER NOT NULL,data TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS analytics_deleted_facts(id TEXT PRIMARY KEY,created REAL NOT NULL,speech INTEGER NOT NULL,answers INTEGER NOT NULL,report INTEGER NOT NULL,questions INTEGER NOT NULL,deleted REAL NOT NULL);
    CREATE TRIGGER IF NOT EXISTS analytics_registration AFTER INSERT ON users BEGIN
      INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,correlation_id,request_id,release,data)
      VALUES('registration:'||NEW.id,'registration_confirmed','server_confirmed',NEW.created,NEW.created,NEW.id,NEW.id,NULL,'unknown','{}');
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_practice AFTER INSERT ON practices BEGIN
      INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,request_id,release,data)
      VALUES('practice:'||NEW.id,'practice_created','server_confirmed',NEW.created,NEW.created,NEW.user_id,NEW.id,NEW.id,NULL,'unknown',json_object('scenario',json_extract(NEW.config,'$.scenario'),'duration_seconds',json_extract(NEW.config,'$.duration')*60,'questions_enabled',json_extract(NEW.config,'$.questions'),'topic_present',length(coalesce(json_extract(NEW.config,'$.topic'),''))>0,'focus_present',json_extract(NEW.config,'$.repeat_focus') IS NOT NULL));
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_segment AFTER INSERT ON segments BEGIN
      INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,request_id,release,data)
      VALUES('segment:'||NEW.id,'segment_saved','server_confirmed',NEW.created,NEW.created,(SELECT user_id FROM practices WHERE id=NEW.practice_id),NEW.practice_id,NEW.practice_id,NULL,'unknown',json_object('segment_id',NEW.id,'segment_index',NEW.segment_index,'duration_seconds',NEW.duration,'kind',NEW.kind));
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_upload_binding AFTER INSERT ON segment_uploads BEGIN
      INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,request_id,release,data)
      VALUES('upload:'||NEW.segment_id,'segment_capture_bound','server_confirmed',(CAST(strftime('%s','now') AS REAL)+CAST(strftime('%f','now') AS REAL)-CAST(strftime('%S','now') AS REAL)),(CAST(strftime('%s','now') AS REAL)+CAST(strftime('%f','now') AS REAL)-CAST(strftime('%S','now') AS REAL)),(SELECT user_id FROM practices WHERE id=NEW.practice_id),NEW.practice_id,NEW.practice_id,NULL,'unknown',json_object('segment_id',NEW.segment_id,'capture_id',NEW.client_key));
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_job_created AFTER INSERT ON jobs BEGIN
      INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,request_id,release,data)
      VALUES('job:'||NEW.id,'job_requested','server_confirmed',NEW.created,NEW.created,(SELECT user_id FROM practices WHERE id=NEW.practice_id),NEW.practice_id,NEW.practice_id,NULL,'unknown',json_object('job_id',NEW.id,'kind',NEW.kind));
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_job_transition AFTER UPDATE OF status,stage ON jobs
      WHEN NEW.status<>OLD.status OR NEW.stage<>OLD.stage BEGIN
      INSERT INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,release,data)
      VALUES(lower(hex(randomblob(16))),'job_transition','server_confirmed',(CAST(strftime('%s','now') AS REAL)+CAST(strftime('%f','now') AS REAL)-CAST(strftime('%S','now') AS REAL)),(CAST(strftime('%s','now') AS REAL)+CAST(strftime('%f','now') AS REAL)-CAST(strftime('%S','now') AS REAL)),(SELECT user_id FROM practices WHERE id=NEW.practice_id),NEW.practice_id,NEW.practice_id,'unknown',json_object('job_id',NEW.id,'kind',NEW.kind,'from_status',OLD.status,'status',NEW.status,'from_stage',OLD.stage,'stage',NEW.stage,'error_code',json_extract(NEW.error,'$.code')));
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_job_result AFTER UPDATE OF status ON jobs
      WHEN NEW.status='succeeded' AND OLD.status<>'succeeded' BEGIN
      INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,release,data)
      VALUES('result:'||NEW.id,CASE WHEN NEW.kind='report' THEN 'report_generated' ELSE 'questions_generated' END,'server_confirmed',coalesce(NEW.finished,(CAST(strftime('%s','now') AS REAL)+CAST(strftime('%f','now') AS REAL)-CAST(strftime('%S','now') AS REAL))),(CAST(strftime('%s','now') AS REAL)+CAST(strftime('%f','now') AS REAL)-CAST(strftime('%S','now') AS REAL)),(SELECT user_id FROM practices WHERE id=NEW.practice_id),NEW.practice_id,NEW.practice_id,'unknown',json_object('job_id',NEW.id,'kind',NEW.kind,'prompt_version',json_extract(NEW.result,'$.provenance.report_prompt_version')));
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_rating AFTER INSERT ON feedback BEGIN
      INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,release,data)
      VALUES('feedback:'||NEW.id,'feedback_submitted','server_confirmed',NEW.created,NEW.created,NEW.user_id,NEW.practice_id,NEW.practice_id,'unknown',json_object('rating',NEW.rating,'report_version_id',(SELECT id FROM jobs WHERE practice_id=NEW.practice_id AND kind='report' AND status='succeeded' ORDER BY finished DESC,id DESC LIMIT 1)));
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_provider_start AFTER INSERT ON ai_attempts BEGIN
      INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,release,data)
      VALUES('attempt:'||NEW.id,'provider_attempt_started','server_confirmed',NEW.created,NEW.created,NEW.user_id,(SELECT practice_id FROM jobs WHERE id=NEW.job_id),coalesce((SELECT practice_id FROM jobs WHERE id=NEW.job_id),(SELECT practice_id FROM live_chunks WHERE id=NEW.job_id),NEW.job_id),'unknown',json_object('attempt_id',NEW.id,'job_id',NEW.job_id,'operation',NEW.operation));
    END;
    CREATE TRIGGER IF NOT EXISTS analytics_provider_result AFTER UPDATE OF status ON ai_attempts
      WHEN NEW.status IS NOT NULL AND (OLD.status IS NULL OR NEW.status<>OLD.status) BEGIN
      INSERT INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,release,data)
      VALUES(lower(hex(randomblob(16))),'provider_attempt_finished','server_confirmed',(CAST(strftime('%s','now') AS REAL)+CAST(strftime('%f','now') AS REAL)-CAST(strftime('%S','now') AS REAL)),(CAST(strftime('%s','now') AS REAL)+CAST(strftime('%f','now') AS REAL)-CAST(strftime('%S','now') AS REAL)),NEW.user_id,(SELECT practice_id FROM jobs WHERE id=NEW.job_id),coalesce((SELECT practice_id FROM jobs WHERE id=NEW.job_id),(SELECT practice_id FROM live_chunks WHERE id=NEW.job_id),NEW.job_id),'unknown',json_object('attempt_id',NEW.id,'job_id',NEW.job_id,'operation',NEW.operation,'http_status',NEW.status,'latency_ms',NEW.latency_ms));
    END;
    ''')
    db.execute("INSERT OR IGNORE INTO analytics_meta VALUES('measurement_started_at',?)", (str(time.time()),))
    db.executescript('CREATE INDEX IF NOT EXISTS analytics_jobs_practice ON jobs(practice_id,kind,status,finished); CREATE INDEX IF NOT EXISTS analytics_feedback_practice ON feedback(practice_id,created);')
    if db.execute("SELECT 1 FROM analytics_meta WHERE key='backfill_v1'").fetchone():
        return
    # Bounded, restartable backfill: each object owns its natural event key.
    for table, kind, prefix, actor, practice, date in [
        ('users','registration_confirmed','registration:', 'id','NULL','created'),
        ('practices','practice_created','practice:', 'user_id','id','created'),
        ('segments','segment_saved','segment:', '(SELECT user_id FROM practices WHERE id=practice_id)','practice_id','created')]:
        extra = "json_object('segment_id',id,'segment_index',segment_index,'kind',kind,'duration_seconds',duration)" if table == 'segments' else "'{}'"
        db.execute(f'''INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,release,data)
          SELECT ?||id,?,'reconstructed',{date},?,{actor},{practice},coalesce({practice},{actor}),'legacy',{extra} FROM {table}''', (prefix,kind,time.time()))
    db.execute('''INSERT OR IGNORE INTO analytics_events(event_id,kind,origin,occurred,received,actor_id,practice_id,correlation_id,release,data)
      SELECT 'result:'||j.id,CASE WHEN j.kind='report' THEN 'report_generated' ELSE 'questions_generated' END,'reconstructed',coalesce(j.finished,j.created),?,p.user_id,j.practice_id,j.practice_id,'legacy',json_object('job_id',j.id,'kind',j.kind)
      FROM jobs j JOIN practices p ON p.id=j.practice_id WHERE j.status='succeeded' ''', (time.time(),))
    db.execute("INSERT OR REPLACE INTO analytics_meta VALUES('schema_version','1')")
    db.execute("INSERT OR REPLACE INTO analytics_meta VALUES('backfill_v1',?)",(str(time.time()),))


def grant_owner(store, email):
    user = store.one('SELECT id FROM users WHERE lower(email)=?', (email.strip().lower(),))
    if not user:
        raise ValueError('account not found')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        # The approved deployment has exactly one owner, never an occupation-based grant.
        db.execute('UPDATE admin_memberships SET revoked=? WHERE revoked IS NULL', (time.time(),))
        db.execute('INSERT INTO admin_memberships VALUES(?,?,NULL) ON CONFLICT(user_id) DO UPDATE SET revoked=NULL', (user['id'],time.time()))
        record(db,'admin_owner_assigned',data={'exclusive_owner':True,'subject_id':user['id'],'issuer':'operator_cli'})
    return user['id']
