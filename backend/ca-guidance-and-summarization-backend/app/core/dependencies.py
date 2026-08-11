from fastapi import HTTPException, Request, status
from typing import Optional
from app.models.schemas import UserInfo

def get_current_user(request: Request) -> UserInfo:
    """Dependency to get the current authenticated user from session."""
    user = request.session.get('user')
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return UserInfo(**user)

def get_optional_user(request: Request) -> Optional[UserInfo]:
    """Dependency to get the current authenticated user from session, or None if not authenticated."""
    user = request.session.get('user')
    if not user:
        return None
    try:
        return UserInfo(**user)
    except Exception:
        return None

