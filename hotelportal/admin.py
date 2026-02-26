from django.contrib import admin, messages
from django.utils.html import mark_safe

from .models import (
    Room,
    Stay,
    Request,
    RequestLine,
    Category,
    ImageAsset,
    Item,
    HotelBillingSettings,
    WhatsAppTemplate,
)


# ----------------------------
# Room / Stay
# ----------------------------

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("hotel", "number", "floor", "status", "is_active", "current_stay")
    list_filter = ("hotel", "status", "is_active")
    search_fields = ("number",)
    ordering = ("hotel", "number")


@admin.register(Stay)
class StayAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hotel",
        "room",
        "guest_name",
        "phone",
        "status",
        "check_in_at",
        "check_out_at",
        "running_total",
    )
    list_filter = ("hotel", "status", "check_in_at")
    search_fields = ("guest_name", "phone")
    readonly_fields = ("check_in_at", "check_out_at", "created_at", "updated_at")
    ordering = ("-check_in_at",)

    @admin.action(description="Mark selected stays as Checked Out")
    def action_mark_checked_out(self, request, queryset):
        count = 0
        for stay in queryset:
            prev = stay.status
            stay.mark_checked_out()
            if prev != "CHECKED_OUT":
                count += 1
        self.message_user(
            request, f"{count} stay(s) marked as Checked Out.", level=messages.SUCCESS
        )

    actions = [action_mark_checked_out]


# ----------------------------
# Catalog admin (Category / Image / Item)
# ----------------------------

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel", "kind", "parent", "position", "is_active", "icon_preview")
    list_filter = ("hotel", "kind", "is_active")
    search_fields = ("name", "hotel__name")
    autocomplete_fields = ("hotel", "parent")
    ordering = ("hotel", "kind", "position", "name")
    fieldsets = (
        (None, {"fields": ("hotel", "name", "kind", "parent", "position", "is_active")}),
        ("Guest-facing", {"fields": ("icon",)}),
    )

    def icon_preview(self, obj):
        if obj.icon:
            return mark_safe(
                f'<img src="{obj.icon.url}" '
                'style="height:24px;width:24px;object-fit:cover;border-radius:4px;" />'
            )
        return "-"
    icon_preview.short_description = "Icon"


@admin.register(ImageAsset)
class ImageAssetAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel", "tags", "created_at")
    list_filter = ("hotel",)
    search_fields = ("name", "tags", "hotel__name")
    autocomplete_fields = ("hotel",)
    ordering = ("hotel", "name")


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "hotel", "category", "price", "is_available", "position")
    list_filter = ("hotel", "category", "is_available")
    search_fields = ("name", "category__name", "hotel__name")
    autocomplete_fields = ("hotel", "category", "image")
    ordering = ("hotel", "category", "position", "name")


# ----------------------------
# Requests & Lines
# ----------------------------

@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "hotel",
        "room",
        "stay",
        "kind",
        "status",
        "subtotal",
        "created_at",
        "accepted_at",
        "completed_at",
    )
    list_filter = ("hotel", "kind", "status", "created_at")
    search_fields = ("room__number", "stay__guest_name", "stay__phone")
    autocomplete_fields = ("hotel", "room", "stay", "service_item")
    ordering = ("-created_at",)


@admin.register(RequestLine)
class RequestLineAdmin(admin.ModelAdmin):
    list_display = ("request", "item", "name_snapshot", "qty", "price_snapshot", "line_total")
    list_filter = ("request__hotel",)
    search_fields = ("name_snapshot", "item__name")
    autocomplete_fields = ("request", "item")


# ----------------------------
# Billing settings
# ----------------------------

@admin.register(HotelBillingSettings)
class HotelBillingSettingsAdmin(admin.ModelAdmin):
    list_display = ("hotel", "gst_number", "gst_percent", "invoice_prefix", "next_invoice_seq")
    autocomplete_fields = ("hotel",)
    search_fields = ("hotel__name", "gst_number")


# ----------------------------
# WhatsApp Templates
# ----------------------------

@admin.register(WhatsAppTemplate)
class WhatsAppTemplateAdmin(admin.ModelAdmin):
    list_display = ("hotel", "label", "code", "type", "is_active", "sort_order")
    list_filter = ("hotel", "type", "is_active")
    search_fields = ("label", "code", "hotel__name")
    autocomplete_fields = ("hotel",)
    ordering = ("hotel", "type", "sort_order")
