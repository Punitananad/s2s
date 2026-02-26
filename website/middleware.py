# website/middleware.py  (16.5D strict)

from django.shortcuts import redirect
from django.utils import timezone


class HotelExpiryMiddleware:
    """
    STRICT expiry lock:

    If hotel subscription is expired, block ALL /portal/ pages
    for hotel users (HOTEL_ADMIN / STAFF / GUEST).

    Only allow:
      - /logout/
      - /portal/billing/expired/

    PLATFORM_ADMIN is never blocked.
    """

    def __init__(self, get_response):
        self.get_response = get_response

        # ✅ only these exact paths are allowed when expired
        self.allowed_exact_paths = {
            "/logout/",
            "/portal/billing/expired/",
        }

    def __call__(self, request):
        user = getattr(request, "user", None)

        # not logged in -> no blocking
        if not user or not user.is_authenticated:
            return self.get_response(request)

        role = getattr(user, "role", None)

        # PLATFORM_ADMIN never blocked
        if role == "PLATFORM_ADMIN":
            return self.get_response(request)

        hotel = getattr(user, "hotel", None)
        if not hotel:
            return self.get_response(request)

        exp = getattr(hotel, "subscription_expires_on", None)
        if not exp:
            return self.get_response(request)

        today = timezone.localdate()
        is_expired = exp < today
        path = request.path or "/"

        # enforce only for portal URLs
        if path.startswith("/portal/") and is_expired:
            if path not in self.allowed_exact_paths:
                return redirect("/portal/billing/expired/")

        return self.get_response(request)
