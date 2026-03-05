from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from website.models import Hotel
from hotelportal.models import Room, Category, Item, HotelBillingSettings
from decimal import Decimal
from django.utils import timezone

User = get_user_model()

class Command(BaseCommand):
    help = 'Setup demo hotel with sample data'

    def handle(self, *args, **options):
        self.stdout.write('Creating demo hotel...')
        
        # Create demo hotel
        hotel, created = Hotel.objects.get_or_create(
            hotel_code='DEMO001',
            defaults={
                'name': 'Grand Plaza Hotel',
                'city': 'Mumbai',
                'address': '123 Marine Drive, Mumbai, Maharashtra 400001',
                'phone': '+91 22 1234 5678',
                'email': 'info@grandplaza.com',
                'owner_name': 'Rajesh Kumar',
                'status': 'ACTIVE',
                'subscription_expires_on': timezone.now().date() + timezone.timedelta(days=365),
            }
        )

        
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created hotel: {hotel.name}'))
        else:
            self.stdout.write(f'Hotel already exists: {hotel.name}')
        
        # Create admin user
        admin_user, created = User.objects.get_or_create(
            username='demo_admin',
            defaults={
                'email': 'admin@grandplaza.com',
                'role': 'HOTEL_ADMIN',
                'hotel': hotel,
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('demo123')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS('Created admin user: demo_admin / demo123'))
        else:
            # Update existing user to be superuser
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.save()
            self.stdout.write(self.style.SUCCESS('Updated admin user to superuser'))
        
        # Create billing settings
        HotelBillingSettings.objects.get_or_create(
            hotel=hotel,
            defaults={
                'gst_number': '27AABCU9603R1ZM',
                'gst_percent': Decimal('5.00'),
                'invoice_prefix': 'GP',
            }
        )
        
        # Create rooms
        rooms_data = [
            ('101', '1'), ('102', '1'), ('103', '1'),
            ('201', '2'), ('202', '2'), ('203', '2'),
            ('301', '3'), ('302', '3'), ('303', '3'),
        ]
        for number, floor in rooms_data:
            Room.objects.get_or_create(
                hotel=hotel,
                number=number,
                defaults={'floor': floor, 'is_active': True, 'status': 'FREE'}
            )
        self.stdout.write(self.style.SUCCESS(f'Created {len(rooms_data)} rooms'))

        
        # Create Food Categories
        food_cats = {
            'Breakfast': ['Eggs & Toast', 'Pancakes', 'Continental Breakfast'],
            'Main Course': ['Butter Chicken', 'Paneer Tikka Masala', 'Biryani', 'Pasta Alfredo'],
            'Beverages': ['Fresh Juice', 'Coffee', 'Tea', 'Smoothies'],
            'Desserts': ['Ice Cream', 'Gulab Jamun', 'Chocolate Cake'],
        }
        
        for cat_name, items in food_cats.items():
            cat, _ = Category.objects.get_or_create(
                hotel=hotel,
                name=cat_name,
                kind='FOOD',
                defaults={'is_active': True}
            )
            
            for idx, item_name in enumerate(items):
                Item.objects.get_or_create(
                    hotel=hotel,
                    category=cat,
                    name=item_name,
                    defaults={
                        'price': Decimal('150.00') + (idx * 50),
                        'is_available': True,
                        'position': idx,
                    }
                )
        
        # Create Service Categories
        service_cats = {
            'Housekeeping': ['Room Cleaning', 'Extra Towels', 'Extra Pillows'],
            'Maintenance': ['AC Repair', 'TV Issue', 'Plumbing'],
            'Concierge': ['Wake Up Call', 'Taxi Booking', 'Tour Information'],
        }
        
        for cat_name, items in service_cats.items():
            cat, _ = Category.objects.get_or_create(
                hotel=hotel,
                name=cat_name,
                kind='SERVICE',
                defaults={'is_active': True}
            )
            
            for idx, item_name in enumerate(items):
                Item.objects.get_or_create(
                    hotel=hotel,
                    category=cat,
                    name=item_name,
                    defaults={
                        'price': Decimal('0.00'),
                        'is_available': True,
                        'position': idx,
                    }
                )
        
        self.stdout.write(self.style.SUCCESS('✓ Demo data created successfully!'))
        self.stdout.write(self.style.WARNING('\nLogin credentials:'))
        self.stdout.write('  Username: demo_admin')
        self.stdout.write('  Password: demo123')
