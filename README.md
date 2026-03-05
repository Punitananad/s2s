# Scan2Service - Hotel Service Management Platform

A modern, real-time hotel service management system that enables guests to order food and request services via QR codes, while hotel staff manage operations through a live dashboard.

## 🌟 Key Features

### For Guests
- **QR Code Access**: Scan room QR code to access services
- **Digital Menu**: Browse food items and services with images
- **Real-time Ordering**: Place food orders and service requests instantly
- **Order Tracking**: Track request status in real-time
- **Phone Verification**: Secure access for active stays

### For Hotel Staff
- **Live Dashboard**: Real-time view of all incoming requests
- **Room Management**: Manage rooms, check-ins, and check-outs
- **Catalog Management**: Manage food menu and service offerings
- **Billing & Invoicing**: Generate GST-compliant invoices
- **WhatsApp Integration**: Send notifications to guests
- **Analytics**: Export reports and track performance

### For Platform Admins
- **Multi-Hotel Support**: Manage multiple hotel properties
- **Subscription Billing**: Track payments and subscriptions
- **Hotel Analytics**: Monitor usage across properties

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- pip
- Virtual environment

### Installation

1. Clone the repository:
```bash
git clone https://github.com/Punitananad/s2s.git
cd s2s
```

2. Create and activate virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run migrations:
```bash
python manage.py migrate
```

5. Create demo data:
```bash
python manage.py setup_demo
```

6. Run the development server:
```bash
python manage.py runserver
```

7. Access the application:
- Guest Interface: http://localhost:8000/h/1/r/1/
- Hotel Portal: http://localhost:8000/portal/
- Admin Panel: http://localhost:8000/admin/

### Demo Credentials
- Username: `demo_admin`
- Password: `demo123`

## 📱 Technology Stack

- **Backend**: Django 4.2.7
- **Real-time**: Django Channels + WebSockets
- **ASGI Server**: Daphne
- **Database**: SQLite (PostgreSQL ready)
- **Frontend**: Bootstrap 5 + HTMX
- **Images**: Pillow

## 🏗️ Project Structure

```
scan2service/
├── guest/              # Guest-facing views and templates
├── hotelportal/        # Hotel staff portal
├── website/            # Platform admin and auth
├── scan2service/       # Project settings
├── templates/          # HTML templates
├── static/             # Static files (CSS, JS, images)
└── media/              # Uploaded files
```

## 🔧 Configuration

### Environment Variables
Create a `.env` file for production:
```
DEBUG=False
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=yourdomain.com
DATABASE_URL=postgresql://user:pass@localhost/dbname
```

### Production Deployment
See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed production setup with Nginx and SSL.

## 📊 Features Roadmap

- [x] QR code room access
- [x] Real-time order management
- [x] Phone verification
- [x] Billing & invoicing
- [x] WhatsApp notifications
- [ ] Payment gateway integration
- [ ] Mobile app (React Native)
- [ ] Analytics dashboard
- [ ] Multi-language support
- [ ] Table reservations
- [ ] Loyalty program

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is proprietary software. All rights reserved.

## 📞 Support

For support, email support@scan2service.in or visit https://scan2service.in

## 🙏 Acknowledgments

Built with Django and modern web technologies to revolutionize hotel service management.
