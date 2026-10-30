"""Error conditions are distinct, translated, contextual, and non-destructive."""

import ast
import base64
import copy
import io
import json
import re
import time
import zipfile
from pathlib import Path
import pytest
from app import (
    errors,
    store,
    training_catalog as catalog,
    training_service as svc,
    training_jobs as jobs,
    training_materials as docs,
)
from test_training import teacher, save, call
from test_game import game


def reject(g, path, body, code, status=422, method='POST'):
    _, res = g.call(method, '/training' + path, body, status)
    error = res.json()['error']
    assert error['code'] == code
    assert re.search('[\u4e00-\u9fff]', error['message'])
    return error


def test_public_error_catalog_covers_routes_and_calculators():
    codes = set()
    for path in (Path(__file__).parents[1] / 'app').glob('*.py'):
        if path.name == 'errors.py':
            continue
        for n in ast.walk(ast.parse(path.read_text())):
            if not isinstance(n, ast.Call):
                continue
            name = (
                n.func.id if isinstance(n.func, ast.Name) else n.func.attr if isinstance(n.func, ast.Attribute) else ''
            )
            index = (
                0
                if name in ('ValueError', 'fail', 'fail_response', '_account_error', '_login_error', 'append')
                else 1
                if name == 'require'
                else -1
            )
            if index >= 0 and len(n.args) > index and isinstance(n.args[index], ast.Constant):
                value = n.args[index].value
                if isinstance(value, str) and re.fullmatch('[A-Z][A-Z0-9_]+', value):
                    codes.add(value)
    assert not codes - errors.MESSAGES.keys()
    assert all(re.search('[\u4e00-\u9fff]', errors.message_for(c)) for c in codes)
    for code in codes:
        reply = errors.response(code)
        assert 400 <= reply.status_code <= 599
    assert 'secret' not in errors.response(ValueError('raw traceback secret')).body.decode()


def source_fixture(g):
    m = call(g, 'POST', '/admin/materials', {'name': '依據.txt', 'data_base64': base64.b64encode(b'source').decode()})
    jobs.POOL.submit(lambda: None).result(10)
    with store.tx() as db:
        body = json.loads(db.execute('SELECT body FROM training_materials WHERE id=?', (m['id'],)).fetchone()[0])
        body['sections'] = [
            {'id': m['id'] + ':' + str(i), 'label': f'第 {i} 段', 'text': '教學依據'} for i in range(1, 12)
        ]
        db.execute('UPDATE training_materials SET body=? WHERE id=?', (store.j(body), m['id']))
    c = catalog.base_course()
    c['material_ids'] = [m['id']]
    c['events'] = [c['events'][0]]
    return c, [s['id'] for s in body['sections']]


def test_sources_count_availability_and_rollback(teacher):
    c, refs = source_fixture(teacher)
    original = save(teacher)
    for selected, code in [
        ([], 'SOURCE_REQUIRED'),
        (refs[:9], 'SOURCE_LIMIT_EXCEEDED'),
        (refs, 'SOURCE_LIMIT_EXCEEDED'),
        (['not-selected-source'], 'SOURCE_NOT_AVAILABLE'),
        ([refs[0], refs[0]], 'SOURCE_DUPLICATE'),
    ]:
        value = copy.deepcopy(c)
        value['events'][0]['source_ids'] = selected
        err = reject(
            teacher,
            '/admin/courses/' + original['id'],
            {**value, 'expected_version': original['version']},
            code,
            method='PUT',
        )
        assert original['events'][0]['title'] in err['message'] and err['details']['event_index'] == 0
        assert err['details']['count'] == len(selected)
        assert next(x for x in call(teacher, 'GET', '/courses') if x['id'] == original['id']) == original
    c['events'][0]['source_ids'] = refs[:8]
    assert len(save(teacher, **c)['events'][0]['source_ids']) == 8


def test_specific_review_class_and_ai_conditions(teacher, monkeypatch):
    c = save(teacher)
    reject(teacher, '/admin/classes', {'course_id': c['id'], 'title': '測試班次'}, 'COURSE_NOT_PUBLISHED')
    reject(teacher, f'/admin/courses/{c["id"]}/publish', {'expected_version': c['version']}, 'REVIEW_REQUIRED')
    c = save(teacher, reviewed=True, unresolved=['尚待確認'])
    reject(teacher, f'/admin/courses/{c["id"]}/publish', {'expected_version': c['version']}, 'UNRESOLVED_ITEMS')
    product = {
        'name': '測試',
        'provider': '教學',
        'kind': 'LIABILITY',
        'source_title': '教材',
        'source_locator': '第 1 頁',
        'facts': ['已核對'],
        'reviewed': False,
    }
    reject(teacher, '/admin/products', product, 'PRODUCT_SOURCE_REQUIRED')
    reject(
        teacher, '/admin/products', {**product, 'source_url': 'https://example.test/policy'}, 'PRODUCT_REVIEW_REQUIRED'
    )
    reject(
        teacher,
        '/admin/products',
        {**product, 'source_url': 'https://example.test/policy', 'facts': []},
        'PRODUCT_FACTS_INVALID',
    )
    j = call(teacher, 'POST', '/admin/ai-jobs', {'course_id': c['id']})
    reject(teacher, f'/admin/ai-jobs/{j["id"]}/apply', {}, 'AI_JOB_NOT_COMPLETE', 409)
    for state, code in [
        ('QUEUED', 'AI_JOB_NOT_COMPLETE'),
        ('APPLIED', 'AI_JOB_ALREADY_APPLIED'),
        ('FAILED', 'AI_JOB_NO_RESULT'),
    ]:
        with store.tx() as db:
            row = json.loads(db.execute('SELECT body FROM training_ai_jobs WHERE id=?', (j['id'],)).fetchone()[0])
            row['status'] = state
            jobs.save(db, row)
        reject(teacher, f'/admin/ai-jobs/{j["id"]}/apply', {}, code, 409)
    monkeypatch.setenv('LIFE_TRAINING_LLM_ENABLED', '1')
    with store.tx() as db:
        row['status'] = 'RUNNING'
        jobs.save(db, row)
    reject(teacher, f'/admin/ai-jobs/{j["id"]}/retry', {}, 'AI_JOB_RUNNING', 409)


@pytest.mark.parametrize(
    'value,code',
    [
        (None, 'CLASS_CODE_INVALID'),
        ('1234', 'CLASS_CODE_INVALID'),
        ('中文中文中文中文', 'CLASS_CODE_INVALID'),
        ('ZZZZZZZZ', 'CLASS_NOT_FOUND'),
    ],
)
def test_class_code_errors(teacher, value, code):
    reject(teacher, '/join', {'code': value}, code, 404 if code == 'CLASS_NOT_FOUND' else 422)


@pytest.mark.parametrize(
    'field,value,label',
    [
        ('salary_minor', 0, '每月收入（元）'),
        ('living_bps', 9000, '生活支出占收入（%）'),
        ('horizon_months', 11, '課程月份'),
    ],
)
def test_field_range_names_and_units(teacher, field, value, label):
    c = catalog.base_course()
    c['rules'][field] = value
    error = reject(teacher, '/admin/courses', c, 'FIELD_OUT_OF_RANGE')
    assert label in error['message']
    if field == 'salary_minor':
        assert '10000' in error['message'] and '1000000' not in error['message']


def test_file_error_boundaries_and_legacy_messages(teacher):
    for name, raw, code in [
        ('empty.txt', b'', 'FILE_EMPTY'),
        ('bad.txt', b'\xff', 'TEXT_ENCODING_INVALID'),
        ('long.txt', b'a' * 160001, 'MATERIAL_TEXT_LIMIT'),
    ]:
        if not raw:
            reject(teacher, '/admin/materials', {'name': name, 'data_base64': ''}, code)
            continue
        m = call(teacher, 'POST', '/admin/materials', {'name': name, 'data_base64': base64.b64encode(raw).decode()})
        jobs.POOL.submit(lambda: None).result(10)
        v = next(x for x in call(teacher, 'GET', '/admin/materials') if x['id'] == m['id'])
        assert v['error_code'] == code and v['message'] == errors.message_for(code)
    with store.tx() as db:
        before = {'status': 'FAILED', 'sections': [], 'message': 'TOO_MANY_PAGES'}
        db.execute('UPDATE training_materials SET body=? WHERE id=?', (store.j(before), m['id']))
    assert next(x for x in call(teacher, 'GET', '/admin/materials') if x['id'] == m['id'])[
        'message'
    ] == errors.message_for('TOO_MANY_PAGES')
    with store.tx(read_only=True) as db:
        assert (
            json.loads(db.execute('SELECT body FROM training_materials WHERE id=?', (m['id'],)).fetchone()[0]) == before
        )
    with pytest.raises(ValueError, match='MATERIAL_TOO_LARGE'):
        docs.decode('big.txt', base64.b64encode(b'x' * (docs.MAX_BYTES + 1)).decode())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('word/document.xml', b'x' * (32 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match='MATERIAL_EXPANDED_TOO_LARGE'):
        docs.extract('docx', buf.getvalue())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for i in range(101):
            z.writestr(f'ppt/slides/slide{i + 1}.xml', '<slide/>')
    with pytest.raises(ValueError, match='TOO_MANY_PAGES'):
        docs.extract('pptx', buf.getvalue())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(
            'word/document.xml',
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            + ('<w:p>課程</w:p>' * 201)
            + '</w:document>',
        )
    with pytest.raises(ValueError, match='MATERIAL_SECTION_LIMIT'):
        docs.extract('docx', buf.getvalue())


def test_aggregate_file_limits_differ_from_single_file(teacher):
    with store.tx() as db:
        uid = db.execute('SELECT id FROM users').fetchone()[0]
        for i in range(100):
            db.execute(
                'INSERT INTO training_materials VALUES(?,?,?,?,?,?,?)',
                (
                    str(i),
                    uid,
                    '小檔.txt',
                    'txt',
                    b'a',
                    store.j({'status': 'READY', 'sections': [], 'message': ''}),
                    time.time(),
                ),
            )
    payload = {'name': 'test.txt', 'data_base64': base64.b64encode(b'x').decode()}
    reject(teacher, '/admin/materials', payload, 'MATERIAL_COUNT_LIMIT', 413)
    with store.tx() as db:
        db.execute('DELETE FROM training_materials')
        db.execute(
            'INSERT INTO training_materials VALUES(?,?,?,?,?,?,?)',
            (
                'total',
                uid,
                '大教材.txt',
                'txt',
                b'x' * (64 * 1024 * 1024),
                store.j({'status': 'READY', 'sections': [], 'message': ''}),
                time.time(),
            ),
        )
    reject(teacher, '/admin/materials', payload, 'MATERIAL_STORAGE_LIMIT', 413)
    with store.tx() as db:
        db.execute('DELETE FROM training_materials')
        for i in range(4):
            db.execute(
                'INSERT INTO training_materials VALUES(?,?,?,?,?,?,?)',
                (
                    str(i),
                    uid,
                    '等候.txt',
                    'txt',
                    b'x',
                    store.j({'status': 'PARSING', 'sections': [], 'message': '', '_instance': jobs.INSTANCE}),
                    time.time(),
                ),
            )
    reject(teacher, '/admin/materials', payload, 'MATERIAL_QUEUE_FULL', 429)


@pytest.mark.parametrize('op', ['D09', 'D10', 'D11'])
def test_funding_wrong_state_is_not_reported_as_money_problem(op):
    from app import handlers

    r = {'version': 1, 'status': 'EXPLORING', 'pending_event': None, 'events': [{'id': 'e'}]}
    with pytest.raises(ValueError, match='^STATE_CONFLICT$'):
        handlers.events_command(op, None, None, r, {'expected_version': 1}, {'event_id': 'e'}, {})
    assert '足以' not in errors.message_for('FUNDING_AVAILABLE')
    assert '期限' in errors.message_for('WAIT_NOT_AVAILABLE')


def test_unverified_start_names_the_actual_requirement(game):
    game.auth()
    with store.tx() as db:
        db.execute('UPDATE users SET verified=0')
    _, reply = game.call('POST', '/campaigns', {'locale': 'zh-TW'}, 403)
    assert reply.json()['error']['code'] == 'EMAIL_NOT_VERIFIED'
    assert '電子郵件' in reply.json()['error']['message']
