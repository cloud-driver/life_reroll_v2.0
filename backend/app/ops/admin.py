"""Content administration and releases (H*)."""

from __future__ import annotations

import hashlib
import json
import sqlite3

from .. import store, engine, content
from .common import fail, require, page


def admin(op, db, b, u, p, q):
    if op == 'H09':
        return 200, {'accepted': True, 'message': 'alive'}
    if op == 'H10':
        db.execute('SELECT 1').fetchone()
        return 200, {'accepted': True, 'message': 'database ready'}
    require(u, 'UNAUTHENTICATED')
    require(u['role'] == 'CONTENT_ADMIN', 'FORBIDDEN')
    if op == 'H01':
        kind = b.get('kind')
        raw = b.get('content_json', '')
        require(
            kind in ('PERSONAS', 'EVENTS', 'PRODUCTS', 'RULESET')
            and isinstance(raw, str)
            and len(raw.encode()) < 2 * 1024 * 1024,
            'CONTENT_INVALID',
        )
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            fail('CONTENT_INVALID')
        require(isinstance(parsed, (dict, list)), 'CONTENT_INVALID')
        entry = {
            'id': engine.uid(),
            'kind': kind,
            'sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'validation_errors': [],
        }
        db.execute('INSERT INTO admin_assets VALUES(?,?,?,?)', (entry['id'], kind, raw, entry['sha256']))
        db.execute(
            'INSERT INTO admin_audit VALUES(?,?,?,?)',
            (engine.uid(), u['id'], f'ASSET_UPLOAD:{entry["id"]}', engine.now()),
        )
        return 201, entry
    if op == 'H02':
        version = b.get('version')
        require(isinstance(version, str) and 1 <= len(version) <= 60, 'CONTENT_INVALID')
        assets = {}
        for field, kind in (
            ('persona_asset_id', 'PERSONAS'),
            ('event_asset_id', 'EVENTS'),
            ('product_asset_id', 'PRODUCTS'),
            ('ruleset_asset_id', 'RULESET'),
        ):
            x = db.execute('SELECT * FROM admin_assets WHERE id=?', (b.get(field),)).fetchone()
            require(x and x['kind'] == kind, 'CONTENT_INVALID')
            assets[field] = x['id']
        release = {
            'id': engine.uid(),
            'version': version,
            'status': 'DRAFT',
            'assets': assets,
            'validation_errors': [],
            'persona_count': 0,
            'stock_count': 5,
            'product_count': 0,
            'created_at': engine.now(),
        }
        try:
            db.execute('INSERT INTO admin_releases VALUES(?,?,?)', (release['id'], version, store.j(release)))
        except sqlite3.IntegrityError:
            fail('VERSION_EXISTS')
        db.execute(
            'INSERT INTO admin_audit VALUES(?,?,?,?)', (engine.uid(), u['id'], f'RELEASE_DRAFT:{version}', engine.now())
        )
        return 201, release
    if op == 'H03':
        return 200, page(
            [json.loads(x['body']) for x in db.execute('SELECT body FROM admin_releases ORDER BY version DESC')]
        )
    if op == 'H07':
        return 200, page(
            [
                json.loads(x['body'])
                for x in db.execute('SELECT body FROM jobs')
                if (not q.get('status') or json.loads(x['body'])['status'] == q['status'])
                and (not q.get('type') or json.loads(x['body'])['type'] == q['type'])
            ]
        )
    if op == 'H08':
        return 200, page(
            [
                dict(x)
                for x in db.execute('SELECT id,actor_id,action,created_at FROM admin_audit ORDER BY created_at DESC')
                if (not q.get('from_date') or x['created_at'][:10] >= q['from_date'])
                and (not q.get('to_date') or x['created_at'][:10] <= q['to_date'])
            ]
        )
    row = db.execute('SELECT * FROM admin_releases WHERE id=?', (p['release_id'],)).fetchone()
    require(row, 'NOT_FOUND')
    release = json.loads(row['body'])
    if op == 'H04':
        return 200, release
    if op == 'H05':
        require(release['status'] in ('DRAFT', 'VALIDATED'), 'STATE_CONFLICT')
        datasets = {}
        for field, key in (
            ('persona_asset_id', 'PERSONAS'),
            ('event_asset_id', 'EVENTS'),
            ('product_asset_id', 'PRODUCTS'),
            ('ruleset_asset_id', 'RULESET'),
        ):
            raw = db.execute('SELECT body FROM admin_assets WHERE id=?', (release['assets'][field],)).fetchone()
            datasets[key] = json.loads(raw['body'])
        errors = []
        if (
            not isinstance(datasets['PERSONAS'], list)
            or not datasets['PERSONAS']
            or any(
                not isinstance(x, dict)
                or not {'id', 'occupation', 'industry', 'annual_income_minor', 'commute_mode', 'family_history'}
                <= x.keys()
                or x['annual_income_minor'] <= 0
                for x in datasets['PERSONAS']
            )
        ):
            errors.append('人設欄位無效')
        if (
            not isinstance(datasets['EVENTS'], list)
            or not datasets['EVENTS']
            or any(
                not isinstance(x, dict) or not {'id', 'kind', 'condition', 'choices', 'effect'} <= x.keys()
                for x in datasets['EVENTS']
            )
        ):
            errors.append('事件結構無效')
        if (
            not isinstance(datasets['PRODUCTS'], list)
            or not datasets['PRODUCTS']
            or any(
                not isinstance(x, dict)
                or not {'id', 'category', 'coverage_options_minor', 'waiting_months', 'premium_rate_bps'} <= x.keys()
                for x in datasets['PRODUCTS']
            )
        ):
            errors.append('保單結構無效')
        if not isinstance(datasets['RULESET'], dict) or datasets['RULESET'].get('stock_count') != 5:
            errors.append('股票數量必須為 5')
        # The 1.0 engine supports curated built-in risk rules only. Fail closed for custom mechanics.
        if not errors:
            if (
                datasets['EVENTS'] != content.EVENTS
                or datasets['PRODUCTS'] != content.PRODUCTS
                or datasets['RULESET'] != {'stock_count': 5}
            ):
                errors.append('本版只允許更換人設池；事件、保險與規則引擎必須符合已審核發布內容。')
        release['validation_errors'] = errors
        release['persona_count'] = len(datasets['PERSONAS']) if isinstance(datasets['PERSONAS'], list) else 0
        release['product_count'] = len(datasets['PRODUCTS']) if isinstance(datasets['PRODUCTS'], list) else 0
        release['status'] = 'DRAFT' if errors else 'VALIDATED'
        db.execute('UPDATE admin_releases SET body=? WHERE id=?', (store.j(release), release['id']))
        return 200, release
    if op == 'H06':
        require(release['status'] == 'VALIDATED', 'CONTENT_NOT_VALIDATED')
        release['status'] = 'PUBLISHED'
        db.execute('UPDATE admin_releases SET body=? WHERE id=?', (store.j(release), release['id']))
        db.execute(
            'INSERT INTO admin_audit VALUES(?,?,?,?)',
            (engine.uid(), u['id'], f'RELEASE_PUBLISH:{release["version"]}', engine.now()),
        )
        return 200, release
    fail('NOT_FOUND')
