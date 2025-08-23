from fastapi import APIRouter, Depends

from ..dependencies import get_current_user
from ..models import User, UserPublic

router = APIRouter(
    prefix="/user",
    tags=["user"],
)


@router.get("/me", response_model=UserPublic)
def get_me(current_user: User = Depends(get_current_user)):
    return UserPublic.model_validate(current_user)
