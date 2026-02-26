from django.urls import path, include
from . import views
from . import views_platform  # 👈 new import

from website import views as website_views

urlpatterns = [
    path("", views.home, name="home"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.S2SLoginView.as_view(), name="login"),
    #path("logout/", views.S2SLogoutView.as_view(), name="logout"),
    path("logout/", views.signout, name="logout"),   # use our explicit view
    path("post-login/", website_views.post_login_redirect, name="post_login"),

        # --- Platform admin (Day-15) ---
    path("platform/hotels/", views_platform.platform_hotel_list, name="platform_hotel_list"),
    path("platform/hotels/<int:pk>/", views_platform.platform_hotel_detail, name="platform_hotel_detail"),
    path("platform/requests/", views_platform.platform_requests_list, name="platform_requests_list"),
    path("platform/hotels/<int:hotel_id>/", views.platform_hotel_profile, name="platform_hotel_profile"),
    path("platform/hotels/<int:hotel_id>/edit/", views.platform_hotel_edit, name="platform_hotel_edit"),
    path("platform/hotels/<int:hotel_id>/payments/add/", views.platform_add_payment, name="platform_add_payment"),


]
