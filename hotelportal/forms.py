from django import forms
from .models import Room


from django.core.exceptions import ValidationError  # 4.2A — Catalog forms
from .models import Category, Item, ImageAsset, HotelBillingSettings       # 4.2A — Catalog forms

class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ["number", "floor", "is_active"]













# 4.2A — Catalog forms



class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name", "kind", "parent", "position", "is_active", "icon"]

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # ---- Parent choices: same hotel, same kind (like before) ----
        hotel = getattr(getattr(self.request, "user", None), "hotel", None) if self.request else None
        kind = self.initial.get("kind") or (self.instance.kind if self.instance.pk else None)

        parent_qs = Category.objects.none()
        if hotel:
            parent_qs = Category.objects.filter(hotel=hotel)
            if kind:
                parent_qs = parent_qs.filter(kind=kind)
        self.fields["parent"].queryset = parent_qs

        # Optional: some basic widgets
        self.fields["name"].widget.attrs.update({"class": "form-control"})
        self.fields["kind"].widget.attrs.update({"class": "form-select"})
        self.fields["parent"].widget.attrs.update({"class": "form-select"})
        self.fields["position"].widget.attrs.update({"class": "form-control"})
        self.fields["is_active"].widget.attrs.update({"class": "form-check-input"})
        self.fields["icon"].widget.attrs.update({"class": "form-control"})

        # Make icon clearly optional
        self.fields["icon"].required = False
        self.fields["icon"].help_text = "Optional square icon for guest category bar."

    def save(self, commit=True):
        obj = super().save(commit=False)

        # Bind hotel from logged-in user
        if self.request:
            obj.hotel = self.request.user.hotel

        # Parent safety
        if obj.parent and (obj.parent.hotel_id != obj.hotel_id or obj.parent.kind != obj.kind):
            raise ValidationError("Parent must be same hotel and kind.")

        if commit:
            obj.save()
        return obj

class ItemForm(forms.ModelForm):
    # Choose existing photo OR upload new (we’ll create ImageAsset behind the scenes)
    image_existing = forms.ModelChoiceField(
        queryset=ImageAsset.objects.none(), required=False, label="Choose existing photo"
    )
    image_upload = forms.ImageField(required=False, label="Or upload new photo")

    class Meta:
        model = Item
        fields = ["category", "name", "price", "unit", "description", "is_available", "position"]

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        hotel = getattr(getattr(self.request, "user", None), "hotel", None) if self.request else None

        if hotel and not self.instance.pk:
            self.instance.hotel = hotel

        # Limit categories to this hotel and active ones
        cat_qs = Category.objects.none()
        img_qs = ImageAsset.objects.none()
        if hotel:
            cat_qs = Category.objects.filter(hotel=hotel, is_active=True)
            img_qs = ImageAsset.objects.filter(hotel=hotel)
        self.fields["category"].queryset = cat_qs
        self.fields["image_existing"].queryset = img_qs

    def clean(self):
        cleaned = super().clean()
        # optional: basic price guard
        if cleaned.get("price") is not None and cleaned["price"] < 0:
            self.add_error("price", "Price cannot be negative.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.request:
            obj.hotel = self.request.user.hotel

        img = self.cleaned_data.get("image_existing")
        upload = self.cleaned_data.get("image_upload")
        if upload:
            # Create an ImageAsset from upload
            name = self.cleaned_data.get("name") or "Item Photo"
            ia = ImageAsset.objects.create(hotel=self.request.user.hotel, name=name, file=upload)
            obj.image = ia
        elif img:
            obj.image = img

        if commit:
            obj.save()
        return obj




class InvoiceSettingsForm(forms.ModelForm):
    class Meta:
        model = HotelBillingSettings
        fields = ["gst_number", "gst_percent", "invoice_prefix", "next_invoice_seq"]
        widgets = {
            "gst_number": forms.TextInput(attrs={"class": "form-control"}),
            "gst_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "invoice_prefix": forms.TextInput(attrs={"class": "form-control"}),
            "next_invoice_seq": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
        }

