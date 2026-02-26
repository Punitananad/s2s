from decimal import Decimal, ROUND_HALF_UP
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from website.models import Hotel


# ----------------------------
# Helpers
# ----------------------------
def _q2(v: Decimal) -> Decimal:
    """Quantize to 2 decimals, HALF_UP, safe for None."""
    return (v or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# -----------------------------------
# Room & Stay (Day-7 groundwork)
# -----------------------------------
class Room(models.Model):
    STATUS_CHOICES = (
        ("FREE", "Free"),
        ("BUSY", "Busy"),
        ("CLEANING", "Cleaning"),
    )

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE)
    number = models.CharField(max_length=20)  # e.g., "101"
    floor = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)

    # live occupancy/tracking
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="FREE")
    current_stay = models.OneToOneField(
        "Stay",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="room_current",
    )

    class Meta:
        unique_together = ("hotel", "number")
        ordering = ("number",)

    def __str__(self):
        return f"{self.hotel.name} - Room {self.number}"

    def can_delete(self):
        return self.current_stay_id is None


class Stay(models.Model):
    STATUS_CHOICES = (
        ("ACTIVE", "Active"),
        ("CHECKED_OUT", "Checked Out"),
    )

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, db_index=True)
    room = models.ForeignKey(Room, on_delete=models.PROTECT, db_index=True)

    guest_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    check_in_at = models.DateTimeField(auto_now_add=True)
    check_out_at = models.DateTimeField(null=True, blank=True)

    # Useful for live totals
    running_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    # --- Billing / Invoice ---
    invoice_no = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    total_due = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    paid_at = models.DateTimeField(null=True, blank=True)
    PAYMENT_CHOICES = (
        ("CASH", "Cash"),
        ("UPI", "UPI"),
        ("CARD", "Card"),
        ("ROOM", "Room Charge"),
        ("OTHER", "Other"),
    )
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_CHOICES, blank=True, default="")
    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "status", "created_at"]),
            models.Index(fields=["hotel", "room", "status"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["hotel", "invoice_no"]),
        ]
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["hotel", "invoice_no"],
                name="uniq_hotel_invoice_no",
                condition=models.Q(invoice_no__isnull=False),
            )
        ]

    def __str__(self):
        return f"Stay #{self.id} — {self.hotel.name} / Room {self.room.number} — {self.get_status_display()}"

    # ---- Validation ----
    def clean(self):
        if self.room and self.room.hotel_id != self.hotel_id:
            raise ValidationError("Stay.hotel must match Stay.room.hotel")
        if self.status == "ACTIVE":
            qs = Stay.objects.filter(hotel_id=self.hotel_id, room_id=self.room_id, status="ACTIVE")
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("This room already has an active stay.")

    # ---- Transitions ----
    def mark_checked_out(self):
        if self.status != "ACTIVE":
            return
        self.status = "CHECKED_OUT"
        self.check_out_at = timezone.now()
        self.save(update_fields=["status", "check_out_at", "updated_at"])

    # ---- Billing helpers ----
    def compute_subtotal(self, include_statuses=None) -> Decimal:
        """
        Sum Request.subtotal for this stay.
        Defaults to NEW/ACCEPTED/COMPLETED; excludes CANCELLED.
        """
        if include_statuses is None:
            include_statuses = ("NEW", "ACCEPTED", "COMPLETED")
        qs = Request.objects.filter(
            hotel=self.hotel, stay=self, status__in=include_statuses
        ).only("subtotal")
        total = Decimal("0.00")
        for r in qs:
            total += (r.subtotal or Decimal("0.00"))
        return _q2(total)

    def effective_gst_percent(self) -> Decimal:
        """
        Read GST % from HotelBillingSettings (defaults to 0.00 if missing).
        """
        settings = getattr(self.hotel, "billing_settings", None)
        if not settings or settings.gst_percent is None:
            return Decimal("0.00")
        return Decimal(settings.gst_percent)

    def compute_totals_with_tax(self):
        """
        Return (subtotal, gst_amount, grand_total).
        """
        subtotal = self.compute_subtotal()
        gst_pct = self.effective_gst_percent()
        gst_amount = _q2(subtotal * gst_pct / Decimal("100.00"))
        grand_total = _q2(subtotal + gst_amount)
        return subtotal, gst_amount, grand_total

    def assign_invoice_number(self):
        """
        Atomically assign an invoice number using HotelBillingSettings sequence.
        Returns the invoice_no.
        """
        if self.invoice_no:
            return self.invoice_no

        with transaction.atomic():
            settings_obj, _ = HotelBillingSettings.objects.select_for_update().get_or_create(
                hotel=self.hotel
            )
            inv_no = f"{settings_obj.invoice_prefix}-{settings_obj.next_invoice_seq:06d}"
            settings_obj.next_invoice_seq += 1
            settings_obj.save(update_fields=["next_invoice_seq"])
            self.invoice_no = inv_no
            self.save(update_fields=["invoice_no"])
            return inv_no

    def refresh_billing_snapshot(self, persist=True) -> Decimal:
        """
        Recalculate totals and update `total_due` (no payment state change).
        """
        _sub, _gst, grand = self.compute_totals_with_tax()
        self.total_due = _q2(grand)
        if persist:
            self.save(update_fields=["total_due", "updated_at"])
        return self.total_due

    def mark_paid(self, mode: str):
        """
        Mark this stay as paid now with given payment mode.
        Ensures invoice_no exists and refreshes total_due snapshot.
        """
        self.refresh_billing_snapshot(persist=False)
        self.payment_mode = mode or ""
        self.paid_at = timezone.now()
        self.is_paid = True
        self.assign_invoice_number()
        self.save(
            update_fields=[
                "total_due",
                "payment_mode",
                "paid_at",
                "is_paid",
                "invoice_no",
                "updated_at",
            ]
        )

    # ---- Keep Room in sync on every save ----
    def save(self, *args, **kwargs):
        is_new = self._state.adding
        if not is_new and self.pk:
            prev = Stay.objects.filter(pk=self.pk).only("status").first()
            previous_status = prev.status if prev else None
        else:
            previous_status = None

        super().save(*args, **kwargs)

        # Sync room state
        rm = self.room
        if self.status == "ACTIVE":
            if rm.current_stay_id != self.id or rm.status != "BUSY":
                rm.current_stay = self
                rm.status = "BUSY"
                rm.save(update_fields=["current_stay", "status"])
        elif self.status == "CHECKED_OUT":
            if rm.current_stay_id == self.id:
                rm.current_stay = None
                rm.status = "CLEANING"
                rm.save(update_fields=["current_stay", "status"])


# ----------------------------
# 4.1A — Catalog models
# ----------------------------
class Category(models.Model):
    KIND_CHOICES = (
        ("FOOD", "Food"),
        ("SERVICE", "Service"),
    )
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=100)
    kind = models.CharField(
        max_length=10,
        choices=KIND_CHOICES,
        default="SERVICE",
        db_index=True,
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )
    position = models.PositiveIntegerField(
        default=0,
        help_text="Ordering within same parent/kind",
    )
    is_active = models.BooleanField(default=True)

    # 🔹 NEW: optional icon per category (used for both Food & Service tabs)
    icon = models.ImageField(
        upload_to="category_icons/",
        null=True,
        blank=True,
        help_text="Square icon for guest bottom category bar.",
    )

    class Meta:
        unique_together = (("hotel", "name", "parent"),)
        ordering = ("position", "name")

    def __str__(self):
        path = f"{self.parent.name} / {self.name}" if self.parent else self.name
        return f"[{self.kind}] {path}"

    def clean(self):
        if self.parent and self.parent.kind != self.kind:
            raise ValidationError("Parent and child categories must be the same kind.")


class ImageAsset(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=120)
    file = models.ImageField(upload_to="item_photos/")
    tags = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("hotel", "name"),)
        ordering = ("name",)

    def __str__(self):
        return self.name


class Item(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    unit = models.CharField(max_length=20, blank=True, help_text="e.g., plate, item, kg")
    description = models.TextField(blank=True)
    image = models.ForeignKey(ImageAsset, null=True, blank=True, on_delete=models.SET_NULL)
    is_available = models.BooleanField(default=True, db_index=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = (("hotel", "category", "name"),)
        indexes = [
            models.Index(fields=["hotel", "is_available"]),
            models.Index(fields=["hotel", "category", "is_available"]),
        ]
        ordering = ("position", "name")

    def __str__(self):
        return f"{self.name} ({self.category.name})"

    def clean(self):
        if self.category and self.hotel_id != self.category.hotel_id:
            raise ValidationError("Item.hotel must match Item.category.hotel")


# ----------------
# 4.4A — Cart
# ----------------
class Cart(models.Model):
    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, db_index=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, db_index=True)
    stay = models.ForeignKey("Stay", on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    status = models.CharField(max_length=12, default="DRAFT")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (("hotel", "room", "stay", "status"),)

    def __str__(self):
        return f"Cart #{self.id} — {self.hotel.name} R{self.room.number} ({self.status})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    qty = models.PositiveIntegerField(default=1)
    price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = (("cart", "item"),)


# --------------------------
# 5.x — Request & Lines
# --------------------------
class Request(models.Model):
    KIND_CHOICES = (
        ("FOOD", "Food"),
        ("SERVICE", "Service"),
    )
    STATUS_CHOICES = (
        ("NEW", "New"),
        ("ACCEPTED", "Accepted"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    )

    hotel = models.ForeignKey(Hotel, on_delete=models.CASCADE, db_index=True)
    room = models.ForeignKey(Room, on_delete=models.PROTECT, db_index=True)
    stay = models.ForeignKey("Stay", on_delete=models.PROTECT, null=True, blank=True, db_index=True)

    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="NEW")

    service_item = models.ForeignKey(
        "Item",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="service_requests",
        help_text="Only set when kind=SERVICE",
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    is_paid = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    note = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["hotel", "status", "updated_at"]),
            models.Index(fields=["hotel", "created_at"]),
            models.Index(fields=["hotel", "kind", "status"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} #{self.id} — R{self.room.number} — {self.get_status_display()}"

    def clean(self):
        if self.room and self.room.hotel_id != self.hotel_id:
            raise ValidationError("Request.hotel must match Request.room.hotel")
        if self.stay and self.stay.hotel_id != self.hotel_id:
            raise ValidationError("Request.hotel must match Request.stay.hotel")
        if self.kind == "SERVICE" and not self.service_item:
            raise ValidationError("Service requests must reference a service item.")
        if self.service_item and self.kind != "SERVICE":
            raise ValidationError("service_item may only be set for SERVICE kind.")
        if self.service_item and self.service_item.hotel_id != self.hotel_id:
            raise ValidationError("Request.hotel must match Request.service_item.hotel")

    def mark_accepted(self):
        self.status = "ACCEPTED"
        self.accepted_at = timezone.now()

    def mark_completed(self):
        self.status = "COMPLETED"
        self.completed_at = timezone.now()

    def mark_cancelled(self):
        self.status = "CANCELLED"
        self.cancelled_at = timezone.now()


class RequestLine(models.Model):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.PROTECT)
    name_snapshot = models.CharField(max_length=120)
    price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    qty = models.PositiveIntegerField(default=1)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = (("request", "item"),)
        indexes = [
            models.Index(fields=["request"]),
        ]

    def __str__(self):
        return f"{self.name_snapshot} × {self.qty} (₹{self.price_snapshot})"


# --- Billing/Invoice settings tied to a Hotel ---
class HotelBillingSettings(models.Model):
    hotel = models.OneToOneField(Hotel, on_delete=models.CASCADE, related_name="billing_settings")
    gst_number = models.CharField(max_length=32, blank=True)
    gst_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    invoice_prefix = models.CharField(max_length=10, default="INV")
    next_invoice_seq = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Hotel Billing Settings"
        verbose_name_plural = "Hotel Billing Settings"

    def __str__(self):
        return f"Billing settings for {self.hotel.name}"

    def next_invoice_number(self) -> str:
        return f"{self.invoice_prefix}-{self.next_invoice_seq:06d}"




class WhatsAppTemplate(models.Model):  # 13.1A
    """
    WhatsApp message templates for guest communication.

    Supported placeholders in `body`:
      {guest_name}   -> Stay.guest_name
      {room_number}  -> Room.number
      {hotel_name}   -> Hotel.name
      {tracking_url} -> e.g. /h/{hotel_id}/r/{room_id}/summary/
      {request_id}   -> Request.id  (if we send per-request)
    """
    TYPE_CHOICES = [
        ("GENERIC", "Generic / Manual"),
        ("ACCEPTED", "Request Accepted"),
        ("REJECTED", "Request Rejected / Cannot Serve"),
        ("COMPLETED", "Request Completed"),
        ("CHECKIN", "Welcome / Check-in"),
        ("CHECKOUT", "Checkout / Goodbye"),
    ]

    hotel = models.ForeignKey(
        Hotel,
        on_delete=models.CASCADE,
        related_name="whatsapp_templates",
    )
    code = models.SlugField(
        max_length=50,
        help_text="Internal code (e.g. accepted, rejected_evening).",
    )
    label = models.CharField(
        max_length=100,
        help_text="Shown in dropdown on Live Board (e.g. 'Accepted – Standard').",
    )
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default="GENERIC",
    )
    body = models.TextField(
        help_text=(
            "Template text with placeholders like "
            "{guest_name}, {room_number}, {hotel_name}, {tracking_url}, {request_id}."
        )
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("hotel", "code")  # each hotel has its own codes
        ordering = ["sort_order", "label"]

    def __str__(self):
        return f"{self.hotel.name} – {self.label}"