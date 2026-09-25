from fastapi import APIRouter, Depends

from app.auth.schemas import UserPublic

from ..dependencies import get_current_user

router = APIRouter(
    prefix="/user",
    tags=["user"],
)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: UserPublic = Depends(get_current_user)):
    return current_user
