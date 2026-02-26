from django.shortcuts import render,  get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.views import LoginView, LogoutView

from .forms import HotelAdminSignupForm, PlatformHotelForm, PlatformHotelPaymentForm
from django.contrib.auth import logout

from django.contrib.auth.decorators import login_required
from .models import User, HotelPayment, Hotel

def home(request):
    return render(request, "website/home.html")




def signup(request):
    if request.method == "POST":
        form = HotelAdminSignupForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Account created. Please log in.")
            return redirect("login")
    else:
        form = HotelAdminSignupForm()
    return render(request, "website/signup.html", {"form": form})

class S2SLoginView(LoginView):
    template_name = "registration/login.html"

class S2SLogoutView(LogoutView):
    pass



def signout(request):
    logout(request)          # clears the session
    return redirect("/login")     # back to login







@login_required
def post_login_redirect(request):
    """
    After login, send user to the correct dashboard based on role:
      - PLATFORM_ADMIN -> Platform Admin UI (/platform/hotels/)
      - HOTEL_ADMIN/STAFF -> Hotel Portal (/portal/live/)
      - GUEST/other -> home page (/)
    """
    user: User = request.user
    role = getattr(user, "role", None)

    if role == User.Roles.PLATFORM_ADMIN:
        # Platform admin dashboard
        return redirect("/platform/hotels/")

    if role in (User.Roles.HOTEL_ADMIN, User.Roles.STAFF):
        # Hotel portal dashboard
        return redirect("/portal/live/")

    # Fallback (e.g. GUEST)
    return redirect("/")



@login_required
def platform_hotel_profile(request, hotel_id):
    """
    Hotel profile page for Platform Admin.
    Tabs: general/billing/payments/requests logs etc.
    Already exists in day-15 — just ensure it uses this hotel_id.
    """
    hotel = get_object_or_404(Hotel, id=hotel_id)
    payments = hotel.payments.all()[:200]
    return render(request, "website/hotel_profile.html", {
        "hotel": hotel,
        "payments": payments,
    })


@login_required
def platform_hotel_edit(request, hotel_id):
    """
    16.3B — Edit any hotel details from platform panel.
    """
    hotel = get_object_or_404(Hotel, id=hotel_id)

    if request.method == "POST":
        form = PlatformHotelForm(request.POST, request.FILES, instance=hotel)
        if form.is_valid():
            form.save()
            messages.success(request, "Hotel details updated.")
            return redirect("platform_hotel_profile", hotel_id=hotel.id)
    else:
        form = PlatformHotelForm(instance=hotel)

    return render(request, "website/hotel_edit.html", {
        "hotel": hotel,
        "form": form,
    })


@login_required
def platform_add_payment(request, hotel_id):
    """
    16.3C — Add manual payment from platform profile.
    This will auto-extend expiry via HotelPayment.save() (Day-16 logic).
    """
    hotel = get_object_or_404(Hotel, id=hotel_id)

    if request.method == "POST":
        form = PlatformHotelPaymentForm(request.POST)
        if form.is_valid():
            pay = form.save(commit=False)
            pay.hotel = hotel
            pay.save()
            messages.success(request, "Payment added and expiry auto-updated.")
            return redirect("platform_hotel_profile", hotel_id=hotel.id)
    else:
        form = PlatformHotelPaymentForm()

    return render(request, "website/payment_add.html", {
        "hotel": hotel,
        "form": form,
    })