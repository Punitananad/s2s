from django.contrib.auth.decorators import user_passes_test

def is_portal_user(user):
    return getattr(user, "role", None) in ("HOTEL_ADMIN", "STAFF", "PLATFORM_ADMIN")

portal_required = user_passes_test(is_portal_user)
