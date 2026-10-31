"""Row pruning, release lookup and the idempotency timestamp migration."""

import json
import sqlite3
import time
from contextlib import closing

from fastapi.testclient import TestClient

from app import store
from app.main import app


def fresh(tmp_path):
    store.DB_FILE = tmp_path / 'maintenance.sqlite3'
    store.init()


def add_user(db, id_='u1'):
    db.execute(
        "INSERT INTO users(id,email,password_hash,display_name,created_at) VALUES(?,?,?,?,?)",
        (id_, id_ + '@example.com', 'x', 'name', '2026-01-01T00:00:00+08:00'),
    )


def test_prune_removes_only_unusable_rows(tmp_path):
    fresh(tmp_path)
    # 2026-10-30 12:30 Asia/Taipei; every timestamp below is relative to this fixed clock
    now = 1793334600
    with store.tx() as db:
        add_user(db)
        sessions = [
            ('live', 'h1', '2026-10-29T12:00:00+08:00', 0),
            ('old', 'h2', '2026-09-01T12:00:00+08:00', 0),
            ('revoked', 'h3', '2026-10-29T12:00:00+08:00', 1),
        ]
        for sid, token, created, revoked in sessions:
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)', (sid, 'u1', token, 'csrf', created, revoked))
        db.execute("INSERT INTO tokens VALUES('t-live','u1','RESET','2026-10-30T13:00:00+08:00')")
        db.execute("INSERT INTO tokens VALUES('t-old','u1','RESET','2026-10-30T11:00:00+08:00')")
        for key, created in (('fresh', now - 60), ('stale', now - 8 * 86400)):
            db.execute(
                'INSERT INTO idempotency(user_id,key,operation,request_hash,reply_json,created_at) VALUES(?,?,?,?,?,?)',
                ('u1', key, 'C01', 'hash', '{}', created),
            )
        removed = store.prune(db, now=now)
    assert removed == {'sessions': 2, 'tokens': 1, 'idempotency': 1}
    with closing(store.connect()) as db:
        assert [r['id'] for r in db.execute('SELECT id FROM sessions')] == ['live']
        assert [r['token_hash'] for r in db.execute('SELECT token_hash FROM tokens')] == ['t-live']
        assert [r['key'] for r in db.execute('SELECT key FROM idempotency')] == ['fresh']


def test_legacy_idempotency_rows_get_a_timestamp(tmp_path):
    store.DB_FILE = tmp_path / 'legacy.sqlite3'
    with closing(sqlite3.connect(store.DB_FILE)) as db, db:
        db.execute(
            'CREATE TABLE idempotency(user_id TEXT NOT NULL,key TEXT NOT NULL,operation TEXT NOT NULL,'
            'request_hash TEXT NOT NULL,reply_json TEXT NOT NULL,PRIMARY KEY(user_id,key,operation))'
        )
        db.execute("INSERT INTO idempotency VALUES('u','k','C01','h','{}')")
    before = time.time()
    store.init()
    with closing(store.connect()) as db:
        created = db.execute('SELECT created_at FROM idempotency').fetchone()['created_at']
        assert created >= before
        assert store.prune(db) == {'sessions': 0, 'tokens': 0, 'idempotency': 0}


def test_published_release_picks_newest_published(tmp_path):
    fresh(tmp_path)
    with store.tx() as db:
        assert store.published_release(db) is None
        for id_, status, created in (
            ('a', 'PUBLISHED', '2026-01-01T00:00:00+08:00'),
            ('b', 'PUBLISHED', '2026-03-01T00:00:00+08:00'),
            ('c', 'DRAFT', '2026-05-01T00:00:00+08:00'),
        ):
            body = {'id': id_, 'status': status, 'created_at': created, 'version': id_}
            db.execute('INSERT INTO admin_releases VALUES(?,?,?)', (id_, id_, json.dumps(body)))
        assert store.published_release(db)['id'] == 'b'


def test_app_lifespan_runs_pruning(tmp_path):
    fresh(tmp_path)
    with store.tx() as db:
        add_user(db)
        db.execute("INSERT INTO sessions VALUES('gone','u1','h','c','2026-01-01T00:00:00+08:00',1)")
    with TestClient(app):
        pass
    with closing(store.connect()) as db:
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
