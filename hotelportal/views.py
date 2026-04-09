from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from website.forms import StaffCreateForm
from .models import Room, HotelBillingSettings, Stay, Request
from .forms import RoomForm
from django.views.decorators.http import require_POST
from django.conf import settings
from django.db.models import Prefetch
from .forms import CategoryForm, ItemForm, InvoiceSettingsForm
from .models import Category, Item, ImageAsset
from django.db import IntegrityError, transaction
from hotelportal.decorators import portal_required
from django.urls import reverse
from django.db.models.deletion import ProtectedError












@login_required
def portal_home(request):
    # allow HOTEL_ADMIN or STAFF
    if getattr(request.user, "role", None) not in ("HOTEL_ADMIN", "STAFF", "PLATFORM_ADMIN"):
        return HttpResponseForbidden("Not allowed.")
    hotel = getattr(request.user, "hotel", None)
    ctx = {}
    if hotel:
        rooms        = Room.objects.filter(hotel=hotel)
        total_rooms  = rooms.count()
        active_rooms = rooms.filter(is_active=True).count()
        active_stays = Stay.objects.filter(hotel=hotel, status="ACTIVE").count()
        open_requests = Request.objects.filter(hotel=hotel, status__in=("NEW", "ACCEPTED")).count()
        unpaid_count = Stay.objects.filter(hotel=hotel, status="CHECKED_OUT", is_paid=False).count()
        _User = get_user_model()
        staff_count  = _User.objects.filter(hotel=hotel, role="STAFF").count()

        ctx["stats"] = {
            "total_rooms":   total_rooms,
            "active_rooms":  active_rooms,
            "active_stays":  active_stays,
            "open_requests": open_requests,
            "unpaid_count":  unpaid_count,
            "staff_count":   staff_count,
            "free_rooms":    rooms.filter(status="FREE").count(),
            "busy_rooms":    rooms.filter(status="BUSY").count(),
            "cleaning_rooms":rooms.filter(status="CLEANING").count(),
        }
    return render(request, "hotelportal/portal_home.html", ctx)



User = get_user_model()

def _is_portal_user(user):
    return getattr(user, "role", None) in ("HOTEL_ADMIN", "PLATFORM_ADMIN")

@login_required
@portal_required
def portal_settings(request):
    if not _is_portal_user(request.user) and request.user.role != "STAFF":
        return HttpResponseForbidden("Not allowed.")
    return render(request, "hotelportal/settings.html")

@login_required
def staff_list(request):
    if not _is_portal_user(request.user):
        return HttpResponseForbidden("Not allowed.")
    staff = User.objects.filter(hotel=request.user.hotel).order_by("username")
    return render(request, "hotelportal/staff_list.html", {"staff": staff})

@login_required
def staff_add(request):
    if getattr(request.user, "role", None) not in ("HOTEL_ADMIN", "PLATFORM_ADMIN"):
        return HttpResponseForbidden("Only hotel admins can add staff.")
    if request.method == "POST":
        form = StaffCreateForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.hotel = request.user.hotel  # bind to same hotel (critical)
            user.save()
            messages.success(request, f"Staff user “{user.username}” created.")
            return redirect("staff_list")
    else:
        form = StaffCreateForm()
    return render(request, "hotelportal/staff_add.html", {"form": form})


@login_required
def rooms_list(request):
    if not _is_portal_user(request.user) and request.user.role != "STAFF":
        return HttpResponseForbidden("Not allowed.")
    rooms = Room.objects.filter(hotel=request.user.hotel).order_by("floor", "number")
    return render(request, "hotelportal/rooms_list.html", {"rooms": rooms})


@login_required
def room_create(request):
    if not _is_portal_user(request.user):  # hotel admin or platform admin only
        return HttpResponseForbidden("Only hotel admins can add rooms.")
    if request.method == "POST":
        form = RoomForm(request.POST)
        if form.is_valid():
            room = form.save(commit=False)
            room.hotel = request.user.hotel
            try:
                room.save()
                messages.success(request, f"Room {room.number} created successfully.")
                return redirect("rooms_list")
            except IntegrityError:
                messages.error(request, f"Room {room.number} already exists for this hotel. Please use a different room number.")
                return render(request, "hotelportal/room_form.html", {"form": form, "mode": "create"})
    else:
        form = RoomForm()
    return render(request, "hotelportal/room_form.html", {"form": form, "mode": "create"})


@login_required
def room_edit(request, pk):
    if not _is_portal_user(request.user):
        return HttpResponseForbidden("Only hotel admins can edit rooms.")
    room = get_object_or_404(Room, pk=pk, hotel=request.user.hotel)
    if request.method == "POST":
        form = RoomForm(request.POST, instance=room)
        if form.is_valid():
            form.save()
            return redirect("rooms_list")
    else:
        form = RoomForm(instance=room)
    return render(request, "hotelportal/room_form.html", {"form": form, "mode": "edit", "room": room})



@login_required
@require_POST
def room_delete(request, pk):
    # Only hotel/platform admins can delete
    if not _is_portal_user(request.user):
        return HttpResponseForbidden("Only hotel admins can delete rooms.")
    room = get_object_or_404(Room, pk=pk, hotel=request.user.hotel)
    if room.current_stay:
        messages.error(request, "Cannot delete: room has an active stay. Check out first.")
        return redirect("rooms_list")
    number = room.number
    room.delete()  # CASCADE wipes related Stays (and later Requests)
    messages.success(request, f"Room {number} deleted permanently.")
    return redirect("rooms_list")


@login_required
def room_generator(request):
    """Bulk room creation: Single / Range / Floor / Custom."""
    if not _is_portal_user(request.user):
        return HttpResponseForbidden("Only hotel admins can generate rooms.")

    hotel = request.user.hotel

    if request.method != "POST":
        return render(request, "hotelportal/room_generator.html")

    method = request.POST.get("method", "single")
    is_active = request.POST.get("is_active") == "on"
    rooms_to_create = []   # list of {"number": str, "floor": str}
    error = None

    # ── Method 1: Single ──────────────────────────────────
    if method == "single":
        number = request.POST.get("number", "").strip()
        floor  = request.POST.get("floor", "").strip()
        if not number:
            error = "Room number is required."
        else:
            rooms_to_create = [{"number": number, "floor": floor}]

    # ── Method 2: Range ───────────────────────────────────
    elif method == "range":
        floor = request.POST.get("range_floor", "").strip()
        try:
            start = int(request.POST.get("range_start", ""))
            end   = int(request.POST.get("range_end", ""))
            if start > end:
                error = "Start must be ≤ End."
            elif (end - start + 1) > 500:
                error = "Range too large — max 500 rooms at once."
            else:
                rooms_to_create = [
                    {"number": str(n), "floor": floor}
                    for n in range(start, end + 1)
                ]
        except (ValueError, TypeError):
            error = "Enter valid integer start and end numbers."

    # ── Method 3: Floor generator ─────────────────────────
    elif method == "floor":
        try:
            floor_start     = int(request.POST.get("floor_start", ""))
            floor_end       = int(request.POST.get("floor_end", ""))
            rooms_per_floor = int(request.POST.get("rooms_per_floor", ""))
            fmt             = request.POST.get("floor_format", "A")

            if floor_start > floor_end:
                error = "Floor start must be ≤ Floor end."
            elif not (1 <= rooms_per_floor <= 99):
                error = "Rooms per floor must be between 1 and 99."
            elif (floor_end - floor_start + 1) * rooms_per_floor > 500:
                error = "Too many rooms — max 500 at once."
            else:
                for f in range(floor_start, floor_end + 1):
                    for r in range(1, rooms_per_floor + 1):
                        if fmt == "A":
                            # e.g. floor 1, room 3 → "103"
                            number = f"{f}{r:02d}"
                        else:
                            # e.g. floor 1 → 'A', room 3 → "A3"
                            letter = chr(ord("A") + (f - floor_start))
                            number = f"{letter}{r}"
                        rooms_to_create.append({"number": number, "floor": str(f)})
        except (ValueError, TypeError):
            error = "Enter valid numbers for floor range and rooms per floor."

    # ── Method 4: Custom list ─────────────────────────────
    elif method == "custom":
        floor = request.POST.get("custom_floor", "").strip()
        raw   = request.POST.get("custom_list", "")
        # accept comma or newline separated
        numbers = [
            n.strip()
            for n in raw.replace("\n", ",").replace(";", ",").split(",")
            if n.strip()
        ]
        if not numbers:
            error = "Enter at least one room number."
        elif len(numbers) > 500:
            error = "Too many rooms — max 500 at once."
        else:
            rooms_to_create = [{"number": n, "floor": floor} for n in numbers]

    # ── Validation error ──────────────────────────────────
    if error:
        messages.error(request, error)
        return render(request, "hotelportal/room_generator.html")

    # ── Deduplicate within input ──────────────────────────
    seen, unique = set(), []
    for r in rooms_to_create:
        if r["number"] not in seen:
            seen.add(r["number"])
            unique.append(r)

    # ── Find already-existing rooms ───────────────────────
    existing = set(
        Room.objects.filter(hotel=hotel, number__in=seen)
                    .values_list("number", flat=True)
    )
    to_create = [r for r in unique if r["number"] not in existing]
    skipped   = [r["number"] for r in unique if r["number"] in existing]

    if not to_create:
        messages.warning(
            request,
            f"All {len(unique)} room(s) already exist — nothing created."
            + (f" Existing: {', '.join(list(existing)[:10])}" if existing else ""),
        )
        return redirect("rooms_list")

    # ── Bulk create inside a transaction ──────────────────
    with transaction.atomic():
        Room.objects.bulk_create([
            Room(hotel=hotel, number=r["number"], floor=r["floor"], is_active=is_active)
            for r in to_create
        ])

    msg = f"{len(to_create)} room(s) created successfully."
    if skipped:
        shown = ", ".join(skipped[:10])
        extra = f" and {len(skipped) - 10} more" if len(skipped) > 10 else ""
        msg += f"  ({len(skipped)} already existed and were skipped: {shown}{extra})"
    messages.success(request, msg)
    return redirect("rooms_list")


@login_required
def rooms_qr_sheet(request):
    # allow HOTEL_ADMIN, STAFF, PLATFORM_ADMIN to print
    if getattr(request.user, "role", None) not in ("HOTEL_ADMIN", "STAFF", "PLATFORM_ADMIN"):
        return HttpResponseForbidden("Not allowed.")
    hotel = request.user.hotel
    rooms = Room.objects.filter(hotel=hotel, is_active=True).order_by("floor", "number")
    context = {
        "hotel": hotel,
        "rooms": rooms,
        "SITE_URL": settings.SITE_URL.rstrip("/"),   # strip trailing slash to avoid //h/... double-slash URLs
    }
    return render(request, "hotelportal/rooms_qr_sheet.html", context)









# 4.2B — Catalog views


#this function is getting used twice..
def _is_admin(user):
    return getattr(user, "role", None) in ("HOTEL_ADMIN", "PLATFORM_ADMIN")

# Categories
@login_required
def categories_list(request):
    if not (_is_admin(request.user) or request.user.role == "STAFF"):
        return HttpResponseForbidden("Not allowed.")
    qs = (Category.objects
          .filter(hotel=request.user.hotel)
          .select_related("parent")
          .order_by("kind", "parent__name", "position", "name"))
    return render(request, "hotelportal/categories_list.html", {"categories": qs})


@login_required
def category_create(request):
    if not _is_admin(request.user):
        return HttpResponseForbidden("Only admins can add categories.")
    if not getattr(request.user, "hotel", None):
        return HttpResponseForbidden("Your user is not linked to a hotel.")

    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.hotel = request.user.hotel
            cat.save()
            messages.success(request, "Category created.")
            return redirect("categories_list")
    else:
        form = CategoryForm(request=request)

    return render(request, "hotelportal/category_form.html", {"form": form, "mode": "create"})


@login_required
def category_edit(request, pk):
    if not _is_admin(request.user):
        return HttpResponseForbidden("Only admins can edit categories.")
    obj = get_object_or_404(Category, pk=pk, hotel=request.user.hotel)

    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES, instance=obj, request=request)
        if form.is_valid():
            cat = form.save(commit=False)
            cat.hotel = request.user.hotel
            cat.save()
            messages.success(request, "Category updated.")
            return redirect("categories_list")
    else:
        form = CategoryForm(instance=obj, request=request)

    return render(
        request,
        "hotelportal/category_form.html",
        {"form": form, "mode": "edit", "obj": obj},
    )


@login_required
@require_POST
def category_delete(request, pk):
    if not _is_admin(request.user):
        return HttpResponseForbidden("Only admins can delete categories.")
    obj = get_object_or_404(Category, pk=pk, hotel=request.user.hotel)
    obj.delete()
    messages.success(request, "Category deleted.")
    return redirect("categories_list")
# Items
@login_required
def items_list(request):
    """
    Show all items for the current hotel, filtered only by kind:
    - kind=FOOD    -> all food items
    - kind=SERVICE -> all service items

    No per-category filter. Items are grouped in the table by category name.
    """
    if not (_is_admin(request.user) or request.user.role == "STAFF"):
        return HttpResponseForbidden("Not allowed.")

    hotel = request.user.hotel

    # kind filter: FOOD / SERVICE, default FOOD
    kind = request.GET.get("kind") or "FOOD"
    if kind not in ("FOOD", "SERVICE"):
        kind = "FOOD"

    # Fetch items for this hotel + kind
    items = (
        Item.objects
        .filter(hotel=hotel, category__kind=kind)
        .select_related("category", "image")
        .order_by("category__position", "category__name", "position", "name")
    )

    ctx = {
        "items": items,
        "current_kind": kind,
    }
    return render(request, "hotelportal/items_list.html", ctx)
@login_required
def item_create(request):
    if not _is_portal_user(request.user):
        return HttpResponseForbidden("Only admins can add items.")
    if request.method == "POST":
        form = ItemForm(request.POST, request.FILES, request=request)
        if form.is_valid():
            item = form.save(commit=False)
            item.hotel = request.user.hotel                  # ← critical line
            if item.category.hotel_id != item.hotel_id:
                form.add_error("category", "Selected category belongs to a different hotel.")
            else:
                item.save()
                messages.success(request, "Item created.")
                return redirect("items_list")
    else:
        form = ItemForm(request=request)
    return render(request, "hotelportal/item_form.html", {"form": form, "mode": "create"})


@login_required
def item_edit(request, pk):
    if not _is_portal_user(request.user):
        return HttpResponseForbidden("Only admins can edit items.")
    obj = get_object_or_404(Item, pk=pk, hotel=request.user.hotel)
    if request.method == "POST":
        form = ItemForm(request.POST, request.FILES, instance=obj, request=request)
        if form.is_valid():
            item = form.save(commit=False)
            item.hotel = request.user.hotel                  # ← critical line
            if item.category.hotel_id != item.hotel_id:
                form.add_error("category", "Selected category belongs to a different hotel.")
            else:
                item.save()
                messages.success(request, "Item updated.")
                return redirect("items_list")
    else:
        form = ItemForm(instance=obj, request=request)
    return render(request, "hotelportal/item_form.html", {"form": form, "mode": "edit", "obj": obj})


@login_required
@require_POST
def item_delete(request, pk):
    if not _is_portal_user(request.user):
        return HttpResponseForbidden("Only hotel admins can delete items.")

    obj = get_object_or_404(Item, pk=pk, hotel=request.user.hotel)

    # where to go back after delete
    next_url = request.POST.get("next")
    if not next_url:
        # fallback: keep same kind tab open
        kind = getattr(obj.category, "kind", "FOOD")
        next_url = f"{reverse('items_list')}?kind={kind}"

    name = obj.name

    try:
        obj.delete()
        messages.success(request, f"Item '{name}' deleted permanently.")
    except ProtectedError:
        messages.error(
            request,
            f"Cannot delete '{name}' because it is used in past orders. "
            "Please mark it as Not available instead."
        )

    return redirect(next_url)

@login_required
@portal_required
def settings_invoice(request):
    hotel = getattr(request.user, "hotel", None)
    if not hotel:
        return redirect("portal_home")

    settings_obj, _ = HotelBillingSettings.objects.get_or_create(hotel=hotel)

    if request.method == "POST":
        form = InvoiceSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Invoice settings updated.")
            return redirect("settings_invoice")
    else:
        form = InvoiceSettingsForm(instance=settings_obj)

    return render(request, "hotelportal/settings_invoice.html", {"form": form})





@login_required
@require_POST
def item_toggle_available(request, pk):
    """
    Flip is_available for an item (Available <-> Not available) in one click.
    Only admins + staff can do this.
    """
    if not (_is_admin(request.user) or request.user.role == "STAFF"):
        return HttpResponseForbidden("Not allowed.")

    hotel = getattr(request.user, "hotel", None)
    obj = get_object_or_404(Item, pk=pk, hotel=hotel)

    # Flip availability
    obj.is_available = not obj.is_available
    obj.save(update_fields=["is_available"])

    # Keep user on same kind tab (FOOD/SERVICE) after toggle
    kind = obj.category.kind
    next_url = request.POST.get("next") or f"{reverse('items_list')}?kind={kind}"
    return redirect(next_url)
