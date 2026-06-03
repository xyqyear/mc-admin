from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.jwt_utils import verify_password
from ..auth.login_code import loginCodeManager
from ..auth.session import clear_auth_cookies, create_session_token, set_auth_cookies
from ..db.crud.user import get_user_by_username
from ..db.database import get_db
from ..dependencies import verify_master_token
from ..models import UserPublic

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


class LoginResponse(BaseModel):
    user: UserPublic


class VerifyCodeRequest(BaseModel):
    username: str
    code: str


class VerifyCodeResponse(BaseModel):
    result: str


class CompleteCodeLoginRequest(BaseModel):
    ticket: str


@router.post("/token", response_model=LoginResponse)
async def login_for_access_token(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    user = await get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User ID is missing",
        )

    public_user = UserPublic(
        id=user.id,
        username=user.username,
        role=user.role,
        created_at=user.created_at,
    )
    token, csrf_token = create_session_token(public_user)
    set_auth_cookies(response, token, csrf_token)
    return LoginResponse(user=public_user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    clear_auth_cookies(response)


@router.post("/verifyCode", dependencies=[Depends(verify_master_token)])
async def verify_code(
    request: VerifyCodeRequest,
    db: AsyncSession = Depends(get_db),
) -> VerifyCodeResponse:
    result = await loginCodeManager.verify_user_with_code(
        db,
        request.username,
        request.code,
    )
    if result:
        return VerifyCodeResponse(result="success")
    raise HTTPException(status_code=400, detail="Invalid username or code")


@router.post("/code/complete", response_model=LoginResponse)
async def complete_code_login(
    request: CompleteCodeLoginRequest,
    response: Response,
) -> LoginResponse:
    user = loginCodeManager.complete_login(request.ticket)
    if user is None:
        raise HTTPException(status_code=400, detail="Invalid or expired login ticket")

    token, csrf_token = create_session_token(user)
    set_auth_cookies(response, token, csrf_token)
    return LoginResponse(user=user)


@router.websocket("/code")
async def code_auth(websocket: WebSocket):
    await loginCodeManager.manage_websocket(websocket)
