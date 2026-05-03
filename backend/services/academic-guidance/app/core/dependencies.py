from fastapi import HTTPException, Request, status
from typing import Optional
from app.models.schemas import UserInfo
from app.core.auth import serializer

def get_current_user(request: Request) -> UserInfo:
    """Dependency to get the current authenticated user from session or token."""
    # First, try to get from Authorization header
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header[7:]
        try:
            user_data = serializer.loads(token)
            return UserInfo(**user_data)
        except Exception:
            pass
    
    # Fallback to session
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

