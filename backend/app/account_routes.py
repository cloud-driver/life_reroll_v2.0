from fastapi import APIRouter,Request
from . import handlers,store,mail
from .coach_routes import envelope

router=APIRouter(prefix='/api/v1')

@router.get('/me/email-verification',tags=['帳號與驗證'])
def verification_state(request:Request):
    from .main import fail_response
    try:
        with store.tx() as db:
            user,_=handlers.get_user(db,request)
            if not user:raise ValueError('UNAUTHENTICATED')
            value=mail.state(db,user)
        return envelope(value)
    except ValueError as exc:return fail_response(str(exc))
