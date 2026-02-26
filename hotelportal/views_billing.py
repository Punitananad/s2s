# hotelportal/views_billing.py  (Day-10.1A — Stay Billing List)

from decimal import Decimal

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone

from .models import Stay
from .views_live import _allow_portal, _hotel_or_403
from hotelportal.decorators import portal_required
import csv
from django.http import HttpResponse








def _billing_stays_queryset(request):
    """
    Build filtered queryset for billing stays list.
    Filters (GET):
      - paid: PAID / UNPAID / ALL (default ALL)
      - payment_mode: CASH / UPI / CARD / ROOM / OTHER / ""(all)
      - start, end: YYYY-MM-DD (applied on check_in_at__date)
      - q: search in guest_name / phone / invoice_no
    """
    hotel = _hotel_or_403(request)
    qs = Stay.objects.select_related("room", "hotel").order_by("-created_at")

    # Normal hotel users see only their hotel
    if hotel:
        qs = qs.filter(hotel=hotel)

    # --- Filters ---
    paid = (request.GET.get("paid") or "ALL").upper()
    payment_mode = (request.GET.get("payment_mode") or "").upper()
    start = (request.GET.get("start") or "").strip()
    end = (request.GET.get("end") or "").strip()
    q = (request.GET.get("q") or "").strip()

    # Paid / Unpaid filter
    if paid == "PAID":
        qs = qs.filter(is_paid=True)
    elif paid == "UNPAID":
        qs = qs.filter(is_paid=False)

    # Payment mode filter
    if payment_mode:
        qs = qs.filter(payment_mode=payment_mode)

    # Date filter (by check-in date for now)
    # NOTE: we *don’t* parse, Django will handle YYYY-MM-DD strings.
    if start:
        qs = qs.filter(check_in_at__date__gte=start)
    if end:
        qs = qs.filter(check_in_at__date__lte=end)

    # Search by guest/invoice/phone
    if q:
        qs = qs.filter(
            Q(guest_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(invoice_no__icontains=q)
        )

    return qs


@login_required
@portal_required
def billing_stays_list(request):
    """
    Day-10.1A:
    Paginated list of stays for billing:
      - invoice_no, guest, room, check-in/out
      - total_due, payment_mode, paid flag
    """
    qs = _billing_stays_queryset(request)

    paginator = Paginator(qs, 25)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    # Defaults for form fields
    today_str = timezone.localdate().isoformat()
    start = (request.GET.get("start") or "").strip()
    end = (request.GET.get("end") or "").strip()
    if not start and not end:
        start = today_str
        end = today_str

    ctx = {
        "page_obj": page_obj,
        "paid": (request.GET.get("paid") or "ALL").upper(),
        "payment_mode": (request.GET.get("payment_mode") or "").upper(),
        "start": start,
        "end": end,
        "q": request.GET.get("q") or "",
    }
    return render(request, "hotelportal/billing_stays.html", ctx)



# -------------------------------
# 10.3 — Billing CSV Export
# -------------------------------

def _billing_queryset_for_export(request):
    """
    Small helper: build the same Stay queryset used for billing list,
    respecting basic filters: status, paid, date range, search.
    """
    hotel = getattr(request.user, "hotel", None)

    qs = Stay.objects.select_related("hotel", "room").order_by("-created_at")
    if hotel:
        qs = qs.filter(hotel=hotel)

    status = (request.GET.get("status") or "").strip()
    paid   = (request.GET.get("paid") or "").strip()     # "yes" / "no" / ""
    start  = (request.GET.get("start") or "").strip()    # yyyy-mm-dd
    end    = (request.GET.get("end") or "").strip()      # yyyy-mm-dd
    q      = (request.GET.get("q") or "").strip()

    if status:
        qs = qs.filter(status=status)

    if paid == "yes":
        qs = qs.filter(is_paid=True)
    elif paid == "no":
        qs = qs.filter(is_paid=False)

    if start:
        qs = qs.filter(check_in_at__date__gte=start)
    if end:
        qs = qs.filter(check_in_at__date__lte=end)

    if q:
        qs = qs.filter(
            Q(guest_name__icontains=q) |
            Q(phone__icontains=q) |
            Q(room__number__icontains=q) |
            Q(invoice_no__icontains=q)
        )

    return qs


@login_required
@portal_required
def billing_export_csv(request):
    """
    Export the filtered Stay billing list as CSV.
    Uses the same filters as the billing list page (status, paid, start, end, q).
    """
    qs = _billing_queryset_for_export(request)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="billing_stays.csv"'

    writer = csv.writer(resp)
    writer.writerow([
        "Invoice No",
        "Hotel",
        "Room",
        "Guest Name",
        "Phone",
        "Status",
        "Check-in",
        "Check-out",
        "GST %",
        "Subtotal",
        "GST Amount",
        "Grand Total",
        "Paid?",
        "Payment Mode",
        "Paid At",
    ])

    for stay in qs.iterator():
        # Use your existing helpers on Stay
        subtotal, gst_amount, grand_total = stay.compute_totals_with_tax()
        gst_pct = stay.effective_gst_percent()

        writer.writerow([
            stay.invoice_no or "",
            getattr(stay.hotel, "name", ""),
            getattr(stay.room, "number", ""),
            stay.guest_name or "",
            stay.phone or "",
            stay.get_status_display(),
            stay.check_in_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M")
                if stay.check_in_at else "",
            stay.check_out_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M")
                if stay.check_out_at else "",
            str(gst_pct),
            str(subtotal),
            str(gst_amount),
            str(grand_total),
            "YES" if stay.is_paid else "NO",
            stay.get_payment_mode_display() if stay.payment_mode else "",
            stay.paid_at.astimezone(timezone.get_current_timezone()).strftime("%Y-%m-%d %H:%M")
                if stay.paid_at else "",
        ])

    return resp



