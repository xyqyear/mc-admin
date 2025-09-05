from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.jwt_utils import get_password_hash
from ..db.crud.user import create_user, delete_user, get_all_users
from ..db.database import get_db
from ..dependencies import RequireRole
from ..models import User, UserCreate, UserPublic, UserRole

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)


@router.get("/users", response_model=list[UserPublic])
async def get_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(UserRole.OWNER)),
):
    """Get all users. Only accessible by OWNER role."""
    users = await get_all_users(db)
    return [
        UserPublic(
            id=user.id,
            username=user.username,
            role=user.role,
            created_at=user.created_at,
        )
        for user in users
        if user.id is not None
    ]


@router.post("/users", response_model=UserPublic)
async def create_new_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(UserRole.OWNER)),
):
    """Create a new user. Only accessible by OWNER role."""
    try:
        # Hash the password
        hashed_password = get_password_hash(user_data.password)

        # Create the user object
        new_user = User(
            username=user_data.username,
            hashed_password=hashed_password,
            role=user_data.role,
        )

        # Save to database
        created_user = await create_user(db, new_user)

        if created_user.id is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user",
            )

        return UserPublic(
            id=created_user.id,
            username=created_user.username,
            role=created_user.role,
            created_at=created_user.created_at,
        )
    except IntegrityError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )


@router.delete("/users/{user_id}")
async def delete_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(RequireRole(UserRole.OWNER)),
):
    """Delete a user by ID. Only accessible by OWNER role."""
    # Prevent users from deleting themselves
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    success = await delete_user(db, user_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return {"message": "User deleted successfully"}
