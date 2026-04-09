"""
Management command: seed_service_menu
Seeds service categories and items with images for a specific hotel.

Usage:
    python manage.py seed_service_menu --hotel 8
    python manage.py seed_service_menu --hotel 8 --clear
"""

import os
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from website.models import Hotel
from hotelportal.models import Category, Item, ImageAsset


SERVICE_MENU = [
    {
        "name": "Housekeeping",
        "position": 1,
        "icon": "cleaner.png",
        "items": [
            {
                "name": "Room Cleaning",
                "price": "0.00",
                "unit": "request",
                "description": "Full room cleaning by housekeeping staff.",
                "position": 1,
                "image": "house-keeping.png",
            },
            {
                "name": "Extra Towels",
                "price": "0.00",
                "unit": "request",
                "description": "Request additional bath or hand towels.",
                "position": 2,
                "image": "house-keeping.png",
            },
            {
                "name": "Extra Pillows",
                "price": "0.00",
                "unit": "request",
                "description": "Request extra pillows for the bed.",
                "position": 3,
                "image": "house-keeping.png",
            },
            {
                "name": "Extra Blanket",
                "price": "0.00",
                "unit": "request",
                "description": "Request an additional blanket.",
                "position": 4,
                "image": "house-keeping.png",
            },
            {
                "name": "Laundry Pickup",
                "price": "50.00",
                "unit": "request",
                "description": "Laundry pickup from your room.",
                "position": 5,
                "image": "house-keeping.png",
            },
        ],
    },
    {
        "name": "Maintenance",
        "position": 2,
        "icon": "truck.png",
        "items": [
            {
                "name": "AC Not Working",
                "price": "0.00",
                "unit": "request",
                "description": "Report air conditioning issue.",
                "position": 1,
                "image": "delivery-man_1.png",
            },
            {
                "name": "TV Issue",
                "price": "0.00",
                "unit": "request",
                "description": "Report TV or remote control problem.",
                "position": 2,
                "image": "delivery-man_1.png",
            },
            {
                "name": "Plumbing Issue",
                "price": "0.00",
                "unit": "request",
                "description": "Report water leakage or plumbing problem.",
                "position": 3,
                "image": "delivery-man_1.png",
            },
            {
                "name": "Light / Electricity",
                "price": "0.00",
                "unit": "request",
                "description": "Report electrical issue in the room.",
                "position": 4,
                "image": "delivery-man_1.png",
            },
            {
                "name": "Wi-Fi Not Working",
                "price": "0.00",
                "unit": "request",
                "description": "Report internet connectivity issue.",
                "position": 5,
                "image": "delivery-man_1.png",
            },
        ],
    },
    {
        "name": "Concierge",
        "position": 3,
        "icon": "cleaner.png",
        "items": [
            {
                "name": "Wake Up Call",
                "price": "0.00",
                "unit": "request",
                "description": "Request a wake-up call at your desired time.",
                "position": 1,
                "image": "delivery-man_1.png",
            },
            {
                "name": "Taxi / Cab Booking",
                "price": "0.00",
                "unit": "request",
                "description": "Arrange a taxi or cab from reception.",
                "position": 2,
                "image": "truck.png",
            },
            {
                "name": "Tour Information",
                "price": "0.00",
                "unit": "request",
                "description": "Get local sightseeing and tour information.",
                "position": 3,
                "image": "delivery-man_1.png",
            },
            {
                "name": "Doctor on Call",
                "price": "0.00",
                "unit": "request",
                "description": "Request a doctor visit to your room.",
                "position": 4,
                "image": "delivery-man_1.png",
            },
        ],
    },
    {
        "name": "Room Amenities",
        "position": 4,
        "icon": "cleaner.png",
        "items": [
            {
                "name": "Iron & Ironing Board",
                "price": "0.00",
                "unit": "request",
                "description": "Request an iron and ironing board.",
                "position": 1,
                "image": "house-keeping.png",
            },
            {
                "name": "Hair Dryer",
                "price": "0.00",
                "unit": "request",
                "description": "Request a hair dryer.",
                "position": 2,
                "image": "house-keeping.png",
            },
            {
                "name": "Toiletries Refill",
                "price": "0.00",
                "unit": "request",
                "description": "Request shampoo, soap, or toothbrush refill.",
                "position": 3,
                "image": "house-keeping.png",
            },
            {
                "name": "Mineral Water",
                "price": "30.00",
                "unit": "bottle",
                "description": "Request mineral water bottles for the room.",
                "position": 4,
                "image": "house-keeping.png",
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Seed service categories and items with images for a hotel"

    def add_arguments(self, parser):
        parser.add_argument(
            "--hotel",
            type=int,
            required=True,
            help="Hotel ID to seed data for",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            default=False,
            help="Delete existing SERVICE categories/items for this hotel before seeding",
        )

    def handle(self, *args, **options):
        hotel_id = options["hotel"]
        do_clear = options["clear"]

        try:
            hotel = Hotel.objects.get(pk=hotel_id)
        except Hotel.DoesNotExist:
            raise CommandError(f"Hotel with id={hotel_id} does not exist.")

        self.stdout.write(f"Seeding service menu for: {self.style.SUCCESS(hotel.name)}")

        if do_clear:
            deleted, _ = Category.objects.filter(hotel=hotel, kind="SERVICE").delete()
            self.stdout.write(self.style.WARNING(f"  Cleared {deleted} existing service categories/items."))

        media_root = settings.MEDIA_ROOT
        cat_icon_dir = os.path.join(media_root, "category_icons")
        item_photo_dir = os.path.join(media_root, "item_photos")

        categories_created = 0
        items_created = 0

        for cat_data in SERVICE_MENU:
            cat, cat_created = Category.objects.get_or_create(
                hotel=hotel,
                name=cat_data["name"],
                kind="SERVICE",
                parent=None,
                defaults={
                    "position": cat_data["position"],
                    "is_active": True,
                },
            )
            if cat_created:
                categories_created += 1

            # Assign icon if not already set
            if not cat.icon:
                icon_path = os.path.join(cat_icon_dir, cat_data["icon"])
                if os.path.exists(icon_path):
                    cat.icon = f"category_icons/{cat_data['icon']}"
                    cat.save(update_fields=["icon"])

            for item_data in cat_data["items"]:
                image_filename = item_data["image"]
                image_path = os.path.join(item_photo_dir, image_filename)

                image_asset = None
                if os.path.exists(image_path):
                    asset_name = os.path.splitext(image_filename)[0].replace("_", " ").replace("-", " ").title()
                    image_asset, _ = ImageAsset.objects.get_or_create(
                        hotel=hotel,
                        name=asset_name,
                        defaults={
                            "file": f"item_photos/{image_filename}",
                            "tags": "service",
                        },
                    )

                item, item_created = Item.objects.get_or_create(
                    hotel=hotel,
                    category=cat,
                    name=item_data["name"],
                    defaults={
                        "price": Decimal(item_data["price"]),
                        "unit": item_data["unit"],
                        "description": item_data["description"],
                        "position": item_data["position"],
                        "is_available": True,
                        "image": image_asset,
                    },
                )
                if item_created:
                    items_created += 1
                    status = self.style.SUCCESS("created")
                else:
                    status = "already exists"
                self.stdout.write(f"    [{cat.name}] {item.name} — {status}")

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done! {categories_created} categories and {items_created} items created for '{hotel.name}'."
            )
        )
        self.stdout.write(f"  Total service categories now: {Category.objects.filter(hotel=hotel, kind='SERVICE').count()}")
        self.stdout.write(f"  Total service items now: {Item.objects.filter(hotel=hotel, category__kind='SERVICE').count()}")
