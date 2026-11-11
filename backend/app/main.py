"""Entry point: python -m app.main --host 127.0.0.1 --port 8000"""

from __future__ import annotations
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.openapi.utils import get_openapi
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
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


# Framework-level failures (unknown route, wrong method, malformed parameters, an escaped
# exception) answer in the same {data, error} envelope as operations, so clients read one shape.
HTTP_ERROR_CODES = {
    401: 'UNAUTHENTICATED',
    403: 'FORBIDDEN',
    404: 'NOT_FOUND',
    405: 'METHOD_NOT_ALLOWED',
    413: 'PAYLOAD_TOO_LARGE',
    429: 'RATE_LIMITED',
}


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    code = HTTP_ERROR_CODES.get(exc.status_code, 'VALIDATION_ERROR' if exc.status_code < 500 else 'SERVICE_UNAVAILABLE')
    reply = error_response(code)
    reply.status_code = exc.status_code
    for name, value in (exc.headers or {}).items():
        reply.headers[name] = value
    return reply


@app.exception_handler(RequestValidationError)
async def request_invalid(request: Request, exc: RequestValidationError):
    return error_response('VALIDATION_ERROR')


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # The server still logs the traceback; the client only ever sees the public message.
    return error_response('SERVICE_UNAVAILABLE')


# Ordinary operations carry a few fields; only a content upload (H01, up to 2 MiB of text) is large.
MAX_BODY_BYTES = 256 * 1024
MAX_UPLOAD_BODY_BYTES = 8 * 1024 * 1024
DRAIN_BODY_BYTES = 16 * 1024 * 1024


def reject_constant(name):
    raise ValueError('non-finite number')


async def read_body(request: Request, limit: int):
    """Parse a bounded JSON object. Returns (body, error code); unreadable JSON stays an empty body."""
    declared = request.headers.get('content-length', '')
    too_large = declared.isdecimal() and int(declared) > limit
    raw = bytearray()
    seen = 0
    async for chunk in request.stream():
        seen += len(chunk)
        if too_large or seen > limit:
            # Discard rather than buffer. Reading the rest lets the client receive the 413 instead
            # of a reset connection; past the drain allowance the connection is simply dropped.
            too_large = True
            raw.clear()
            if seen > DRAIN_BODY_BYTES:
                break
            continue
        raw += chunk
    if too_large:
        return None, 'PAYLOAD_TOO_LARGE'
    try:
        # NaN and Infinity are not JSON; letting them through would poison stored amounts.
        body = json.loads(raw, parse_constant=reject_constant) if raw.strip() else {}
    except ValueError:
        # Covers malformed JSON, bad UTF-8 and NaN/Infinity alike. Treating a broken body as
        # empty used to surface as a misleading downstream error (e.g. "wrong password").
        return None, 'VALIDATION_ERROR'
    except RecursionError:
        return None, 'VALIDATION_ERROR'
    if not isinstance(body, dict):
        return None, 'VALIDATION_ERROR'
    return body, None


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
    except (TypeError, KeyError, OverflowError, AttributeError, IndexError):
        # A wrongly typed or shaped field; logged because the same types can also mean a defect.
        logging.warning('Rejected malformed input for operation %s', op, exc_info=True)
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
    limit = MAX_UPLOAD_BODY_BYTES if op == 'H01' else MAX_BODY_BYTES

    async def endpoint(request: Request):
        body, error = await read_body(request, limit)
        if error:
            return fail_response(error)
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
