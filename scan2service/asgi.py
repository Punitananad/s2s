"""
ASGI config for Scan2Service project.

It exposes the ASGI callable as a module-level variable named ``application``.
"""

import os

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

import hotelportal.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scan2service.settings')

# Standard Django ASGI app (for HTTP)
django_asgi_app = get_asgi_application()

# Channels router: HTTP + WebSocket
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            hotelportal.routing.websocket_urlpatterns
        )
    ),
})
