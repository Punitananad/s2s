from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from website.forms import StaffCreateForm
from .models import Room, HotelBillingSettings
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
    return render(request, "hotelportal/portal_home.html")



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
            room.save()
            return redirect("rooms_list")
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
def rooms_qr_sheet(request):
    # allow HOTEL_ADMIN, STAFF, PLATFORM_ADMIN to print
    if getattr(request.user, "role", None) not in ("HOTEL_ADMIN", "STAFF", "PLATFORM_ADMIN"):
        return HttpResponseForbidden("Not allowed.")
    hotel = request.user.hotel
    rooms = Room.objects.filter(hotel=hotel, is_active=True).order_by("floor", "number")
    context = {
        "hotel": hotel,
        "rooms": rooms,
        "SITE_URL": settings.SITE_URL,   # 🔸 (not in basic Django, but needed for Scan2Service)
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
