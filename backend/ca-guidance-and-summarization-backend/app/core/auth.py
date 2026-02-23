from authlib.integrations.starlette_client import OAuth
from itsdangerous import URLSafeSerializer
from app.core.config import settings

# Initialize OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=settings.GOOGLE_CLIENT_ID,
    client_secret=settings.GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile https://www.googleapis.com/auth/calendar.events'
    }
)

# Serializer for token encoding
serializer = URLSafeSerializer(settings.SECRET_KEY)

