from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.jwt_utils import (
    create_access_token,
    get_token_expiry,
    verify_password,
)
from ..auth.login_code import loginCodeManager
from ..db.crud.user import get_user_by_username
from ..db.database import get_db
from ..dependencies import JwtClaims, verify_master_token

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
)


class Token(BaseModel):
    access_token: str
    token_type: str


class VerifyTokenRequest(BaseModel):
    username: str
    code: str


class VerifyTokenResponse(BaseModel):
    result: str


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    user = await get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # 用户登录时 id 不应该为 None
    if user.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User ID is missing",
        )

    # 使用 JwtClaims 创建 JWT 数据
    jwt_claims = JwtClaims(
        sub=user.username,
        user_id=user.id,
        username=user.username,
        role=user.role.value,
        created_at=user.created_at.isoformat(),
        exp=get_token_expiry(),
    )
    access_token = create_access_token(jwt_claims)
    return Token(access_token=access_token, token_type="bearer")


@router.post("/verifyCode", dependencies=[Depends(verify_master_token)])
async def verify_code(request: VerifyTokenRequest, db: AsyncSession = Depends(get_db)):
    result = await loginCodeManager.verify_user_with_code(
        db, request.username, request.code
    )
    if result:
        return VerifyTokenResponse(result="success")
    else:
        raise HTTPException(status_code=400, detail="Invalid username or code")


@router.websocket("/code")
async def code_auth(websocket: WebSocket):
    """
    protocol:
        server -> client: {"type": "code", "code": "12345678", "timeout": 60}
        server -> client: {"type": "verified", "access_token": "jwttoken"}
    """
    await loginCodeManager.manage_websocket(websocket)
