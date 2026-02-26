# website/views_platform.py  (15.1C)
from decimal import Decimal

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Sum, Count
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from .models import Hotel, HotelPayment, User
from hotelportal.models import Request  # existing Request model


def _is_platform_admin(user) -> bool:
    """
    Only PLATFORM_ADMIN should access these views.
    """
    return getattr(user, "role", None) == User.Roles.PLATFORM_ADMIN


# 15.2A – All hotels listing (platform)
@login_required
@user_passes_test(_is_platform_admin)
def platform_hotel_list(request):
    q = (request.GET.get("q") or "").strip()

    hotels = Hotel.objects.all().order_by("name")
    if q:
        hotels = hotels.filter(
            Q(name__icontains=q)
            | Q(city__icontains=q)
            | Q(hotel_code__icontains=q)
            | Q(owner_name__icontains=q)
        )

    # For now, we’ll calculate converted inline in template:
    # converted = hotel.payments.exists()
    # net_due = hotel.net_due()

    ctx = {
        "hotels": hotels,
        "q": q,
        "today": timezone.localdate(),
    }
    return render(request, "website/platform_hotel_list.html", ctx)


# 15.2B – Single hotel profile page
@login_required
@user_passes_test(_is_platform_admin)
def platform_hotel_detail(request, pk):
    hotel = get_object_or_404(Hotel, pk=pk)

    today = timezone.localdate()
    expected = hotel.billing_expected_amount(as_of=today)
    received = hotel.total_payment_received(as_of=today)
    net_due = hotel.net_due(as_of=today)

    # Last 50 payments for this hotel (for Payments tab)
    payments = hotel.payments.all().order_by("-date", "-id")[:50]

    # Request log filters (inside this hotel's profile)
    start = (request.GET.get("req_start") or "").strip()
    end = (request.GET.get("req_end") or "").strip()

    req_qs = Request.objects.filter(hotel=hotel)

    if start:
        req_qs = req_qs.filter(created_at__date__gte=start)
    if end:
        req_qs = req_qs.filter(created_at__date__lte=end)

    req_summary = req_qs.aggregate(
        total_requests=Count("id"),
        total_amount=Sum("subtotal"),
    )

    ctx = {
        "hotel": hotel,
        "today": today,
        "expected_payment": expected,
        "total_received": received,
        "net_due": net_due,
        "payments": payments,
        "req_start": start,
        "req_end": end,
        "req_total": req_summary.get("total_requests") or 0,
        "req_total_amount": req_summary.get("total_amount") or Decimal("0.00"),
        "requests_sample": req_qs.order_by("-created_at")[:25],  # small sample for log tab
    }
    return render(request, "website/platform_hotel_detail.html", ctx)


# 15.2C – Global requests list across all hotels
@login_required
@user_passes_test(_is_platform_admin)
def platform_requests_list(request):
    hotel_id = (request.GET.get("hotel") or "").strip()
    start = (request.GET.get("start") or "").strip()
    end = (request.GET.get("end") or "").strip()
    kind = (request.GET.get("kind") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Request.objects.select_related("hotel", "room").all()

    if hotel_id:
        qs = qs.filter(hotel_id=hotel_id)
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    if kind:
        qs = qs.filter(kind=kind)
    if status:
        qs = qs.filter(status=status)

    summary = qs.aggregate(
        total_requests=Count("id"),
        total_amount=Sum("subtotal"),
    )

    hotels = Hotel.objects.all().order_by("name")

    ctx = {
        "hotels": hotels,
        "selected_hotel": hotel_id,
        "start": start,
        "end": end,
        "kind": kind,
        "status": status,
        "total_requests": summary.get("total_requests") or 0,
        "total_amount": summary.get("total_amount") or Decimal("0.00"),
        "requests": qs.order_by("-created_at")[:200],  # cap for now
    }
    return render(request, "website/platform_requests_list.html", ctx)
