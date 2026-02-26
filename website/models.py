# website/models.py  (Day-16 final)

from decimal import Decimal
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from dateutil.relativedelta import relativedelta


class Hotel(models.Model):
    # -----------------------------
    # Basic hotel info
    # -----------------------------
    name = models.CharField(max_length=150)
    city = models.CharField(max_length=80, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    # Existing Scan2Service hotel fields
    gst_number = models.CharField(max_length=30, blank=True, null=True)
    owner_name = models.CharField(max_length=100, blank=True, null=True)
    hotel_code = models.CharField(max_length=20, blank=True, null=True, unique=True)
    logo = models.ImageField(upload_to="hotel_logos/", blank=True, null=True)
    subscription_expires_on = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=[("ACTIVE", "Active"), ("PAUSED", "Paused"), ("DISABLED", "Disabled")],
        default="ACTIVE",
    )

    # 14.x – staff WhatsApp group (invite code for Selenium bot)
    staff_whatsapp_group_code = models.CharField(
        max_length=64,
        blank=True,
        help_text="WhatsApp invite code for staff group (e.g. B78LUcPkZ520TSPRIIcFaV)",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    # -----------------------------
    # 15/16.x – Platform Billing Settings (per hotel)
    # -----------------------------
    BILLING_FREQ_CHOICES = (
        ("MONTHLY", "Monthly"),
        ("YEARLY", "Yearly"),
    )

    billing_start_date = models.DateField(
        blank=True,
        null=True,
        help_text="Date from which platform billing should be calculated.",
    )
    billing_frequency = models.CharField(
        max_length=10,
        choices=BILLING_FREQ_CHOICES,
        default="MONTHLY",
        help_text="Billing frequency for this hotel.",
    )
    billing_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Billing amount per period (e.g. per month or per year).",
    )

    def __str__(self) -> str:
        return f"{self.name} ({self.city})" if self.city else self.name

    # -----------------------------
    # 16.1B — Billing helpers / computed fields
    # -----------------------------

    @property
    def is_converted(self) -> bool:
        """Converted = has at least one payment row."""
        return self.payments.exists()

    def _billing_periods_until(self, as_of=None) -> int:
        """
        Count how many billing cycles started from billing_start_date until as_of (inclusive).
        MONTHLY: counts months
        YEARLY : counts years
        """
        if not self.billing_start_date or self.billing_amount <= 0:
            return 0

        if as_of is None:
            as_of = timezone.localdate()
        else:
            as_of = getattr(as_of, "date", lambda: as_of)()

        start = self.billing_start_date
        if as_of < start:
            return 0

        if self.billing_frequency == "YEARLY":
            years = as_of.year - start.year
            if (as_of.month, as_of.day) >= (start.month, start.day):
                years += 1
            return max(years, 0)

        # Default MONTHLY
        months = (as_of.year - start.year) * 12 + (as_of.month - start.month)
        if as_of.day >= start.day:
            months += 1
        return max(months, 0)

    def billing_expected_amount(self, as_of=None) -> Decimal:
        """
        expected_payment = periods * billing_amount
        """
        if not self.billing_start_date or self.billing_amount <= 0:
            return Decimal("0.00")

        periods = self._billing_periods_until(as_of=as_of)
        return (self.billing_amount * periods).quantize(Decimal("0.01"))

    def total_payment_received(self, as_of=None) -> Decimal:
        """
        total received from billing_start_date until as_of (inclusive)
        """
        if not self.billing_start_date:
            return Decimal("0.00")

        qs = self.payments.filter(date__gte=self.billing_start_date)
        if as_of is not None:
            limit = getattr(as_of, "date", lambda: as_of)()
            qs = qs.filter(date__lte=limit)

        total = qs.aggregate(models.Sum("amount"))["amount__sum"] or Decimal("0.00")
        return Decimal(total).quantize(Decimal("0.01"))

    def net_due(self, as_of=None) -> Decimal:
        """
        net_due = expected - received (never negative)
        """
        exp = self.billing_expected_amount(as_of=as_of)
        got = self.total_payment_received(as_of=as_of)
        diff = exp - got
        if diff < 0:
            diff = Decimal("0.00")
        return diff.quantize(Decimal("0.01"))

    # -----------------------------
    # 16.2C — Extend expiry utility
    # -----------------------------
    def extend_expiry_by_cycles(self, cycles: int):
        """
        Extend expiry date by N cycles based on billing_frequency.
        """
        if cycles <= 0:
            return

        base = self.subscription_expires_on or timezone.localdate()

        if self.billing_frequency == "YEARLY":
            self.subscription_expires_on = base + relativedelta(years=cycles)
        else:
            self.subscription_expires_on = base + relativedelta(months=cycles)

        self.save(update_fields=["subscription_expires_on"])


class User(AbstractUser):
    class Roles(models.TextChoices):
        PLATFORM_ADMIN = "PLATFORM_ADMIN", "Platform Admin"
        HOTEL_ADMIN = "HOTEL_ADMIN", "Hotel Admin"
        STAFF = "STAFF", "Staff"
        GUEST = "GUEST", "Guest"

    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.HOTEL_ADMIN
    )
    hotel = models.ForeignKey(Hotel, null=True, blank=True, on_delete=models.SET_NULL)

    def is_platform_admin(self):
        return self.role == self.Roles.PLATFORM_ADMIN

    def is_hotel_admin(self):
        return self.role == self.Roles.HOTEL_ADMIN

    def is_staff_user(self):
        return self.role == self.Roles.STAFF


class HotelPayment(models.Model):
    MODE_CHOICES = (
        ("PG", "Payment Gateway"),
        ("CASH", "Cash"),
        ("BANK", "Bank Transfer"),
        ("UPI", "UPI"),
        ("OTHER", "Other"),
    )

    hotel = models.ForeignKey(
        "website.Hotel",
        on_delete=models.CASCADE,
        related_name="payments",
    )

    date = models.DateField(
        default=timezone.localdate,
        help_text="Payment date (when money was received).",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mode = models.CharField(max_length=10, choices=MODE_CHOICES, default="PG")
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Transaction ID, bank ref, or any short note.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Optional for Day-17 gateways
    gateway = models.CharField(max_length=30, blank=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.hotel.name} – ₹{self.amount} on {self.date} ({self.mode})"

    # -----------------------------
    # 16.2B — cycles covered by this payment
    # -----------------------------
    def cycles_purchased(self):
        bill_amt = getattr(self.hotel, "billing_amount", None) or Decimal("0.00")
        if bill_amt <= 0:
            return 0
        cycles = int(Decimal(self.amount) / Decimal(bill_amt))
        return max(cycles, 0)

    # -----------------------------
    # 16.2C — Auto extend expiry on new payment
    # -----------------------------
    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)

        if is_new:
            cycles = self.cycles_purchased()
            if cycles > 0:
                self.hotel.extend_expiry_by_cycles(cycles)
