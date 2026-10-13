"""Short, content-free aggregate retention and deletion-aware private snapshots."""
import hashlib
import json
import time
import uuid
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from .analytics_events import record


def delete_facts(db,practice):
    pid=practice['id'];saved=db.execute("SELECT COUNT(*) speech,COALESCE(SUM(duration),0) seconds FROM segments WHERE practice_id=? AND kind='speech'",(pid,)).fetchone()
    answers=db.execute("SELECT COUNT(*) FROM segments WHERE practice_id=? AND kind='answer'",(pid,)).fetchone()[0]
    report=db.execute("SELECT COUNT(*) FROM jobs WHERE practice_id=? AND kind='report' AND status='succeeded'",(pid,)).fetchone()[0]
    fid=uuid.uuid4().hex
    db.execute('INSERT INTO analytics_deleted_facts VALUES(?,?,?,?,?,?,?)',(fid,practice['created'],int(bool(saved['speech'])),answers,int(bool(report)),int(bool(json.loads(practice['config']).get('questions'))),time.time()))
    # No surviving trace ID/capture ID/account association can reconstruct deleted content.
    db.execute('DELETE FROM analytics_events WHERE practice_id=? OR correlation_id=?',(pid,pid))
    db.execute('DELETE FROM practice_attribution WHERE practice_id=?',(pid,))
    db.execute("UPDATE analytics_snapshots SET revoked=?,data='{}' WHERE revoked IS NULL AND EXISTS(SELECT 1 FROM json_each(analytics_snapshots.data,'$.practices') p WHERE json_extract(p.value,'$.id')=?)",(time.time(),pid))
    record(db,'practice_deleted',data={'anonymous_fact_id':fid,'speech_saved':bool(saved['speech']),'answers':answers,'report_available':bool(report)})


def rollup(store):
    zone=ZoneInfo('Europe/Moscow');moment=time.time()
    with store.connect() as db:
        days={datetime.fromtimestamp(r['occurred'],zone).date() for r in db.execute("SELECT DISTINCT occurred FROM analytics_events WHERE kind IN ('registration_confirmed','segment_saved','report_generated') AND occurred>=?",(moment-180*86400,))}
        # Reconcile late deliveries and prior business retention in one bounded transaction per day.
    for day in sorted(days):
        a=datetime.combine(day,datetime.min.time(),zone).timestamp();b=a+86400
        with store.connect() as db:
            watermark=db.execute('SELECT COALESCE(MAX(seq),0) FROM analytics_events WHERE occurred>=? AND occurred<?',(a,b)).fetchone()[0]
            old=db.execute('SELECT watermark FROM analytics_rollups WHERE day=?',(day.isoformat(),)).fetchone()
            if old and old[0]==watermark:continue
            values={r['kind']:r['count'] for r in db.execute("SELECT kind,COUNT(DISTINCT event_id) count FROM analytics_events WHERE occurred>=? AND occurred<? AND kind IN ('registration_confirmed','segment_saved','report_generated') GROUP BY kind",(a,b))}
            # Report refreshes are diagnostic, never additional completed practices.
            values['practices_with_report']=db.execute("SELECT COUNT(DISTINCT practice_id) FROM analytics_events WHERE kind='report_generated' AND occurred>=? AND occurred<?",(a,b)).fetchone()[0]
            db.execute('INSERT INTO analytics_rollups VALUES(?,?,?,?) ON CONFLICT(day) DO UPDATE SET calculated=excluded.calculated,watermark=excluded.watermark,data=excluded.data',(day.isoformat(),moment,watermark,json.dumps(values)))


def prune(db):
    moment=time.time()
    db.execute('DELETE FROM analytics_events WHERE received<?',(moment-180*86400,))
    # Stable visitor IDs are discarded after their last measured use; business attribution stays immutable.
    db.execute('DELETE FROM analytics_sessions WHERE last_activity<?',(moment-180*86400,))
    cutoff=(datetime.now(ZoneInfo('Europe/Moscow')).date()-timedelta(days=731)).isoformat()
    db.execute('DELETE FROM analytics_rollups WHERE day<?',(cutoff,))
    db.execute("UPDATE analytics_snapshots SET revoked=?,data='{}' WHERE created<? AND revoked IS NULL",(moment,moment-180*86400))
