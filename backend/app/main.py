"""Entry point: python -m app.main --host 127.0.0.1 --port 8000"""

from __future__ import annotations
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.openapi.utils import get_openapi
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager
import anyio
from fastapi.middleware.cors import CORSMiddleware
from . import handlers, store, engine, wire, mail
from .errors import response as error_response
from .coach_routes import router as coach_router
from .insight_routes import router as insight_router
from .account_routes import router as account_router
from .training_routes import router as training_router

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / 'data/api_registry.json').read_text(encoding='utf-8'))
REGISTRY_BY_ID = {x['id']: x for x in REGISTRY}
SCHEMAS = json.loads((ROOT / 'data/schema_reference.json').read_text(encoding='utf-8'))['$defs']


@asynccontextmanager
async def lifespan(app):
    # Bound concurrent synchronous requests (and scrypt allocations) on small hosts.
    anyio.to_thread.current_default_thread_limiter().total_tokens = max(
        2, min(32, int(os.environ.get('LIFE_REQUEST_WORKERS', '4')))
    )
    async with anyio.create_task_group() as tasks:
        tasks.start_soon(prune_forever)
        yield
        tasks.cancel_scope.cancel()


def prune_once():
    with store.tx() as db:
        removed = store.prune(db)
    if any(removed.values()):
        logging.info('Pruned expired rows: %s', removed)


async def prune_forever():
    interval = max(60, int(os.environ.get('LIFE_PRUNE_INTERVAL_SECONDS', str(6 * 3600))))
    while True:
        try:
            await run_in_threadpool(prune_once)
        except Exception:
            logging.exception('Pruning expired rows failed')
        await anyio.sleep(interval)


app = FastAPI(
    lifespan=lifespan,
    title='人生讀檔｜保險教育遊戲 API',
    version='1.2.0',
    description='虛構保險及股票。每個遊戲狀態由後端 SQLite 權威存放。',
    docs_url='/docx',
    redoc_url=None,
)
store.init()
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=1)
origins = [
    x.strip().rstrip('/')
    for x in os.environ.get(
        'LIFE_CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173'
    ).split(',')
    if x.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allow_headers=['Authorization', 'Content-Type', 'X-CSRF-Token', 'Idempotency-Key', 'X-Demo-Coach-Token'],
    expose_headers=['X-Session-Token', 'X-Dev-Verification-Token', 'Content-Disposition'],
)
app.include_router(coach_router)
app.include_router(insight_router)
app.include_router(account_router)
app.include_router(training_router)


def fail_response(error):
    return error_response(error)


def dispatch(op, request, body=None):
    if body is None:
        body = {}
    request.state.mail_tasks = []
    try:
        with store.tx(read_only=request.method in ('GET', 'HEAD')) as db:
            u, sid = handlers.get_user(db, request)
            handlers.verify_csrf(request, u)
            current_user = u['id'] if u else None
            key = request.headers.get('idempotency-key', '')
            if op in ('C01', 'D01', 'E10', 'G04') and (not key or len(key) > 128):
                raise ValueError('IDEMPOTENCY_KEY_REQUIRED')
            if key and current_user and request.method not in ('GET', 'HEAD'):
                canonical = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
                digest = hashlib.sha256((request.url.path + '\n' + canonical).encode()).hexdigest()
                cached = db.execute(
                    'SELECT * FROM idempotency WHERE user_id=? AND key=? AND operation=?', (current_user, key, op)
                ).fetchone()
                if cached:
                    if cached['request_hash'] != digest:
                        raise ValueError('IDEMPOTENCY_KEY_REUSED')
                    record = json.loads(cached['reply_json'])
                    return JSONResponse(status_code=record['status'], content=record['response'])
            status, value = handlers.result(
                op, db, request, body or {}, u, request.path_params, dict(request.query_params)
            )
            if status == 401 and isinstance(value, dict) and value.get('_login_error'):
                return fail_response(value['_login_error'])
            if isinstance(value, dict) and value.get('_account_error'):
                return fail_response(value['_account_error'])
            cookie_token = None
            dev_token = None
            if isinstance(value, dict) and '_cookie_token' in value:
                cookie_token = value.pop('_cookie_token')
            if isinstance(value, dict):
                dev_token = value.pop('dev_verification_token', None) or value.pop('dev_token', None)
            if status == 204:
                return Response(status_code=204)
            value = wire.output(REGISTRY_BY_ID[op], value)
            response = {'data': value, 'meta': {'api_version': 'v1'}}
            if key and current_user and request.method not in ('GET', 'HEAD'):
                db.execute(
                    'INSERT INTO idempotency(user_id,key,operation,request_hash,reply_json,created_at) VALUES(?,?,?,?,?,?)',
                    (
                        current_user,
                        key,
                        op,
                        digest,
                        json.dumps({'status': status, 'response': response}, ensure_ascii=False),
                        time.time(),
                    ),
                )
            resp = JSONResponse(
                status_code=status,
                content=response,
                background=BackgroundTask(mail.submit_all, request.state.mail_tasks),
            )
            if cookie_token:
                resp.headers['X-Session-Token'] = cookie_token
                resp.set_cookie(
                    'life_session',
                    cookie_token,
                    max_age=60 * 60 * 24 * 30,
                    httponly=True,
                    samesite='lax',
                    secure=os.environ.get('LIFE_DEVELOPMENT_MODE', '1') == '0',
                )
            if dev_token:
                resp.headers['X-Dev-Verification-Token'] = dev_token
            if op == 'A04':
                resp.delete_cookie('life_session')
            return resp
    except ValueError as exc:
        return fail_response(exc)
    except (TypeError, KeyError, OverflowError):
        return fail_response('VALIDATION_ERROR')
    except Exception:
        logging.exception('Unhandled operation %s', op)
        return fail_response('SERVICE_UNAVAILABLE')


def make_get(op):
    def endpoint(request: Request):
        return dispatch(op, request)

    endpoint.__name__ = 'get_' + op
    return endpoint


def make_write(op):
    async def endpoint(request: Request):
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            return fail_response('VALIDATION_ERROR')
        return await run_in_threadpool(dispatch, op, request, body)

    endpoint.__name__ = 'write_' + op
    return endpoint


for item in REGISTRY:
    op = item['id']
    path = item['path']
    method = item['method']
    app.add_api_route(
        path,
        make_get(op) if method == 'GET' else make_write(op),
        methods=[method],
        tags=[item['group']],
        summary=f'{op} {item["description"]}',
        description=f'{item["rule"]}\n\n請求：{item["input"]}；成功：{item["output"]}。',
        operation_id=op,
        include_in_schema=True,
    )


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    doc = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    doc.setdefault('components', {}).setdefault('schemas', {})
    for name, schema in SCHEMAS.items():
        doc['components']['schemas'][name] = json.loads(json.dumps(schema).replace('#/$defs/', '#/components/schemas/'))
    for op in REGISTRY:
        path, method = op['path'], op['method'].lower()
        input_ = op['input']
        ref = input_ if input_ in SCHEMAS else None
        route = doc['paths'][path][method]
        if ref and method not in ('get', 'delete'):
            route['requestBody'] = {
                'required': True,
                'content': {'application/json': {'schema': {'$ref': '#/components/schemas/' + ref}}},
            }
        out = op['output']
        code = out.split(' ')[0]
        if code.isdecimal():
            route['responses'][code] = (
                {
                    'description': out,
                    'content': {
                        'application/json': {
                            'schema': {
                                'type': 'object',
                                'properties': {'data': {'description': out}, 'meta': {'type': 'object'}},
                            }
                        }
                    },
                }
                if code != '204'
                else {'description': 'No Content'}
            )
    app.openapi_schema = doc
    return doc


app.openapi = custom_openapi


@app.get('/', include_in_schema=False)
def home():
    return {'service': 'Life Replay API', 'swagger': '/docx', 'frontend': 'independent static server'}


@app.get('/api/v1/report-exports/{export_id}/download', include_in_schema=True, tags=['報告與重生'])
def download_report(export_id: str, request: Request):
    from io import BytesIO
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    with store.tx(read_only=True) as db:
        u, _ = handlers.get_user(db, request)
        if not u:
            return fail_response('UNAUTHENTICATED')
        c = next(
            (v for v in store.list_campaigns(db, u['id']) if any(x['id'] == export_id for x in v.get('exports', []))),
            None,
        )
        if not c:
            return fail_response('NOT_FOUND')
    buf = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont('MSung-Light'))
    p = canvas.Canvas(buf, pagesize=(595, 842))
    p.setFont('MSung-Light', 18)
    p.drawString(50, 785, '人生讀檔：三輪人生報告')
    p.setFont('MSung-Light', 12)
    y = 740
    for line in c['final_report']['comparison_notes']:
        p.drawString(50, y, line[:55])
        y -= 36
    for r in c['runs']:
        rep = engine.report(r)
        p.drawString(
            50,
            y,
            f'第 {r["run_index"]} 輪：{rep["ending_reason"]}；期末淨資產 {rep["ending_net_worth_minor"] // 100:,} 元',
        )
        y -= 36
    p.drawString(50, y, '商品、股價與報告均為教育模擬，不構成投資或投保建議。')
    p.save()
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type='application/pdf',
        headers={'Content-Disposition': 'attachment; filename="life-replay-report.pdf"'},
    )


if __name__ == '__main__':
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description='人生讀檔獨立 API 後端')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run('app.main:app', host=args.host, port=args.port)
