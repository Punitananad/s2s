# Day 5.3 — Staff Live Board (polling), with detail popup and today counters.
from django.views.decorators.http import require_POST, require_GET
import json
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from .models import Request,Room, Stay, WhatsAppTemplate 
from hotelportal.decorators import portal_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Prefetch, Count
import csv
from django.db import transaction
from django.contrib import messages
from decimal import Decimal, ROUND_HALF_UP
from hotelportal.models import Stay, Request, HotelBillingSettings,Room
from hotelportal.realtime import push_live_board
from hotelportal.sockets import broadcast_portal_board
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
# hotelportal/views_live.py
from urllib.parse import urlencode, quote
from django.urls import reverse, NoReverseMatch

# you already created this earlier



# hotelportal/views_live.py






# hotelportal/views_live.py



def _q2(val: Decimal) -> Decimal:
    
    return (val or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)




























#from .views import _hotel_or_403  # you already had this helper






def _allow_portal(user):
    return getattr(user, "role", None) in ("HOTEL_ADMIN", "STAFF", "PLATFORM_ADMIN")

def _hotel_or_403(request):
    hotel = getattr(request.user, "hotel", None)
    if not hotel and getattr(request.user, "role", None) != "PLATFORM_ADMIN":
        return None
    return hotel

def _serialize_requests(qs, hotel=None):
    """
    Serialize Request queryset for Live Board / polling.

    Day-14 addition:
      - include hotel_id
      - include hotel_staff_group_code (for external WhatsApp sender script)
    """
    # Resolve hotel once, if not provided
    if hotel is None:
        # If qs is non-empty, take hotel from the first row
        first = qs[0] if qs else None
        hotel = getattr(first, "hotel", None)

    hotel_id = hotel.id if hotel else None
    staff_group_code = ""

    if hotel and hasattr(hotel, "staff_whatsapp_group_code"):
        staff_group_code = hotel.staff_whatsapp_group_code or ""

    out = []
    for r in qs:
        row_hotel_id = hotel_id or getattr(r.hotel, "id", None)
        row_group_code = staff_group_code
        if not row_group_code and hasattr(r.hotel, "staff_whatsapp_group_code"):
            row_group_code = r.hotel.staff_whatsapp_group_code or ""

        out.append(
            {
                "id": r.id,
                "room": r.room.number if r.room else "",
                "kind": r.kind,
                "status": r.status,
                "subtotal": float(r.subtotal or 0),
                "created_at": r.created_at.isoformat(),
                "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "cancelled_at": r.cancelled_at.isoformat() if r.cancelled_at else None,
                "note": r.note or "",
                "lines": [
                    {"name": ln.name_snapshot, "qty": ln.qty}
                    for ln in r.lines.all()
                ],
                # 👇 extra for the bot script
                "hotel_id": row_hotel_id,
                "hotel_staff_group_code": row_group_code,
            }
        )
    return out




def _serialize_rooms(qs):
    # expect qs = Room.objects.filter(hotel=...).select_related("current_stay")
    out = []
    for rm in qs:
        st = rm.current_stay
        out.append({
            "id": rm.id,
            "number": rm.number,
            "floor": rm.floor,
            "status": rm.status,  # FREE / BUSY / CLEANING
            "guest_name": st.guest_name if st else "",
            "guest_phone": st.phone if st else "",

            # Billing info for live board (Day-10)
            "stay_id": st.id if st else None,
            "total_due": float(st.total_due or 0) if st else 0.0,
            "is_paid": bool(st.is_paid) if st else False,
        })
    return out


def _broadcast_live_board(hotel):
    """
    Build a fresh board_state snapshot and push it via WebSocket
    to the correct hotel group (or 'all' for platform admin).
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return  # channel layer misconfigured or disabled

    qs = Request.objects.all()
    room_qs = Room.objects.all()
    if hotel:
        qs = qs.filter(hotel=hotel)
        room_qs = room_qs.filter(hotel=hotel)

    new_qs = qs.filter(status="NEW").select_related("room").order_by("-created_at")[:100]
    acc_qs = qs.filter(status="ACCEPTED").select_related("room").order_by("-updated_at")[:100]

    today = timezone.localdate()
    counts = {
        "completed_today": qs.filter(status="COMPLETED", completed_at__date=today).count(),
        "cancelled_today": qs.filter(status="CANCELLED", cancelled_at__date=today).count(),
    }

    room_qs = room_qs.select_related("current_stay").order_by("floor", "number")
    free_rooms     = [r for r in room_qs if r.status == "FREE"]
    busy_rooms     = [r for r in room_qs if r.status == "BUSY"]
    cleaning_rooms = [r for r in room_qs if r.status == "CLEANING"]

    payload = {
        "type": "board_state",
        "data": {
            "new": _serialize_requests(new_qs,  hotel=hotel),
            "accepted": _serialize_requests(acc_qs,  hotel=hotel),
            "counts": counts,
            "rooms": {
                "free": _serialize_rooms(free_rooms),
                "busy": _serialize_rooms(busy_rooms),
                "cleaning": _serialize_rooms(cleaning_rooms),
            }
        }
    }

    # Per-hotel group (portal UI)
    if hotel:
        async_to_sync(channel_layer.group_send)(
            f"hotel_portal_live_{hotel.id}",
            {
                "type": "board.push",
                "payload": payload,
            },
        )

    # Global group for staff-bot / platform listeners
    async_to_sync(channel_layer.group_send)(
        "hotel_portal_live_all",
        {
            "type": "board.push",
            "payload": payload,
        },
    )





@login_required
@portal_required
def live_board(request):
    """
    Show:
      - 2 lanes for service/food requests: NEW, ACCEPTED
      - 3 lanes for rooms: FREE, BUSY, CLEANING
    This is our operations screen, different from layout page.
    """
    hotel = _hotel_or_403(request)
    if not hotel and getattr(request.user, "role", None) != "PLATFORM_ADMIN":
        return HttpResponseForbidden("No hotel set")

    # -----------------------
    # Requests (existing)
    # -----------------------
    qs = Request.objects.all()
    if hotel:
        qs = qs.filter(hotel=hotel)

    new_qs = qs.filter(status="NEW").select_related("room").order_by("-created_at")[:100]
    acc_qs = qs.filter(status="ACCEPTED").select_related("room").order_by("-updated_at")[:100]

    today = timezone.localdate()
    completed_today = qs.filter(status="COMPLETED", completed_at__date=today).count()
    cancelled_today = qs.filter(status="CANCELLED", cancelled_at__date=today).count()

    # -----------------------
    # Rooms (existing)
    # -----------------------
    room_qs = Room.objects.all()
    if hotel:
        room_qs = room_qs.filter(hotel=hotel)
    room_qs = room_qs.select_related("current_stay").order_by("floor", "number")

    free_rooms     = [r for r in room_qs if r.status == "FREE"]
    busy_rooms     = [r for r in room_qs if r.status == "BUSY"]
    cleaning_rooms = [r for r in room_qs if r.status == "CLEANING"]

    # -----------------------
    # 13.1B — WhatsApp templates
    # -----------------------
    # For now: show ALL active templates (ignore hotel filter so you always see them).
    # Later we can tighten this to per-hotel once everything is working.
    wa_qs = WhatsAppTemplate.objects.filter(is_active=True).order_by("sort_order", "label")
    wa_templates = [
        {"id": t.id, "label": t.label}
        for t in wa_qs
    ]

    ctx = {
        "new_initial_json": json.dumps(_serialize_requests(new_qs, hotel=hotel)),
        "accepted_initial_json": json.dumps(_serialize_requests(acc_qs, hotel=hotel)),
        "completed_today": completed_today,
        "cancelled_today": cancelled_today,

        # rooms initial json
        "free_rooms_json": json.dumps(_serialize_rooms(free_rooms)),
        "busy_rooms_json": json.dumps(_serialize_rooms(busy_rooms)),
        "cleaning_rooms_json": json.dumps(_serialize_rooms(cleaning_rooms)),

        # 13.1B: WhatsApp templates for JS
        "wa_templates_json": json.dumps(wa_templates),
    }
    return render(request, "hotelportal/live_board.html", ctx)





# -----------------------------
# 7.2 — LIVE POLL (AJAX)
# -----------------------------
@login_required
@portal_required
@require_GET
def live_poll(request):
    hotel = _hotel_or_403(request)
    if not hotel and request.user.role != "PLATFORM_ADMIN":
        return JsonResponse({"ok": False, "error": "no-hotel"}, status=403)

    qs = Request.objects.filter(hotel=hotel) if hotel else Request.objects.all()

    new_qs = qs.filter(status="NEW").select_related("room").order_by("-created_at")[:100]
    acc_qs = qs.filter(status="ACCEPTED").select_related("room").order_by("-updated_at")[:100]

    today = timezone.localdate()
    counts = {
        "completed_today": qs.filter(status="COMPLETED", completed_at__date=today).count(),
        "cancelled_today": qs.filter(status="CANCELLED", cancelled_at__date=today).count(),
    }

    # rooms
    room_qs = Room.objects.filter(hotel=hotel) if hotel else Room.objects.all()
    room_qs = room_qs.select_related("current_stay").order_by("floor", "number")

    free_rooms     = [r for r in room_qs if r.status == "FREE"]
    busy_rooms     = [r for r in room_qs if r.status == "BUSY"]
    cleaning_rooms = [r for r in room_qs if r.status == "CLEANING"]

    return JsonResponse({
        "ok": True,
        "new": _serialize_requests(new_qs, hotel=hotel),
        "accepted": _serialize_requests(acc_qs, hotel=hotel),
        "counts": counts,
        "rooms": {
            "free": _serialize_rooms(free_rooms),
            "busy": _serialize_rooms(busy_rooms),
            "cleaning": _serialize_rooms(cleaning_rooms),
        }
    })








@login_required
@portal_required
def live_action(request, request_id):
    """
    POST: accept | complete | cancel
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    hotel = _hotel_or_403(request)
    if not hotel and request.user.role != "PLATFORM_ADMIN":
        return JsonResponse({"ok": False, "error": "no_hotel"}, status=403)

    action = request.POST.get("action")
    if action not in ("accept", "complete", "cancel"):
        return HttpResponseBadRequest("Invalid action")

    # lock the row to avoid race conditions
    qs = Request.objects.select_for_update()
    if hotel:
        qs = qs.filter(hotel=hotel)
    req = get_object_or_404(qs, id=request_id)

    now = timezone.now()
    if action == "accept":
        if req.status != "NEW":
            return JsonResponse({"ok": False, "error": "bad_state"}, status=409)
        req.status = "ACCEPTED"
        req.accepted_at = now
        req.save(update_fields=["status", "accepted_at", "updated_at"])
    elif action == "complete":
        if req.status != "ACCEPTED":
            return JsonResponse({"ok": False, "error": "bad_state"}, status=409)
        req.status = "COMPLETED"
        req.completed_at = now
        req.save(update_fields=["status", "completed_at", "updated_at"])
    else:  # cancel
        if req.status not in ("NEW", "ACCEPTED"):
            return JsonResponse({"ok": False, "error": "bad_state"}, status=409)
        req.status = "CANCELLED"
        req.cancelled_at = now
        req.save(update_fields=["status", "cancelled_at", "updated_at"])
        # NEW: push live update
    push_live_board(hotel)
        # 11.2 — push live update
    # 🔔 PUSH live board update
    _broadcast_live_board(hotel)    
    broadcast_portal_board(hotel.id if hotel else None)

    return JsonResponse({"ok": True})
    

# live_detail: add select_related(...) and pass request=...
@login_required
@portal_required
def live_detail(request, request_id):
    """
    Return an HTML fragment with full details for popup.
    """
    hotel = _hotel_or_403(request)
    if not hotel and getattr(request.user, "role", None) != "PLATFORM_ADMIN":
        return JsonResponse({"error": "no_hotel"}, status=403)

    qs = (Request.objects
          .select_related("room", "service_item", "stay")
          .prefetch_related("lines"))
    if hotel:
        qs = qs.filter(hotel=hotel)

    r = get_object_or_404(qs, id=request_id)
    html = render_to_string("hotelportal/_request_detail.html", {"r": r}, request=request)
    return JsonResponse({"ok": True, "html": html})






# Helper: build filtered queryset
# -------------------------------

# ...your existing imports...

def _filtered_history_queryset(request):
    """
    Build the filtered queryset for the history table/export using GET params.
    Filters: status, kind, room, start, end, q
    Default: if no filters provided, show *today*.
    """
    hotel = getattr(request.user, "hotel", None)

    qs = (
        Request.objects
        .select_related("room", "service_item")
        .order_by("-created_at", "-id")  # newest first, stable
    )
    if hotel:
        qs = qs.filter(hotel=hotel)  # PLATFORM_ADMIN: no hotel -> see all

    # --- Filters (all optional) ---
    status = (request.GET.get("status") or "").strip()
    kind   = (request.GET.get("kind") or "").strip()
    room   = (request.GET.get("room") or "").strip()  # exact room number from dropdown
    start  = (request.GET.get("start") or "").strip()
    end    = (request.GET.get("end") or "").strip()
    q      = (request.GET.get("q") or "").strip()

    # If user did not set ANY filter, default to today's date
    no_filters = not any([status, kind, room, start, end, q])
    if no_filters:
        today = timezone.localdate()
        qs = qs.filter(created_at__date=today)
        return qs

    # Otherwise respect provided filters
    if status:
        qs = qs.filter(status=status)
    if kind:
        qs = qs.filter(kind=kind)
    if room:
        qs = qs.filter(room__number=room)
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)
    if q:
        qs = qs.filter(Q(note__icontains=q) | Q(service_item__name__icontains=q))

    return qs


@login_required
@user_passes_test(_allow_portal)
def history_view(request):
    """
    Paginated history list with filters.
    Defaults to today's records when no filters provided.
    """
    hotel = getattr(request.user, "hotel", None)
    qs = _filtered_history_queryset(request)

    paginator = Paginator(qs, 25)
    # Always show page 1 by default (newest first due to ordering)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    # room choices for dropdown (only for current hotel)
    rooms_qs = Room.objects.all()
    if hotel:
        rooms_qs = rooms_qs.filter(hotel=hotel)
    rooms_qs = rooms_qs.order_by("number").values_list("number", flat=True)

    # For the form, if user didn’t provide start/end, prefill with today (UX)
    start = (request.GET.get("start") or "").strip()
    end   = (request.GET.get("end") or "").strip()
    if not start and not end:
        today_str = timezone.localdate().isoformat()
        start = today_str
        end = today_str

    ctx = {
        "page_obj": page_obj,
        "status": request.GET.get("status") or "",
        "kind": request.GET.get("kind") or "",
        "room": request.GET.get("room") or "",
        "start": start,
        "end": end,
        "q": request.GET.get("q") or "",
        "rooms": list(rooms_qs),
    }
    return render(request, "hotelportal/history.html", ctx)

# -------------------------------
# 8.1 — Export CSV (respects filters)
# -------------------------------
@login_required
@user_passes_test(_allow_portal)
def history_export_csv(request):
    """
    Download CSV of the currently filtered history list.
    """
    qs = _filtered_history_queryset(request)

    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = 'attachment; filename="requests_export.csv"'

    writer = csv.writer(resp)
    writer.writerow([
        "ID", "Hotel", "Room", "Kind", "Status",
        "Subtotal", "Created", "Accepted", "Completed", "Cancelled",
        "Service Item", "Note",
    ])

    for r in qs.iterator():
        writer.writerow([
            r.id,
            getattr(r.hotel, "name", ""),
            getattr(r.room, "number", ""),
            r.kind,
            r.status,
            str(r.subtotal or ""),
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            r.accepted_at.strftime("%Y-%m-%d %H:%M:%S") if r.accepted_at else "",
            r.completed_at.strftime("%Y-%m-%d %H:%M:%S") if r.completed_at else "",
            r.cancelled_at.strftime("%Y-%m-%d %H:%M:%S") if r.cancelled_at else "",
            (r.service_item.name if r.service_item else ""),
            r.note or "",
        ])
    return resp

# -------------------------------
# Single Request Detail
# -------------------------------
# request_detail: add slip support
@portal_required
def request_detail(request, pk):
    """
    Show a single request (food or service) with guest info, note, timestamps, and lines.
    Print-friendly page. Use ?print=slip for compact receipt.
    """
    hotel = getattr(request.user, "hotel", None)

    qs = (Request.objects
          .select_related("room", "service_item", "stay")
          .prefetch_related("lines"))
    if hotel:
        qs = qs.filter(hotel=hotel)

    r = get_object_or_404(qs, id=pk)

    if (request.GET.get("print") or "").lower() == "slip":
        return render(request, "hotelportal/receipt_slip.html", {"r": r})

    return render(request, "hotelportal/request_detail.html", {"r": r})





# -----------------------------
# we keep your existing endpoint:
# POST /portal/stay/checkin/  (you already wired this in urls)
# -----------------------------
@login_required
@portal_required
@require_POST
def stay_checkin(request):
    """
    Expects: room_id, guest_name, phone
    Creates a Stay and flips room -> BUSY
    """
    hotel = _hotel_or_403(request)
    if not hotel and request.user.role != "PLATFORM_ADMIN":
        return JsonResponse({"ok": False, "error": "no-hotel"}, status=403)

    room_id   = request.POST.get("room_id")
    guest_name= (request.POST.get("guest_name") or "").strip()
    phone     = (request.POST.get("phone") or "").strip()

    room = get_object_or_404(Room, id=room_id, hotel=hotel)

    if room.current_stay:
        return JsonResponse({"ok": False, "error": "already-busy"}, status=400)

    stay = Stay.objects.create(
        hotel=hotel,
        room=room,
        guest_name=guest_name,
        phone=phone,
        status="CHECKED_IN",
        check_in_at=timezone.now(),
    )
    room.current_stay = stay
    room.status = "BUSY"
    room.save(update_fields=["current_stay", "status"])
    push_live_board(hotel)
        # 11.2 — push live update
    _broadcast_live_board(hotel)    
    broadcast_portal_board(hotel.id if hotel else None)
    return JsonResponse({"ok": True, "stay_id": stay.id})
    







# 7.7 — Check-out and Mark Ready endpoints

@login_required
@portal_required
@require_POST
def stay_checkout(request):
    """
    Mark a BUSY room as CHECKED_OUT -> CLEANING
    """
    hotel = _hotel_or_403(request)
    if not hotel:
        return JsonResponse({"ok": False, "error": "no-hotel"}, status=403)

    room_id = request.POST.get("room_id")
    room = get_object_or_404(Room, id=room_id, hotel=hotel)

    stay = getattr(room, "current_stay", None)
    if not stay:
        return JsonResponse({"ok": False, "error": "no-active-stay"}, status=400)

    stay.status = "CHECKED_OUT"
    stay.check_out_at = timezone.now()
    stay.save(update_fields=["status", "check_out_at"])

    room.current_stay = None
    room.status = "CLEANING"
    room.save(update_fields=["current_stay", "status"])
    push_live_board(hotel)
        # 11.2 — push live update
    _broadcast_live_board(hotel)    
    broadcast_portal_board(hotel.id if hotel else None)
    return JsonResponse({"ok": True})


@login_required
@portal_required
@require_POST
def room_mark_ready(request):
    """
    Mark a CLEANING room as FREE.
    """
    hotel = _hotel_or_403(request)
    if not hotel:
        return JsonResponse({"ok": False, "error": "no-hotel"}, status=403)

    room_id = request.POST.get("room_id")
    room = get_object_or_404(Room, id=room_id, hotel=hotel)

    if room.status != "CLEANING":
        return JsonResponse({"ok": False, "error": "not-cleaning"}, status=400)

    room.status = "FREE"
    room.save(update_fields=["status"])
    push_live_board(hotel)

        # 11.2 — push live update
    _broadcast_live_board(hotel)    
    broadcast_portal_board(hotel.id if hotel else None)
    return JsonResponse({"ok": True})







from django.db.models import Sum

@portal_required
def stay_detail_popup(request):
    """
    Returns HTML fragment with *current* stay details for a BUSY room:
    - guest/phone
    - all requests (FOOD + SERVICE) belonging to this stay
    - totals (food, services, grand)
    - unpaid totals
    - Checkout + Print buttons
    """
    hotel = _hotel_or_403(request)
    room_id = request.GET.get("room_id")
    if not room_id:
        return JsonResponse({"ok": False, "error": "missing_room"}, status=400)

    room_qs = Room.objects.all()
    if hotel:
        room_qs = room_qs.filter(hotel=hotel)

    room = get_object_or_404(room_qs, id=room_id)
    stay = _get_open_stay(room)
    if not stay:
        html = '<div class="text-muted">No active stay for this room.</div>'
        return JsonResponse({"ok": True, "html": html})

    # All requests for this stay (we'll still SHOW cancelled in list)
    reqs = (
        Request.objects
        .filter(hotel=room.hotel, room=room, stay=stay)
        .select_related("service_item")
        .prefetch_related("lines")
        .order_by("-created_at")
    )

    # ---- Totals (exclude CANCELLED from amounts) ----
    billable_qs = reqs.exclude(status="CANCELLED")

    food_total = (
        billable_qs
        .filter(kind="FOOD")
        .aggregate(total=Sum("subtotal"))["total"] or 0
    )
    svc_total = (
        billable_qs
        .filter(kind="SERVICE")
        .aggregate(total=Sum("subtotal"))["total"] or 0
    )
    grand_total = food_total + svc_total

    # ---- Unpaid portion (for current due) ----
    unpaid_qs = billable_qs.filter(is_paid=False)

    unpaid_food_total = (
        unpaid_qs
        .filter(kind="FOOD")
        .aggregate(total=Sum("subtotal"))["total"] or 0
    )
    unpaid_svc_total = (
        unpaid_qs
        .filter(kind="SERVICE")
        .aggregate(total=Sum("subtotal"))["total"] or 0
    )
    unpaid_total = unpaid_food_total + unpaid_svc_total

    html = render_to_string(
        "hotelportal/_stay_detail.html",
        {
            "room": room,
            "stay": stay,
            "requests": reqs,
            "food_total": food_total,
            "svc_total": svc_total,
            "grand_total": grand_total,
            "unpaid_total": unpaid_total,
            "unpaid_food_total": unpaid_food_total,
            "unpaid_svc_total": unpaid_svc_total,
        },
    )
    return JsonResponse({"ok": True, "html": html})


def _get_open_stay(room):
    # Fallback helper if room.current_stay isn’t set on ORM side
    return (getattr(room, "current_stay", None)
            or Stay.objects.filter(room=room, checkout_at__isnull=True).order_by("-id").first())







  
@portal_required
def stay_print_slip(request):
    """
    Print-friendly *stay* slip for the currently open stay (or a given stay_id).
    GET: ?room_id=...  OR ?stay_id=...
    """
    hotel = _hotel_or_403(request)
    stay_id = request.GET.get("stay_id")
    room_id = request.GET.get("room_id")

    if stay_id:
        qs = Stay.objects.select_related("room", "hotel")
        if hotel:
            qs = qs.filter(hotel=hotel)
        stay = get_object_or_404(qs, id=stay_id)
        room = stay.room
    else:
        if not room_id:
            return HttpResponse("Missing room_id or stay_id", status=400)
        room_qs = Room.objects.all()
        if hotel:
            room_qs = room_qs.filter(hotel=hotel)
        room = get_object_or_404(room_qs, id=room_id)
        stay = _get_open_stay(room)
        if not stay:
            return HttpResponse("No active stay.", status=404)

    reqs = (Request.objects
            .filter(hotel=room.hotel, room=room, stay=stay)
            .select_related("service_item")
            .prefetch_related("lines")
            .order_by("created_at"))

    food_total = reqs.filter(kind="FOOD").exclude(status="CANCELLED").aggregate(Sum("subtotal"))["subtotal__sum"] or 0
    svc_total  = reqs.filter(kind="SERVICE").exclude(status="CANCELLED").aggregate(Sum("subtotal"))["subtotal__sum"] or 0
    grand = food_total + svc_total

    return render(request, "hotelportal/stay_receipt_slip.html", {
        "stay": stay, "room": room, "requests": reqs,
        "food_total": food_total, "svc_total": svc_total, "grand_total": grand,
        "print_mode": True,
    })


@portal_required
def stay_checkout_confirm(request):
    """
    Finalize checkout:
    - computes totals
    - closes the stay (sets checkout_at)
    - sets room status -> CLEANING and drops current_stay link (your existing checkout flow does this;
      keep it consistent with your earlier portal_stay_checkout side-effects)
    Returns: {ok: true, totals:{food, service, grand}}
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    hotel = _hotel_or_403(request)
    room_id = request.POST.get("room_id")
    if not room_id:
        return JsonResponse({"ok": False, "error": "missing_room"}, status=400)

    room_qs = Room.objects.select_for_update()
    if hotel:
        room_qs = room_qs.filter(hotel=hotel)
    room = get_object_or_404(room_qs, id=room_id)

    stay = _get_open_stay(room)
    if not stay:
        return JsonResponse({"ok": False, "error": "no_active_stay"}, status=404)

    # Totals (exclude cancelled)
    reqs = Request.objects.filter(hotel=room.hotel, room=room, stay=stay)
    food_total = reqs.filter(kind="FOOD").exclude(status="CANCELLED").aggregate(Sum("subtotal"))["subtotal__sum"] or 0
    svc_total  = reqs.filter(kind="SERVICE").exclude(status="CANCELLED").aggregate(Sum("subtotal"))["subtotal__sum"] or 0
    grand = food_total + svc_total

    # Close stay + flip room; keep in a transaction to be safe
    from django.db import transaction
    with transaction.atomic():
        # mark stay closed
        if not getattr(stay, "checkout_at", None):
            stay.checkout_at = timezone.now()
            stay.save(update_fields=["checkout_at"])
        # room → CLEANING, detach current_stay if you store it explicitly
        room.status = "CLEANING"
        if hasattr(room, "current_stay_id"):
            room.current_stay = None
        room.save(update_fields=["status", *(["current_stay"] if hasattr(room, "current_stay_id") else [])])

    return JsonResponse({
        "ok": True,
        "totals": {
            "food": float(food_total),
            "service": float(svc_total),
            "grand": float(grand),
        }
    })









# --- Day-8.5: Stay History + Stay Detail (full page) ---



def _today_dates():
    today = timezone.localdate()
    return today, today

def _filtered_stays_queryset(request):
    """
    Filters:
      - status: ACTIVE / CHECKED_OUT
      - room: (partial match on room.number)
      - start, end: (by check-in date)
      - q: guest_name / phone icontains
    Defaults to today's check-ins if start/end not provided.
    """
    hotel = _hotel_or_403(request)  # None for PLATFORM_ADMIN
    qs = Stay.objects.select_related("room", "hotel").order_by("-created_at")
    if hotel:
        qs = qs.filter(hotel=hotel)

    status = (request.GET.get("status") or "").strip().upper()
    room   = (request.GET.get("room") or "").strip()
    start  = (request.GET.get("start") or "").strip()
    end    = (request.GET.get("end") or "").strip()
    q      = (request.GET.get("q") or "").strip()

    # status
    if status == "ACTIVE":
        qs = qs.filter(checkout_at__isnull=True)
    elif status == "CHECKED_OUT":
        qs = qs.filter(checkout_at__isnull=False)

    # room partial
    if room:
        qs = qs.filter(room__number__icontains=room)

    # date range (by check-in date = created_at.date())
    if not start and not end:
        start, end = _today_dates()
    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)

    # search guest/phone
    if q:
        qs = qs.filter(Q(guest_name__icontains=q) | Q(phone__icontains=q))

    return qs, status, room, start, end, q



@login_required
@portal_required
def stays_history_view(request):
    qs, status, room, start, end, q = _filtered_stays_queryset(request)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    # 🔹 All rooms (numbers) that have at least one Stay in this hotel
    rooms_qs = (
        Room.objects
        .filter(hotel=request.user.hotel, stay__isnull=False)
        .order_by("number")
        .distinct()
    )

    ctx = {
        "page_obj": page_obj,
        "status": status,
        "room": room,
        "start": str(start) if start else "",
        "end": str(end) if end else "",
        "q": q,
        "rooms": rooms_qs,   # ← NEW
    }
    return render(request, "hotelportal/stays_history.html", ctx)


@login_required
@portal_required
def stays_export_csv(request):
    qs, status, room, start, end, q = _filtered_stays_queryset(request)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="stays.csv"'

    writer = csv.writer(response)
    writer.writerow([
        "ID",
        "Room",
        "Guest",
        "Phone",
        "Status",
        "Check-in",
        "Checkout",
    ])

    # Use the real check-in / check-out fields from the Stay model
    for s in qs.select_related("room"):
        writer.writerow([
            s.id,
            s.room.number if s.room_id else "",
            (s.guest_name or ""),
            (s.phone or ""),
            s.status,
            s.check_in_at.strftime("%Y-%m-%d %H:%M") if s.check_in_at else "",
            s.check_out_at.strftime("%Y-%m-%d %H:%M") if s.check_out_at else "",
        ])

    return response

@login_required
@portal_required
def stay_detail_page(request, pk):
    """Full-page Stay Profile with all requests and totals."""
    hotel = _hotel_or_403(request)
    qs = Stay.objects.select_related("room", "hotel")
    if hotel:
        qs = qs.filter(hotel=hotel)
    stay = get_object_or_404(qs, id=pk)

    reqs = (
        Request.objects
        .filter(stay=stay)
        .select_related("service_item", "room")
        .prefetch_related("lines")
        .order_by("created_at")
    )

    # Only billable (non-cancelled) requests
    billable_qs = reqs.exclude(status="CANCELLED")

    # Totals excluding cancelled
    food_total = sum((r.subtotal or 0) for r in billable_qs if r.kind == "FOOD")
    svc_total  = sum((r.subtotal or 0) for r in billable_qs if r.kind == "SERVICE")
    grand_total = (food_total or 0) + (svc_total or 0)

    # Paid vs unpaid totals
    unpaid_qs = billable_qs.filter(is_paid=False)
    paid_qs   = billable_qs.filter(is_paid=True)

    unpaid_total = sum((r.subtotal or 0) for r in unpaid_qs)
    paid_total   = sum((r.subtotal or 0) for r in paid_qs)

    ctx = {
        "stay": stay,
        "room": stay.room,
        "requests": reqs,
        "food_total": food_total,
        "svc_total": svc_total,
        "grand_total": grand_total,
        "paid_total": paid_total,
        "unpaid_total": unpaid_total,
    }
    return render(request, "hotelportal/stay_detail.html", ctx)









def _q2(val: Decimal) -> Decimal:
    return (val or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

@login_required
@portal_required
def stay_invoice(request, pk):
    """
    Full printable invoice for a Stay:
    - Includes GST settings (number & percent) from HotelBillingSettings
    - Itemizes FOOD lines and SERVICE requests
    - Computes Subtotal, GST, Grand Total
    """
    # Pull the stay + all requests + lines in one shot
    qs = (
        Stay.objects
        .select_related("hotel", "room")
        .prefetch_related(
            Prefetch(
                "request_set",
                queryset=(
                    Request.objects
                    .select_related("service_item")
                    .prefetch_related("lines")
                    .order_by("created_at")
                ),
                to_attr="all_requests"   # -> stay.all_requests
            )
        )
    )
    stay = get_object_or_404(qs, id=pk)

    # Hotel billing settings (may be absent)
    settings_obj = getattr(stay.hotel, "billing_settings", None)
    gst_percent = _q2(getattr(settings_obj, "gst_percent", Decimal("0.00")))
    gst_number  = getattr(settings_obj, "gst_number", "") or ""

    # Which requests count on invoice? (exclude CANCELLED)
    billable = [r for r in (stay.all_requests or []) if r.status != "CANCELLED"]

    # Subtotal = sum of Request.subtotal
    subtotal = _q2(sum((r.subtotal or Decimal("0.00")) for r in billable))

    # Tax (assume everything taxable; you can refine later)
    tax = _q2(subtotal * (gst_percent / Decimal("100")))
    grand_total = _q2(subtotal + tax)

    ctx = {
        "stay": stay,
        "hotel": stay.hotel,
        "room": stay.room,
        "requests": billable,      # each has .lines and .service_item
        "gst_number": gst_number,
        "gst_percent": gst_percent,
        "subtotal": subtotal,
        "tax": tax,
        "grand_total": grand_total,
        # Optional invoice meta (if/when you add numbering & paid flags)
        "invoice_no": getattr(stay, "invoice_no", None),
        "paid_at": getattr(stay, "paid_at", None),
        "payment_mode": getattr(stay, "payment_mode", "") or "",
    }
    return render(request, "hotelportal/invoice.html", ctx)




def _assign_invoice_number_if_needed(stay: Stay):
    """
    Ensure stay has invoice_no, using hotel's HotelBillingSettings sequence.
    """
    if stay.invoice_no:
        return stay.invoice_no

    with transaction.atomic():
        # lock settings row
        settings_obj, _ = HotelBillingSettings.objects.select_for_update().get_or_create(hotel=stay.hotel)
        inv_no = f"{settings_obj.invoice_prefix}-{settings_obj.next_invoice_seq:06d}"
        settings_obj.next_invoice_seq += 1
        settings_obj.save(update_fields=["next_invoice_seq"])

        stay.invoice_no = inv_no
        stay.save(update_fields=["invoice_no"])
        return inv_no
    

@login_required
@portal_required
@transaction.atomic
def stay_mark_paid(request, pk):
    """
    Marks a Stay as paid with chosen payment mode, ensures invoice number.
    Called from stay_detail page or _stay_detail popup.
    """
    stay = get_object_or_404(Stay, id=pk, hotel=request.user.hotel)
    if request.method != "POST":
        return redirect("portal_stay_detail", pk=pk)

    mode = request.POST.get("payment_mode", "").upper()
    if mode not in [c[0] for c in Stay.PAYMENT_CHOICES]:
        messages.error(request, "Invalid payment mode.")
        return redirect("portal_stay_detail", pk=pk)

    # NEW: mark all current non-cancelled requests for this stay as paid
    Request.objects.filter(stay=stay).exclude(status="CANCELLED").update(is_paid=True)

    # Existing logic (invoice, flags, etc.)
    stay.mark_paid(mode)

    messages.success(request, f"Marked Stay #{stay.id} as paid ({mode}).")
    broadcast_portal_board(stay.hotel_id)
    return redirect("portal_stay_detail", pk=pk)



# 10.1B — Billing list with filters + summary
@portal_required
def billing_list(request):
    """
    Stay-level billing list:
    - Shows all stays with total_due > 0
    - Filters: date range, paid/unpaid, search
    - Summary: total stays, total billed, total paid, outstanding
    """
    hotel = _hotel_or_403(request)

    qs = (
        Stay.objects
        .select_related("room", "hotel")
        .filter(total_due__gt=0)  # only stays that have some bill
        .order_by("-created_at")
    )
    if hotel:
        qs = qs.filter(hotel=hotel)

    # --- Filters ---
    # 1) Paid / Unpaid
    paid = (request.GET.get("paid") or "").strip()
    if paid == "paid":
        qs = qs.filter(is_paid=True)
    elif paid == "unpaid":
        qs = qs.filter(is_paid=False)

    # 2) Date range (we’ll use created_at date for now)
    start = (request.GET.get("start") or "").strip()
    end   = (request.GET.get("end") or "").strip()

    if start:
        qs = qs.filter(created_at__date__gte=start)
    if end:
        qs = qs.filter(created_at__date__lte=end)

    # 3) Search: guest / phone / room / invoice
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(guest_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(room__number__icontains=q)
            | Q(invoice_no__icontains=q)
        )

    # --- Summary aggregates ---
    summary = qs.aggregate(
        total_stays=Count("id"),
        total_billed=Sum("total_due"),
        total_paid=Sum("total_due", filter=Q(is_paid=True)),
    )

    total_stays   = summary["total_stays"] or 0
    total_billed  = summary["total_billed"] or Decimal("0.00")
    total_paid    = summary["total_paid"] or Decimal("0.00")
    total_due_out = total_billed - total_paid

    # --- Pagination ---
    paginator = Paginator(qs, 25)
    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    ctx = {
        "page_obj": page_obj,
        "total_stays": total_stays,
        "total_billed": total_billed,
        "total_paid": total_paid,
        "total_due_out": total_due_out,

        # keep current filters in context so template can show them
        "paid": paid,
        "start": start,
        "end": end,
        "q": q,
    }
    return render(request, "hotelportal/billing_list.html", ctx)





# 13.1B — Redirect to WhatsApp Web with pre-filled text
# 13.1B — Redirect to WhatsApp Web with pre-filled text
# 13.1B — Redirect to WhatsApp Web with pre-filled text
@portal_required
def portal_request_whatsapp(request, pk):
    """
    Build a WhatsApp Web URL for a given Request + Template and redirect.

    URL pattern example:
      /portal/requests/<pk>/whatsapp/?template_id=123
    """
    hotel = _hotel_or_403(request)
    if not hotel and getattr(request.user, "role", None) != "PLATFORM_ADMIN":
        return redirect("portal_live")  # adjust if your live-board name is different

    tmpl_id = request.GET.get("template_id")
    if not tmpl_id:
        return redirect("portal_live")

    # Load Request + Template for this hotel
    req_obj = get_object_or_404(Request, pk=pk, hotel=hotel)
    tmpl = get_object_or_404(WhatsAppTemplate, pk=tmpl_id, hotel=hotel, is_active=True)

    stay = req_obj.stay
    room = req_obj.room

    # We need a phone number to send WhatsApp
    if not stay or not stay.phone:
        return redirect("portal_live")

    # --- Build tracking URL for guest summary, with fallbacks ---
    try:
        # 1) Try namespaced pattern (if you ever add app_name = "guest")
        tracking_path = reverse(
            "guest:room_summary",
            kwargs={"hotel_id": hotel.id, "room_id": room.id},
        )
    except NoReverseMatch:
        try:
            # 2) Try non-namespaced name
            tracking_path = reverse(
                "guest_room_summary",
                kwargs={"hotel_id": hotel.id, "room_id": room.id},
            )
        except NoReverseMatch:
            # 3) Fallback to manual path (matches your QR pattern)
            tracking_path = f"/h/{hotel.id}/r/{room.id}/{req_obj.id}/"

    tracking_url = request.build_absolute_uri(tracking_path)

    # Prepare placeholder context
    ctx = {
        "guest_name": stay.guest_name or "",
        "room_number": room.number,
        "hotel_name": hotel.name,
        "tracking_url": tracking_url,
        "request_id": req_obj.id,
    }

    # Render body via .format(), but be safe if placeholder typo
    try:
        body = tmpl.body.format(**ctx)
    except KeyError:
        body = tmpl.body

    # Clean phone (digits only)
    phone_raw = "+91"+stay.phone or ""
    phone_digits = "".join(ch for ch in phone_raw if ch.isdigit())

    # Build WhatsApp Web URL
    query = urlencode(
        {
            "phone": phone_digits,
            "text": body,
        },
        quote_via=quote,
    )
    wa_url = f"https://api.whatsapp.com/send?{query}"

    return redirect(wa_url)





# 13.1C — Room-based WhatsApp (for BUSY rooms / current stay)
@portal_required
def portal_room_whatsapp(request, room_id):
    """
    Send a WhatsApp message for the *current stay* of a room,
    using the selected WhatsAppTemplate.

    Called from BUSY room cards on the Live Board.
    URL example:
      /portal/rooms/12/whatsapp/?template_id=4
    """
    hotel = _hotel_or_403(request)
    # If no hotel bound and not platform admin → bounce somewhere safe
    if not hotel and getattr(request.user, "role", None) != "PLATFORM_ADMIN":
        return redirect("/")

    tmpl_id = request.GET.get("template_id")
    if not tmpl_id:
        return redirect("/")

    # Load the room for this hotel
    room_qs = Room.objects.all()
    if hotel:
        room_qs = room_qs.filter(hotel=hotel)
    room = get_object_or_404(room_qs, id=room_id)

    # Find the current stay for this room
    stay = getattr(room, "current_stay", None) or _get_open_stay(room)
    if not stay or not stay.phone:
        # No active stay or no phone → nothing to do
        return redirect("/")

    # Load template for this hotel
    tmpl = get_object_or_404(WhatsAppTemplate, pk=tmpl_id, hotel=hotel, is_active=True)

    # --- Build tracking URL with same fallbacks as portal_request_whatsapp ---
    try:
        tracking_path = reverse(
            "guest:room_summary",
            kwargs={"hotel_id": hotel.id, "room_id": room.id},
        )
    except NoReverseMatch:
        try:
            tracking_path = reverse(
                "guest_room_summary",
                kwargs={"hotel_id": hotel.id, "room_id": room.id},
            )
        except NoReverseMatch:
            tracking_path = f"/h/{hotel.id}/r/{room.id}/summary/"

    tracking_url = request.build_absolute_uri(tracking_path)

    # Placeholder context (request_id is blank here: this is room-level)
    ctx = {
        "guest_name": stay.guest_name or "",
        "room_number": room.number,
        "hotel_name": hotel.name,
        "tracking_url": tracking_url,
        "request_id": "",   # no specific request tied for room-level messages
    }

    # Format message body, fall back if placeholder typo
    try:
        body = tmpl.body.format(**ctx)
    except KeyError:
        body = tmpl.body

    # Clean phone to digits only
    phone_raw = stay.phone or ""
    phone_digits = "".join(ch for ch in phone_raw if ch.isdigit())

    from urllib.parse import urlencode, quote

    query = urlencode(
        {
            "phone": phone_digits,
            "text": body,
        },
        quote_via=quote,
    )
    wa_url = f"https://api.whatsapp.com/send?{query}"

    return redirect(wa_url)






# 13.2A — Portal WhatsApp template settings (list + add/edit + soft delete)
@portal_required
def portal_whatsapp_templates(request):
    """
    Simple settings screen for hotel-specific WhatsApp templates.
    - GET: show all templates for this hotel
    - POST:
        mode=save   -> create/update (and keep ACTIVE)
        mode=delete -> soft-delete (is_active=False)
    """
    hotel = _hotel_or_403(request)
    if not hotel:
        return HttpResponseForbidden("No hotel set")

    if request.method == "POST":
        mode = (request.POST.get("mode") or "save").strip()
        tmpl_id = (request.POST.get("tmpl_id") or "").strip()

        # -----------------------
        # DISABLE (soft-delete)
        # -----------------------
        if mode == "delete" and tmpl_id:
            WhatsAppTemplate.objects.filter(id=tmpl_id, hotel=hotel).update(is_active=False)
            messages.success(request, "Template disabled successfully.")
            return redirect("portal_whatsapp_templates")

        # -----------------------
        # SAVE (create / update, always ACTIVE)
        # -----------------------
        if mode == "save":
            code     = (request.POST.get("code") or "").strip()
            label    = (request.POST.get("label") or "").strip()
            type_    = (request.POST.get("type") or "GENERIC").strip()
            body     = (request.POST.get("body") or "").strip()
            sort_raw = (request.POST.get("sort_order") or "").strip()

            try:
                sort_order = int(sort_raw or 0)
            except ValueError:
                sort_order = 0

            if not code or not label:
                messages.error(request, "Code and Label are required.")
                return redirect("portal_whatsapp_templates")

            # Existing template?
            if tmpl_id:
                tmpl = get_object_or_404(WhatsAppTemplate, id=tmpl_id, hotel=hotel)
            else:
                # Either create new or reuse same (hotel, code)
                tmpl, _ = WhatsAppTemplate.objects.get_or_create(
                    hotel=hotel,
                    code=code,
                    defaults={
                        "label": label,
                        "type": type_,
                        "body": body,
                        "sort_order": sort_order,
                        "is_active": True,   # new templates start as ACTIVE
                    },
                )

            # Update fields
            tmpl.code       = code
            tmpl.label      = label
            tmpl.type       = type_
            tmpl.body       = body
            tmpl.sort_order = sort_order
            tmpl.is_active  = True      # SAVE always keeps / makes it ACTIVE
            tmpl.save()

            messages.success(request, f"Template “{tmpl.label}” saved.")
            return redirect("portal_whatsapp_templates")

        # Any other mode is invalid
        messages.error(request, "Invalid action.")
        return redirect("portal_whatsapp_templates")

    # -----------------------
    # GET – list all templates for this hotel
    # -----------------------
    templates = (
        WhatsAppTemplate.objects
        .filter(hotel=hotel)
        .order_by("sort_order", "label")
    )
    return render(
        request,
        "hotelportal/whatsapp_templates.html",
        {"templates": templates},
    )



@login_required
def portal_expired_page(request):  # 16.6A
    hotel = getattr(request.user, "hotel", None)
    return render(request, "hotelportal/expired.html", {"hotel": hotel})