"""
Management command: seed_food_menu
Seeds food categories and items with images for a specific hotel.

Usage:
    python manage.py seed_food_menu --hotel 1
    python manage.py seed_food_menu --hotel 1 --clear   # wipe existing food data first
"""

import os
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from website.models import Hotel
from hotelportal.models import Category, Item, ImageAsset


# ---------------------------------------------------------------------------
# Menu data
# ---------------------------------------------------------------------------
# Each category entry:
#   name, position, icon_file (relative to MEDIA_ROOT/category_icons/)
# Each item entry:
#   name, price, unit, description, position, image_file (relative to MEDIA_ROOT/item_photos/)

MENU = [
    {
        "name": "Starters",
        "position": 1,
        "icon": "pizza.png",          # existing in media/category_icons/
        "items": [
            {
                "name": "Veg Spring Rolls",
                "price": "120.00",
                "unit": "plate",
                "description": "Crispy rolls stuffed with mixed vegetables.",
                "position": 1,
                "image": "burger.png",
            },
            {
                "name": "Paneer Tikka",
                "price": "180.00",
                "unit": "plate",
                "description": "Marinated cottage cheese grilled in tandoor.",
                "position": 2,
                "image": "pexels-rajesh-tp-1633525.jpg",
            },
            {
                "name": "Popcorn Chicken",
                "price": "150.00",
                "unit": "plate",
                "description": "Crispy bite-sized chicken pieces.",
                "position": 3,
                "image": "popcorn.png",
            },
        ],
    },
    {
        "name": "Main Course",
        "position": 2,
        "icon": "pizza.png",
        "items": [
            {
                "name": "Butter Chicken",
                "price": "280.00",
                "unit": "plate",
                "description": "Tender chicken in rich tomato-butter gravy.",
                "position": 1,
                "image": "download_1.jpg",
            },
            {
                "name": "Paneer Butter Masala",
                "price": "250.00",
                "unit": "plate",
                "description": "Creamy paneer curry with aromatic spices.",
                "position": 2,
                "image": "pexels-rajesh-tp-1633525.jpg",
            },
            {
                "name": "Veg Biryani",
                "price": "220.00",
                "unit": "plate",
                "description": "Fragrant basmati rice with mixed vegetables.",
                "position": 3,
                "image": "download_1.jpg",
            },
            {
                "name": "Chicken Biryani",
                "price": "300.00",
                "unit": "plate",
                "description": "Dum-cooked biryani with juicy chicken pieces.",
                "position": 4,
                "image": "pexels-rajesh-tp-1633525.jpg",
            },
        ],
    },
    {
        "name": "Beverages",
        "position": 3,
        "icon": "cocktail.png",        # existing in media/category_icons/
        "items": [
            {
                "name": "Fresh Lime Soda",
                "price": "60.00",
                "unit": "glass",
                "description": "Refreshing lime juice with soda.",
                "position": 1,
                "image": "nimbu_paani.jpg",
            },
            {
                "name": "Mango Lassi",
                "price": "80.00",
                "unit": "glass",
                "description": "Thick yogurt-based mango smoothie.",
                "position": 2,
                "image": "nimbu_paani.jpg",
            },
            {
                "name": "Masala Chai",
                "price": "40.00",
                "unit": "cup",
                "description": "Indian spiced milk tea.",
                "position": 3,
                "image": "nimbu_paani.jpg",
            },
            {
                "name": "Cold Coffee",
                "price": "100.00",
                "unit": "glass",
                "description": "Blended iced coffee with milk.",
                "position": 4,
                "image": "nimbu_paani.jpg",
            },
        ],
    },
    {
        "name": "Breakfast",
        "position": 4,
        "icon": "cupcake.png",
        "items": [
            {
                "name": "Masala Omelette",
                "price": "100.00",
                "unit": "plate",
                "description": "Fluffy egg omelette with onion and chilli.",
                "position": 1,
                "image": "download_1.jpg",
            },
            {
                "name": "Aloo Paratha",
                "price": "90.00",
                "unit": "plate",
                "description": "Stuffed flatbread served with curd and pickle.",
                "position": 2,
                "image": "pexels-rajesh-tp-1633525.jpg",
            },
            {
                "name": "Idli Sambar",
                "price": "80.00",
                "unit": "plate",
                "description": "Steamed rice cakes with lentil soup.",
                "position": 3,
                "image": "download_1.jpg",
            },
            {
                "name": "Bread Butter Toast",
                "price": "50.00",
                "unit": "plate",
                "description": "Toasted bread served with butter and jam.",
                "position": 4,
                "image": "download_1.jpg",
            },
        ],
    },
    {
        "name": "Snacks",
        "position": 5,
        "icon": "pizza.png",
        "items": [
            {
                "name": "Burger",
                "price": "130.00",
                "unit": "piece",
                "description": "Grilled patty burger with lettuce and sauce.",
                "position": 1,
                "image": "burger.png",
            },
            {
                "name": "French Fries",
                "price": "90.00",
                "unit": "plate",
                "description": "Crispy golden potato fries.",
                "position": 2,
                "image": "popcorn.png",
            },
            {
                "name": "Samosa (2 pcs)",
                "price": "40.00",
                "unit": "plate",
                "description": "Fried pastry stuffed with spiced potatoes.",
                "position": 3,
                "image": "popcorn.png",
            },
        ],
    },
    {
        "name": "Desserts",
        "position": 6,
        "icon": "cupcake.png",         # existing in media/category_icons/
        "items": [
            {
                "name": "Vanilla Ice Cream",
                "price": "80.00",
                "unit": "scoop",
                "description": "Creamy vanilla ice cream.",
                "position": 1,
                "image": "icecream.jpg",
            },
            {
                "name": "Chocolate Brownie",
                "price": "120.00",
                "unit": "piece",
                "description": "Warm fudgy brownie with chocolate sauce.",
                "position": 2,
                "image": "icecream.jpg",
            },
            {
                "name": "Gulab Jamun",
                "price": "60.00",
                "unit": "plate",
                "description": "Soft milk-solid balls soaked in rose syrup.",
                "position": 3,
                "image": "icecream.jpg",
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Seed food categories and items with images for a hotel"

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
            help="Delete existing FOOD categories/items for this hotel before seeding",
        )

    def handle(self, *args, **options):
        hotel_id = options["hotel"]
        do_clear = options["clear"]

        try:
            hotel = Hotel.objects.get(pk=hotel_id)
        except Hotel.DoesNotExist:
            raise CommandError(f"Hotel with id={hotel_id} does not exist.")

        self.stdout.write(f"Seeding food menu for: {self.style.SUCCESS(hotel.name)}")

        if do_clear:
            deleted, _ = Category.objects.filter(hotel=hotel, kind="FOOD").delete()
            self.stdout.write(self.style.WARNING(f"  Cleared {deleted} existing food categories/items."))

        media_root = settings.MEDIA_ROOT
        cat_icon_dir = os.path.join(media_root, "category_icons")
        item_photo_dir = os.path.join(media_root, "item_photos")

        categories_created = 0
        items_created = 0

        for cat_data in MENU:
            cat, cat_created = Category.objects.get_or_create(
                hotel=hotel,
                name=cat_data["name"],
                kind="FOOD",
                parent=None,
                defaults={
                    "position": cat_data["position"],
                    "is_active": True,
                },
            )
            if cat_created:
                categories_created += 1

            # Assign icon if available and not already set
            if not cat.icon:
                icon_path = os.path.join(cat_icon_dir, cat_data["icon"])
                if os.path.exists(icon_path):
                    # Store path relative to MEDIA_ROOT
                    cat.icon = f"category_icons/{cat_data['icon']}"
                    cat.save(update_fields=["icon"])

            for item_data in cat_data["items"]:
                # Get or create ImageAsset for this image file
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
                            "tags": "food",
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
        self.stdout.write(f"  Hotel ID: {hotel.id}")
        self.stdout.write(f"  Total food categories now: {Category.objects.filter(hotel=hotel, kind='FOOD').count()}")
        self.stdout.write(f"  Total food items now: {Item.objects.filter(hotel=hotel, category__kind='FOOD').count()}")
