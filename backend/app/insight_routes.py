"""Owned read-only insights and explicit, cancellable background simulations."""
from starlette.concurrency import run_in_threadpool
import time
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse
from . import handlers,store,radar,insights
from .coach_routes import envelope,parse_body

router=APIRouter(prefix='/api/v1',tags=['危機雷達與人生分岔預演'])
from .errors import response as error_response

def error(exc):return error_response(exc)

def user(db,request):
    u,_=handlers.get_user(db,request)
    if not u:raise ValueError('UNAUTHENTICATED')
    handlers.verify_csrf(request,u);return u
def available(c,r):
    if r['status']!='ENDED' or c['status']!='AWAITING_REBIRTH' or c['runs'][-1]['id']!=r['id'] or len(c['runs'])>=3:raise ValueError('REBIRTH_NOT_AVAILABLE')

@router.get('/runs/{run_id}/radar')
def radar_read(run_id:str,request:Request):
    try:
        with store.tx(read_only=True) as db:
            u=user(db,request);_,r=handlers.owned_run(db,{'run_id':run_id},u)
        if r['status']=='ENDED':raise ValueError('RADAR_RUN_ENDED')
        return envelope(radar.read(r))
    except ValueError as exc:return error(exc)

@router.get('/runs/{run_id}/branches')
def latest(run_id:str,request:Request):
    try:
        with store.tx() as db:
            u=user(db,request);c,r=handlers.owned_run(db,{'run_id':run_id},u);available(c,r)
            value=insights.latest(db,u['id'],c,r)
        return envelope(value)
    except ValueError as exc:return error(exc)

@router.post('/runs/{run_id}/branches')
async def start(run_id:str,request:Request):
    try:body=await parse_body(request)
    except ValueError as exc:return error(exc)
    return await run_in_threadpool(start_sync,run_id,request,body)

def start_sync(run_id:str,request:Request,body):
    try:
        if set(body)-{'expected_version','expected_campaign_version'}:raise ValueError('VALIDATION_ERROR')
        with store.tx() as db:
            u=user(db,request);c,r=handlers.owned_run(db,{'run_id':run_id},u)
            job,task=insights.prepare(db,u['id'],c,r,request.headers.get('idempotency-key',''),body)
        insights.submit(task);return envelope(job,202)
    except (ValueError,TypeError,KeyError) as exc:return error(exc if isinstance(exc,ValueError) else ValueError('VALIDATION_ERROR'))

@router.get('/insights/jobs/{job_id}')
def read_job(job_id:str,request:Request):
    try:
        with store.tx() as db:
            u=user(db,request);value=insights.public(insights.load(db,job_id,u['id']))
        return envelope(value)
    except ValueError as exc:return error(exc)

@router.post('/insights/jobs/{job_id}/cancel')
def cancel(job_id:str,request:Request):
    try:
        with store.tx() as db:
            u=user(db,request);job=insights.load(db,job_id,u['id'])
            if job['status'] in insights.ACTIVE:
                job.update(status='CANCELLED',notice='已停止，已完成的日期仍可閱讀；也可以直接選擇回溯日期。')
                db.execute('UPDATE insight_jobs SET body=?,updated_at=? WHERE id=?',(store.j(job),time.time(),job_id))
        return envelope(insights.public(job))
    except ValueError as exc:return error(exc)
