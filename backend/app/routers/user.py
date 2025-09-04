from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_current_user
from ..models import User, UserPublic

router = APIRouter(
    prefix="/user",
    tags=["user"],
)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: UserPublic = Depends(get_current_user)):
    return current_user
