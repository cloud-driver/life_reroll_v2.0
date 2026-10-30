"""SQLite transaction boundary; all run commands commit one authoritative snapshot."""
from __future__ import annotations
import json
import os
import sqlite3
from contextlib import contextmanager,closing
from pathlib import Path

DB_FILE = Path(os.environ.get('LIFE_REPLAY_DB',str(Path(__file__).resolve().parents[1]/'game.sqlite3')))

def connect():
    DB_FILE.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DB_FILE,timeout=15,check_same_thread=False)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db

def init():
    with closing(connect()) as db, db:
        # WAL persists in the database; setting it per request needlessly locks
        # schema metadata. Keep FULL durability for authoritative game saves.
        db.execute('PRAGMA journal_mode=WAL')
        needs_run_index=not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_runs'").fetchone()
        db.executescript('''
        CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,verified INTEGER NOT NULL DEFAULT 0,role TEXT NOT NULL DEFAULT 'PLAYER',
            settings TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),
            token_hash TEXT NOT NULL UNIQUE, csrf TEXT NOT NULL, created_at TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tokens(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),purpose TEXT NOT NULL,expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS login_attempts(email_hash TEXT PRIMARY KEY,count INTEGER NOT NULL,first_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS campaigns(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),status TEXT NOT NULL,
            body TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS only_active_campaign ON campaigns(user_id) WHERE status != 'COMPLETED';
        CREATE INDEX IF NOT EXISTS campaigns_owner_created ON campaigns(user_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS campaign_runs(run_id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE);
        CREATE INDEX IF NOT EXISTS campaign_runs_campaign ON campaign_runs(campaign_id);
        CREATE TRIGGER IF NOT EXISTS campaign_runs_insert AFTER INSERT ON campaigns BEGIN
            INSERT INTO campaign_runs SELECT json_extract(value,'$.id'),NEW.id FROM json_each(NEW.body,'$.runs');
        END;
        CREATE TRIGGER IF NOT EXISTS campaign_runs_update AFTER UPDATE OF body ON campaigns
        WHEN json_extract(OLD.body,'$.runs[#-1].id') IS NOT json_extract(NEW.body,'$.runs[#-1].id') BEGIN
            DELETE FROM campaign_runs WHERE campaign_id=NEW.id;
            INSERT INTO campaign_runs SELECT json_extract(value,'$.id'),NEW.id FROM json_each(NEW.body,'$.runs');
        END;
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,type TEXT NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS idempotency(user_id TEXT NOT NULL,key TEXT NOT NULL,operation TEXT NOT NULL,
            request_hash TEXT NOT NULL,reply_json TEXT NOT NULL,PRIMARY KEY(user_id,key,operation));
        CREATE TABLE IF NOT EXISTS admin_assets(id TEXT PRIMARY KEY,kind TEXT NOT NULL,body TEXT NOT NULL,sha256 TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_releases(id TEXT PRIMARY KEY,version TEXT NOT NULL UNIQUE,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_audit(id TEXT PRIMARY KEY,actor_id TEXT NOT NULL,action TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS coach_jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,run_id TEXT NOT NULL,
            request_key TEXT NOT NULL,request_hash TEXT NOT NULL,context_key TEXT NOT NULL,created_at REAL NOT NULL,
            updated_at REAL NOT NULL,body TEXT NOT NULL,UNIQUE(owner,request_key));
        CREATE INDEX IF NOT EXISTS coach_active_status ON coach_jobs(json_extract(body,'$.status'),created_at);
        CREATE INDEX IF NOT EXISTS coach_owner_created ON coach_jobs(owner,created_at);
        CREATE INDEX IF NOT EXISTS coach_owner_context ON coach_jobs(owner,run_id,context_key,created_at);
        CREATE TABLE IF NOT EXISTS coach_requests(owner TEXT NOT NULL,key TEXT NOT NULL,request_hash TEXT NOT NULL,
            job_id TEXT NOT NULL REFERENCES coach_jobs(id) ON DELETE CASCADE,PRIMARY KEY(owner,key));
        CREATE TABLE IF NOT EXISTS insight_jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            run_id TEXT NOT NULL,context_key TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,body TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS insight_active_status ON insight_jobs(json_extract(body,'$.status'));
        CREATE INDEX IF NOT EXISTS insight_owner_context ON insight_jobs(owner,context_key,created_at);
        CREATE TABLE IF NOT EXISTS insight_requests(owner TEXT NOT NULL,key TEXT NOT NULL,request_hash TEXT NOT NULL,
            job_id TEXT NOT NULL REFERENCES insight_jobs(id) ON DELETE CASCADE,created_at REAL NOT NULL,PRIMARY KEY(owner,key));
        CREATE TABLE IF NOT EXISTS mail_deliveries(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL,status TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,instance_id TEXT NOT NULL,error_code TEXT);
        CREATE INDEX IF NOT EXISTS mail_user_created ON mail_deliveries(user_id,created_at);
        CREATE TABLE IF NOT EXISTS email_challenges(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,expires_at REAL NOT NULL,attempts INTEGER NOT NULL,sent_at REAL NOT NULL,delivery_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS legal_acceptances(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            terms_version TEXT NOT NULL,privacy_version TEXT NOT NULL,accepted_at TEXT NOT NULL);
        ''')
        if needs_run_index or not db.execute("SELECT 1 FROM schema_migrations WHERE name='run-index-v1'").fetchone():
            db.execute("INSERT OR IGNORE INTO campaign_runs SELECT json_extract(value,'$.id'),c.id FROM campaigns c,json_each(c.body,'$.runs')")
            db.execute("INSERT OR IGNORE INTO schema_migrations VALUES('run-index-v1')")
        if 'created_at' not in {row['name'] for row in db.execute('PRAGMA table_info(insight_requests)')}:
            db.execute('ALTER TABLE insight_requests ADD COLUMN created_at REAL NOT NULL DEFAULT 0')
        db.execute('CREATE INDEX IF NOT EXISTS insight_requests_owner_created ON insight_requests(owner,created_at)')
        from .training_service import init_schema
        init_schema(db)

@contextmanager
def tx(read_only=False):
    db=connect()
    try:
        db.execute('BEGIN' if read_only else 'BEGIN IMMEDIATE')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def j(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def get_campaign(db,id_,user=None):
    row=db.execute('SELECT * FROM campaigns WHERE id=?',(id_,)).fetchone()
    if not row or user is not None and row['user_id']!=user:return None
    return json.loads(row['body'])
def put_campaign(db,c):
    db.execute('UPDATE campaigns SET status=?,body=? WHERE id=?',(c['status'],j(c),c['id']))
def list_campaigns(db,user):
    return [json.loads(x['body']) for x in db.execute('SELECT body FROM campaigns WHERE user_id=? ORDER BY created_at DESC',(user,))]
def active_campaign(db,user):
    row=db.execute("SELECT body FROM campaigns WHERE user_id=? AND status!='COMPLETED'",(user,)).fetchone()
    return json.loads(row['body']) if row else None
def find_run(db,run_id,user):
    row=db.execute('''SELECT c.body FROM campaign_runs r JOIN campaigns c ON c.id=r.campaign_id
                      WHERE r.run_id=? AND c.user_id=?''',(run_id,user)).fetchone()
    if row:
        c=json.loads(row['body'])
        for r in c['runs']:
            if r['id']==run_id:return c,r
    return None,None
