# website/admin.py  (Day-16 final)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, Hotel, HotelPayment


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role", "hotel", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff", "hotel")
    search_fields = ("username", "email")
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Scan2Service", {"fields": ("role", "hotel")}),
    )


@admin.register(Hotel)
class HotelAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "hotel_code",
        "city",
        "status",
        "subscription_expires_on",
        "billing_start_date",
        "billing_frequency",
        "billing_amount",
        "owner_name",
        "gst_number",
        "created_at",
    )
    list_filter = ("status", "city", "subscription_expires_on", "billing_frequency")
    search_fields = ("name", "city", "hotel_code", "gst_number", "owner_name", "email")
    readonly_fields = ("created_at",)

    fieldsets = (
        ("Identity", {"fields": ("name", "hotel_code", "logo")}),
        ("Contact", {"fields": ("city", "address", "phone", "email", "owner_name")}),
        ("Compliance & Notes", {"fields": ("gst_number", "notes")}),

        ("Subscription & Status", {
            "fields": (
                "subscription_expires_on",
                "status",
                "staff_whatsapp_group_code",
            )
        }),

        ("Platform Billing (Admin only)", {
            "fields": (
                "billing_start_date",
                "billing_frequency",
                "billing_amount",
            )
        }),

        ("Timestamps", {"fields": ("created_at",)}),
    )


@admin.register(HotelPayment)
class HotelPaymentAdmin(admin.ModelAdmin):
    list_display = ("hotel", "date", "amount", "mode", "reference", "created_at")
    list_filter = ("mode", "date", "hotel")
    search_fields = ("hotel__name", "reference", "notes")
    autocomplete_fields = ("hotel",)
    date_hierarchy = "date"
