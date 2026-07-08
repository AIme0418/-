from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..auth import require_admin_token
from ..storage import load_persona, save_persona

router = APIRouter(dependencies=[Depends(require_admin_token)])


class PersonaUpdate(BaseModel):
    name: str
    system_prompt: str


@router.get("/api/persona")
def get_persona():
    return load_persona()


@router.put("/api/persona")
def update_persona(update: PersonaUpdate):
    return save_persona(update.model_dump())
