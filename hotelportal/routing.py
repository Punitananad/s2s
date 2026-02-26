# hotelportal/routing.py
from django.urls import path
from . import consumers

websocket_urlpatterns = [
    # Existing WebSocket used by the portal live board
    path("ws/portal/live/", consumers.HotelLiveConsumer.as_asgi()),

    # New alias for the external bot script (Day-14)
    path("ws/hotel-portal-live/", consumers.HotelLiveConsumer.as_asgi()),
]
