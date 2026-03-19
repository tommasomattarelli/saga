"""Role-based access control."""

from fastapi import Depends, HTTPException, status

from app.models.user import User
from app.security.auth import get_current_user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require the current user to be an admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
