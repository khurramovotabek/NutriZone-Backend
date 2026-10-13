"""
ASGI entrypoint.

Serves the realtime (Channels/WebSocket) surface as a separate ASGI
worker pool from the WSGI pool (Django Implementation Blueprint §9).
Composes each app's own `interfaces/routing.py` centrally, mirroring
the URL-conf composition pattern in config/urls/. `chat`'s own
WebSocket routes are now registered (Chat Phase 3); `notifications`
remains an empty extension point until that module is implemented.
"""
import os

from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", f"config.settings.{os.environ.get('DJANGO_ENV', 'development')}")

# get_asgi_application() must be called before importing anything that
# touches Django models/apps (Channels convention).
django_asgi_app = get_asgi_application()

from core.channels_auth import JWTAuthMiddlewareStack  # noqa: E402
from apps.chat.interfaces.routing import websocket_urlpatterns as chat_websocket_urlpatterns  # noqa: E402

# Composed from per-app interfaces/routing.py modules -- `chat` is wired now;
# `notifications` remains an empty extension point until that module is implemented:
#   websocket_urlpatterns = chat_websocket_urlpatterns + apps.notifications.interfaces.routing.websocket_urlpatterns
websocket_urlpatterns: list = [*chat_websocket_urlpatterns]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
