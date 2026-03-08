from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
import httpx
from app.core.auth import oauth, serializer
from app.core.config import settings
from app.models.schemas import UserInfo
from app.core.dependencies import get_current_user
from app.ca_guidance.tools.calendar_tool import clear_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_redirect_uri(request: Request) -> str:
    """
    Build OAuth callback URL so it is the same origin as the login request.
    This prevents 'mismatching_state' CSRF errors: the session cookie set at login
    must be sent when Google redirects to the callback (same host/path).
    When behind a reverse proxy, use X-Forwarded-Proto and X-Forwarded-Host.
    """
    if settings.REDIRECT_URI.strip():
        return settings.REDIRECT_URI.strip()
    # Same-origin callback: use the host/scheme the user's browser sees
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").strip().lower()
    if proto == "http" and (request.headers.get("x-forwarded-proto") or "").strip().lower() == "https":
        proto = "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    if host:
        host = host.split(",")[0].strip()
    base = f"{proto}://{host}"
    # If app is under a path (e.g. /guidance/auth/login), keep that path for callback
    path = request.url.path
    if "/auth" in path:
        path_prefix = path[: path.index("/auth")]
    else:
        path_prefix = ""
    return f"{base}{path_prefix}/auth/callback"


@router.get("/login")
async def login(request: Request):
    """Initiate Google OAuth login flow."""
    if not (settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in "
                "backend/services/academic-guidance/.env. See .env.example for setup instructions."
            ),
        )
    redirect_uri = _build_redirect_uri(request)
    return await oauth.google.authorize_redirect(request, redirect_uri, prompt="select_account")

@router.get("/callback", name="auth_callback")
async def auth_callback(request: Request):
    """Handle OAuth callback from Google."""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            # Fetch user info if not in token
            access_token = token.get('access_token')
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    'https://www.googleapis.com/oauth2/v2/userinfo',
                    headers={'Authorization': f'Bearer {access_token}'}
                )
                user_info = response.json()
        
        # Store user info in session
        user_data = {
            'email': user_info.get('email'),
            'name': user_info.get('name'),
            'picture': user_info.get('picture'),
            'access_token': token.get('access_token'),
        }
        request.session['user'] = user_data
        
        # Create a secure token for the frontend
        access_token = serializer.dumps(user_data)
        
        # Redirect to frontend with token
        frontend_url = f"{settings.FRONTEND_URL}?token={access_token}"
        return RedirectResponse(url=frontend_url)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )

@router.get("/me", response_model=UserInfo)
async def get_current_user_endpoint(request: Request):
    """Get current authenticated user info."""
    return get_current_user(request)

@router.post("/verify")
async def verify_token(token: str):
    """Verify a token from the frontend."""
    try:
        token_data = serializer.loads(token)
        return {"valid": True, "user": token_data}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

@router.post("/logout")
async def logout(request: Request):
    """Log out the current user."""
    request.session.clear()
    clear_access_token()
    return {"message": "Logged out successfully"}

