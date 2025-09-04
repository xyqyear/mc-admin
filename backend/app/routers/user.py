from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_current_user
from ..models import User, UserPublic

router = APIRouter(
    prefix="/user",
    tags=["user"],
)


@router.get("/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)):
    if current_user.id is None:
        # This should not happen for persisted users, but handle the case
        raise HTTPException(status_code=500, detail="User ID is missing")
    return UserPublic(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        created_at=current_user.created_at,
    )
