"""Short SQLite transactions; private content never enters request logs."""
import json
import os
from contextlib import contextmanager
import sqlite3
import time
import uuid
from pathlib import Path


def uid():
    return uuid.uuid4().hex


def now():
    return time.time()


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directory, 0o700)
        self.media = self.directory / 'media'
        self.media.mkdir(exist_ok=True, mode=0o700)
        os.chmod(self.media, 0o700)
        self.path = self.directory / 'pilot.sqlite3'
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,onboarding_completed INTEGER NOT NULL DEFAULT 0,consent INTEGER NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS practices(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,config TEXT NOT NULL,created REAL NOT NULL,status TEXT NOT NULL DEFAULT 'draft',questions TEXT NOT NULL DEFAULT '[]',report TEXT);
                CREATE TABLE IF NOT EXISTS segments(id TEXT PRIMARY KEY,practice_id TEXT NOT NULL,kind TEXT NOT NULL,segment_index INTEGER NOT NULL,filename TEXT NOT NULL,duration REAL NOT NULL,transcript TEXT,created REAL NOT NULL,UNIQUE(practice_id,segment_index));
                CREATE TABLE IF NOT EXISTS segment_uploads(segment_id TEXT PRIMARY KEY,practice_id TEXT NOT NULL,client_key TEXT NOT NULL,sha256 TEXT NOT NULL,UNIQUE(practice_id,client_key));
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,practice_id TEXT NOT NULL,kind TEXT NOT NULL,status TEXT NOT NULL,stage TEXT NOT NULL,created REAL NOT NULL,started REAL,finished REAL,result TEXT,error TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(practice_id) WHERE status IN ('pending','running');
                CREATE TABLE IF NOT EXISTS usage(id TEXT PRIMARY KEY,job_id TEXT NOT NULL,user_id TEXT NOT NULL,created REAL NOT NULL,data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS ai_attempts(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,job_id TEXT NOT NULL,operation TEXT NOT NULL,created REAL NOT NULL,audio_seconds REAL NOT NULL,input_chars INTEGER NOT NULL,output_tokens INTEGER NOT NULL,status INTEGER,latency_ms REAL);
                CREATE INDEX IF NOT EXISTS ai_attempt_day ON ai_attempts(created,user_id);
                CREATE TABLE IF NOT EXISTS operational_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS live_sessions(practice_id TEXT NOT NULL,session_id TEXT NOT NULL,created REAL NOT NULL,segment_id TEXT,status TEXT NOT NULL DEFAULT 'open',expected_chunks INTEGER,PRIMARY KEY(practice_id,session_id));
                CREATE TABLE IF NOT EXISTS live_chunks(id TEXT PRIMARY KEY,practice_id TEXT NOT NULL,session_id TEXT NOT NULL,chunk_index INTEGER NOT NULL,offset_seconds REAL NOT NULL,duration REAL NOT NULL,filename TEXT NOT NULL,sha256 TEXT NOT NULL,status TEXT NOT NULL,transcript TEXT,error TEXT,created REAL NOT NULL,UNIQUE(practice_id,session_id,chunk_index));
                CREATE INDEX IF NOT EXISTS live_queue ON live_chunks(status,created);
                CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,user_id TEXT,practice_id TEXT,kind TEXT NOT NULL,created REAL NOT NULL,data TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,practice_id TEXT NOT NULL,rating INTEGER NOT NULL,text TEXT NOT NULL,created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS invites(token TEXT PRIMARY KEY,expires REAL NOT NULL,uses_left INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS resets(token TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS rate_limits(key TEXT NOT NULL,created REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS rate_key ON rate_limits(key,created);
                CREATE INDEX IF NOT EXISTS practices_owner ON practices(user_id,created);
                CREATE INDEX IF NOT EXISTS events_day ON events(created,kind);
            ''')
            if 'question_provenance' not in [row[1] for row in db.execute('PRAGMA table_info(practices)')]:
                db.execute('ALTER TABLE practices ADD COLUMN question_provenance TEXT')
            if 'expected_chunks' not in [row[1] for row in db.execute('PRAGMA table_info(live_sessions)')]:
                db.execute('ALTER TABLE live_sessions ADD COLUMN expected_chunks INTEGER')
            from .analytics_events import migrate
            migrate(db)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        try:
            with db:
                yield db
        finally:
            db.close()

    def one(self, sql, args=()):
        with self.connect() as db:
            row = db.execute(sql, args).fetchone()
            return dict(row) if row else None

    def all(self, sql, args=()):
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).rowcount

    def event(self, kind, user_id=None, practice_id=None, data=None, *, visitor=None, session=None):
        with self.connect() as db:
            db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)', (uid(), user_id, practice_id, kind, now(), json.dumps(data or {})))
            if kind in ('request','service_failure','login','logout'):
                from .analytics_events import record
                safe = {k:v for k,v in (data or {}).items() if k in ('request_id','route','method','status','latency_ms','error_code','code','job_id','operation')}
                record(db,kind,user_id,practice_id,safe,request_id=safe.get('request_id'),visitor=visitor,session=session)

    def limited(self, key, count, seconds):
        # Lock before reading so concurrent requests cannot overrun the bound.
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM rate_limits WHERE created<?', (now() - 86400,))
            found = db.execute('SELECT COUNT(*) FROM rate_limits WHERE key=? AND created>?', (key, now() - seconds)).fetchone()[0]
            if found >= count:
                return True
            db.execute('INSERT INTO rate_limits VALUES(?,?)', (key, now()))
            return False

    def usage(self, job, data):
        self.execute('INSERT INTO usage VALUES(?,?,?,?,?)', (uid(), job['id'], job['user_id'], now(), json.dumps(data)))

    def recover_jobs(self):
        self.execute("UPDATE jobs SET status='pending',stage='restart_recovery' WHERE status='running'")

    def recover_live_chunks(self):
        self.execute("UPDATE live_chunks SET status='pending' WHERE status='running'")

    def claim_live_chunk(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT c.*,p.user_id FROM live_chunks c JOIN practices p ON p.id=c.practice_id JOIN live_sessions s ON s.practice_id=c.practice_id AND s.session_id=c.session_id WHERE c.status='pending' AND s.status IN ('open','bound') ORDER BY c.created LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE live_chunks SET status='running' WHERE id=?", (row['id'],))
            return dict(row)

    def claim_job(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT j.*,p.user_id,p.config FROM jobs j JOIN practices p ON p.id=j.practice_id WHERE j.status='pending' ORDER BY j.created LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='running',started=?,stage='transcription' WHERE id=?", (now(), row['id']))
            return dict(row)
