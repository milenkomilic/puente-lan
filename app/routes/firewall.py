from fastapi import APIRouter, Depends

from app import firewall
from app.routes.bridges import require_actor

router = APIRouter(prefix="/api/firewall")
PORT = 8080


@router.get("")
def get_status(actor=Depends(require_actor)):
    return firewall.status(PORT)


@router.post("/apply")
def do_apply(actor=Depends(require_actor)):
    return firewall.apply(PORT)