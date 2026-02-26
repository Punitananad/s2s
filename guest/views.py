# guest/views.py — Day-4: live cart with HTML fragments, phone gate OFF

from collections import defaultdict
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseForbidden
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from hotelportal.models import Hotel, Room, Category, Item, Cart, CartItem, Request, RequestLine

from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
 #from .views import _get_or_create_cart, _badge_count 
# guest/views.py

from hotelportal.views_live import _broadcast_live_board  # 11.3A – realtime push to portal


from website.models import Hotel











# ----------------------------------------------------------------------
# 7.x COMMON HELPERS
# ----------------------------------------------------------------------


def _get_guest_phone_cookie(request):
    """Cookie we set after successful phone verification for this room path."""
    return request.COOKIES.get("s2s_phone")


def _current_stay_if_verified(request, room):
    """
    Return room.current_stay ONLY if the cookie matches that stay's phone.
    Otherwise return None.
    """
    stay = getattr(room, "current_stay", None)
    if not stay:
        return None
    phone_cookie = _get_guest_phone_cookie(request)
    if phone_cookie == stay.phone:
        return stay
    return None


def _require_phone_ok(request, hotel, room):
    """
    If the room has an active stay, block the action when cookie != stay.phone.
    This is the server-side protection (7.6).
    Returns JsonResponse(403) if blocked, else None.
    """
    stay = getattr(room, "current_stay", None)
    if not stay:
        return None  # no active stay → allow
    phone_cookie = _get_guest_phone_cookie(request)
    if phone_cookie != stay.phone:
        return JsonResponse({"ok": False, "error": "PHONE_REQUIRED"}, status=403)
    return None


def _get_or_create_cart(hotel, room, stay=None):
    """
    Single place to create/fetch the current cart.
    If stay is provided, cart is linked to that stay.
    """
    cart, _ = Cart.objects.get_or_create(
        hotel=hotel,
        room=room,
        stay=stay,
        status="DRAFT",
    )
    return cart


def _badge_count(cart: Cart) -> int:
    return sum(ci.qty for ci in cart.items.all())


def _render_cart_fragment(cart: Cart) -> HttpResponse:
    items = list(cart.items.select_related("item"))
    total = sum((ci.price_snapshot * ci.qty for ci in items), Decimal("0.00"))

    html = render_to_string(
        "guest/_cart_body.html",
        {"cart": cart, "items": items, "total": total},
    )
    resp = HttpResponse(html)
    # Total items
    resp["X-Cart-Count"] = str(_badge_count(cart))
    # Total amount (for mini cart bar)
    resp["X-Cart-Total"] = str(total.quantize(Decimal("0.01")))
    return resp


# ----------------------------------------------------------------------
# PHONE VERIFY (7.3)
# ----------------------------------------------------------------------


@require_POST
def verify_phone(request, hotel_id, room_id):
    """
    Guest enters phone in modal → we check against current_stay.phone.
    If OK → we set s2s_phone cookie scoped to /h/<id>/r/<id>/ for 7 days.
    """
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)
    stay = getattr(room, "current_stay", None)

    phone = (request.POST.get("phone") or "").strip()
    if not stay:
        return JsonResponse({"ok": False, "error": "NO_STAY"})
    if not phone:
        return JsonResponse({"ok": False, "error": "EMPTY_PHONE"})
    if phone != stay.phone:
        return JsonResponse({"ok": False, "error": "MISMATCH"})

    resp = JsonResponse({"ok": True})
    resp.set_cookie(
        "s2s_phone",
        phone,
        max_age=7 * 24 * 3600,  # 7 days
        samesite="Lax",
        path=f"/h/{hotel.id}/r/{room.id}/",
    )
    return resp


# ----------------------------------------------------------------------
# MAIN ROOM PAGE
# ----------------------------------------------------------------------


@ensure_csrf_cookie
def room_view(request, hotel_id, room_id):
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)

    cats = Category.objects.filter(
        hotel=hotel,
        is_active=True,
    ).select_related("parent").order_by("position", "name")

    items = Item.objects.filter(
        hotel=hotel,
        is_available=True,
    ).select_related("category", "image").order_by("position", "name")

    from collections import defaultdict
    items_by_cat = defaultdict(list)
    for it in items:
        items_by_cat[it.category_id].append(it)

    children = defaultdict(list)
    top_food, top_service = [], []
    for c in cats:
        if c.parent_id:
            children[c.parent_id].append(c)
        else:
            (top_food if c.kind == "FOOD" else top_service).append(c)

    # 👇 NEW: flattened lists for bottom category bar (food / service)
    food_categories = [c for c in cats if c.kind == "FOOD"]
    service_categories = [c for c in cats if c.kind == "SERVICE"]

    # ----- Day-7 phone gate -----
    stay = getattr(room, "current_stay", None)
    needs_phone = bool(stay)
    phone_cookie = _get_guest_phone_cookie(request)
    phone_verified = bool(needs_phone and phone_cookie == (stay.phone if stay else None))

    # guest name only if verified
    guest_name = ""
    if phone_verified and stay and getattr(stay, "guest_name", None):
        guest_name = stay.guest_name
    elif phone_verified and stay and getattr(stay, "name", None):
        guest_name = stay.name

    # cart: stay-bound if verified
    cart = _get_or_create_cart(hotel, room, stay=stay if phone_verified else None)

    ctx = dict(
        hotel=hotel,
        room=room,
        top_food=top_food,
        top_service=top_service,
        children=children,
        items_by_cat=items_by_cat,
        food_categories=food_categories,      # 👈 NEW
        service_categories=service_categories,  # 👈 NEW
        cart_count=_badge_count(cart),
        needs_phone=needs_phone,
        phone_verified=phone_verified,
        has_stay=bool(stay),
        guest_name=guest_name,
    )
    return render(request, "guest/room.html", ctx)


# ----------------------------------------------------------------------
# CART ENDPOINTS (VIEW / ADD / UPDATE / CLEAR)
# all of these are 7.6-protected now.
# ----------------------------------------------------------------------


@require_GET
def cart_view(request, hotel_id, room_id):
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)

    # if verified, load stay-bound cart
    stay = _current_stay_if_verified(request, room)
    cart = _get_or_create_cart(hotel, room, stay=stay)
    return _render_cart_fragment(cart)


@require_POST
def cart_add(request, hotel_id, room_id):
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)

    # 7.6 guard
    blocked = _require_phone_ok(request, hotel, room)
    if blocked:
        return blocked

    item_id = request.POST.get("item_id")
    qty = int(request.POST.get("qty", "1") or "1")
    if not item_id:
        return HttpResponseBadRequest("Missing item_id")
    if qty < 1:
        qty = 1

    item = get_object_or_404(Item, id=item_id, hotel=hotel, is_available=True)

    # if verified → tie cart to stay
    stay = _current_stay_if_verified(request, room)
    cart = _get_or_create_cart(hotel, room, stay=stay)

    with transaction.atomic():
        ci, created = CartItem.objects.select_for_update().get_or_create(
            cart=cart,
            item=item,
            defaults={"qty": qty, "price_snapshot": item.price},
        )
        if not created:
            ci.qty += qty
            ci.save(update_fields=["qty"])

    return _render_cart_fragment(cart)


@require_POST
def cart_update(request, hotel_id, room_id):
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)

    # 7.6 guard
    blocked = _require_phone_ok(request, hotel, room)
    if blocked:
        return blocked

    item_id = request.POST.get("item_id")
    qty = int(request.POST.get("qty", "1") or "1")
    if not item_id:
        return HttpResponseBadRequest("Missing item_id")

    stay = _current_stay_if_verified(request, room)
    cart = _get_or_create_cart(hotel, room, stay=stay)

    ci = get_object_or_404(CartItem, cart=cart, item_id=item_id)

    if qty <= 0:
        ci.delete()
    else:
        ci.qty = qty
        ci.save(update_fields=["qty"])

    return _render_cart_fragment(cart)


@require_POST
def cart_clear(request, hotel_id, room_id):
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)

    # 7.6 guard
    blocked = _require_phone_ok(request, hotel, room)
    if blocked:
        return blocked

    stay = _current_stay_if_verified(request, room)
    cart = _get_or_create_cart(hotel, room, stay=stay)
    cart.items.all().delete()
    return _render_cart_fragment(cart)


# ----------------------------------------------------------------------
# ORDER SUBMIT (cart → Request + RequestLines)
# now properly ties to stay (7.4)
# ----------------------------------------------------------------------


@require_POST
def order_submit_stub(request, hotel_id, room_id):
    """
    Convert DRAFT cart → Request(kind=FOOD, status=NEW) and tie it to the
    verified stay (7.4). Also capture guest 'note' (order-level) from POST.
    """
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)

    # 7.6 guard
    blocked = _require_phone_ok(request, hotel, room)
    if blocked:
        return blocked

    # tie to verified stay
    stay = _current_stay_if_verified(request, room)

    # read optional note (limit to 200 to match model)
    note_txt = (request.POST.get("note") or "").strip()
    if len(note_txt) > 200:
        note_txt = note_txt[:200]

    cart = Cart.objects.filter(
        hotel=hotel,
        room=room,
        stay=stay,
        status="DRAFT",
    ).first()
    if not cart or not cart.items.exists():
        return JsonResponse({"ok": False, "error": "empty_cart"}, status=400)

    with transaction.atomic():
        subtotal = Decimal("0.00")
        for ci in cart.items.all():
            subtotal += ci.price_snapshot * ci.qty

        req = Request.objects.create(
            hotel=hotel,
            room=room,
            stay=stay,          # request belongs to this stay (7.4)
            kind="FOOD",
            status="NEW",
            subtotal=subtotal,
            note=note_txt or "",  # store guest note (empty string is fine for CharField)
        )

        lines = []
        for ci in cart.items.select_related("item"):
            lines.append(
                RequestLine(
                    request=req,
                    item=ci.item,
                    name_snapshot=ci.item.name,
                    price_snapshot=ci.price_snapshot,
                    qty=ci.qty,
                    line_total=ci.price_snapshot * ci.qty,
                )
            )
        RequestLine.objects.bulk_create(lines)

        # clear / mark cart
        cart.items.all().delete()
        cart.delete()
        #cart.status = "SUBMITTED"
        #cart.save(update_fields=["status"])
    _broadcast_live_board(hotel)
    return JsonResponse({"ok": True, "request_id": req.id})


# ----------------------------------------------------------------------
# SERVICE REQUEST (non-cart)
# also ties to stay if verified (7.4)
# ----------------------------------------------------------------------


@require_POST
def service_request(request, hotel_id, room_id):
    """
    Create a SERVICE Request tied to the verified stay (if any),
    prevent duplicate NEW/ACCEPTED for same service_item,
    and capture an optional guest 'note' from POST.
    """
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room  = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)

    # 7.6 guard
    blocked = _require_phone_ok(request, hotel, room)
    if blocked:
        return blocked

    item_id = request.POST.get("item_id")
    if not item_id:
        return HttpResponseBadRequest("Missing item_id")

    item = get_object_or_404(Item, id=item_id, hotel=hotel, is_available=True)
    if item.category.kind != "SERVICE":
        return JsonResponse({"ok": False, "error": "not_a_service"}, status=400)

    # prevent duplicate active service
    open_exists = Request.objects.filter(
        hotel=hotel,
        room=room,
        kind="SERVICE",
        service_item=item,
        status__in=["NEW", "ACCEPTED"],
    ).exists()
    if open_exists:
        return JsonResponse({"ok": False, "error": "already_requested"}, status=409)

    # tie to verified stay
    stay = _current_stay_if_verified(request, room)

    # read optional note (limit to 200)
    note_txt = (request.POST.get("note") or "").strip()
    if len(note_txt) > 200:
        note_txt = note_txt[:200]

    price = item.price if item.price is not None else Decimal("0.00")
    req = Request.objects.create(
        hotel=hotel,
        room=room,
        stay=stay,
        kind="SERVICE",
        status="NEW",
        subtotal=price,
        service_item=item,     # this carries the service identity
        note=note_txt or "",   # this is the guest’s note (no longer item name)
    )
    _broadcast_live_board(hotel)
    return JsonResponse({"ok": True, "request_id": req.id})


# ----------------------------------------------------------------------
# GUEST SUMMARY (for "My services" modal poll)
# ----------------------------------------------------------------------


@require_GET
def guest_summary(request, hotel_id, room_id):
    hotel = get_object_or_404(Hotel, id=hotel_id, status="ACTIVE")
    room  = get_object_or_404(Room, id=room_id, hotel=hotel, is_active=True)

    stay = getattr(room, "current_stay", None)
    phone_cookie = _get_guest_phone_cookie(request)

    if stay and phone_cookie == stay.phone:
        # ✅ guest is verified for THIS stay → show ONLY this stay
        qs = (Request.objects
              .filter(hotel=hotel, room=room, stay=stay)
              .select_related("room", "service_item")
              .prefetch_related("lines")
              .order_by("-created_at")[:100])
    else:
        # fallback (old behaviour)
        since = timezone.now() - timezone.timedelta(days=1)
        qs = (Request.objects
              .filter(hotel=hotel, room=room, created_at__gte=since)
              .select_related("room", "service_item")
              .prefetch_related("lines")
              .order_by("-created_at")[:100])

    food, services = [], []
    for r in qs:
        if r.kind == "FOOD":
            food.append({
                "request_id": r.id,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "cancelled_at": r.cancelled_at.isoformat() if r.cancelled_at else None,
                "subtotal": float(r.subtotal or 0),
                "lines": [{"name": ln.name_snapshot, "qty": ln.qty} for ln in r.lines.all()],
            })
        else:
            nm = (r.service_item.name if r.service_item else (r.note or "Service"))
            services.append({
                "request_id": r.id,
                "name": nm,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "cancelled_at": r.cancelled_at.isoformat() if r.cancelled_at else None,
            })

    return JsonResponse({"ok": True, "food": food, "services": services})


# ----------------------------------------------------------------------
# OPTIONAL: tiny stub so template calls don't explode
# ----------------------------------------------------------------------


@require_GET
def cart_mini(request):
    """
    If you don’t use this, you can delete this view and the URL.
    Right now it just returns an empty cart partial.
    """
    html = render_to_string(
        "guest/_cart_body.html",
        {"cart": None, "items": [], "total": Decimal("0.00")},
    )
    return HttpResponse(html)




# 13.2B — Guest-facing per-request tracking page
def request_tracking(request, hotel_id, room_id, request_id):
    hotel = get_object_or_404(Hotel, id=hotel_id)
    room = get_object_or_404(Room, id=room_id, hotel=hotel)

    req_obj = get_object_or_404(
        Request.objects.select_related("hotel", "room", "stay").prefetch_related("lines"),
        id=request_id,
        hotel=hotel,
        room=room,
    )

    ctx = {
        "hotel": hotel,
        "room": room,
        "req": req_obj,
    }
    return render(request, "guest/request_tracking.html", ctx)