from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Hotel, HotelPayment
from django.contrib.auth import get_user_model

class HotelAdminSignupForm(UserCreationForm):
    # hotel fields bundled into signup
    hotel_name = forms.CharField(max_length=150, label="Hotel name")
    city = forms.CharField(max_length=80, required=False)
    phone = forms.CharField(max_length=20, required=False)
    email = forms.EmailField(required=False, help_text="Hotel contact email")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)  # we’ll capture username; email is hotel email here

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "HOTEL_ADMIN"
        # create hotel
        hotel = Hotel.objects.create(
            name=self.cleaned_data["hotel_name"],
            city=self.cleaned_data.get("city", ""),
            phone=self.cleaned_data.get("phone", ""),
            email=self.cleaned_data.get("email", ""),
            status="ACTIVE",
        )
        user.hotel = hotel
        if commit:
            user.save()
        return user






User = get_user_model()

class StaffCreateForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")  # password1/password2 come from UserCreationForm

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = "STAFF"  # hotel will be set in the view for safety
        if commit:
            user.save()
        return user










class PlatformHotelForm(forms.ModelForm):
    class Meta:
        model = Hotel
        fields = [
            # --- General / Identity ---
            "name", "hotel_code", "logo",
            "city", "address", "phone", "email",
            "owner_name", "gst_number", "notes",
            "status",

            # --- WhatsApp staff group ---
            "staff_whatsapp_group_code",

            # --- Platform billing ---
            "billing_start_date",
            "billing_frequency",
            "billing_amount",

            # --- Expiry ---
            "subscription_expires_on",
        ]
        widgets = {
            "billing_start_date": forms.DateInput(attrs={"type": "date"}),
            "subscription_expires_on": forms.DateInput(attrs={"type": "date"}),
        }


class PlatformHotelPaymentForm(forms.ModelForm):
    class Meta:
        model = HotelPayment
        fields = ["date", "amount", "mode", "reference", "notes"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }