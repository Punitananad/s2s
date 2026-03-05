# Production Deployment Guide

## Server Setup (Ubuntu 24.04)

### 1. Initial Server Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install python3.12 python3.12-venv python3-pip nginx supervisor git -y
```

### 2. Clone and Setup Application
### 2. Clone and Setup Appln

```bash
# Create app directory
mkdir -p /home/punu/scan2service
cd /home/punu/scan2service

# Clone repository
git clone https://github.com/Punitananad/s2s.git .

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Setup demo data (optional)
python manage.py setup_demo

# Collect static files
python manage.py collectstatic --noinput
```

### 3. Configure Supervisor

Create `/etc/supervisor/conf.d/scan2service.conf`:

```ini
[program:scan2service]
directory=/home/punu/scan2service
command=/home/punu/scan2service/.venv/bin/daphne -b 127.0.0.1 -p 8000 scan2service.asgi:application
user=punu
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/home/punu/scan2service/app.log
environment=DJANGO_SETTINGS_MODULE="scan2service.settings"
```

Start the service:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start scan2service
```

### 4. Configure Nginx

Create `/etc/nginx/sites-available/scan2service`:

```nginx
server {
    listen 80;
    server_name scan2service.in www.scan2service.in;

    client_max_body_size 20M;

    location /static/ {
        alias /home/punu/scan2service/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /home/punu/scan2service/media/;
        expires 30d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/scan2service /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### 5. SSL Certificate (Let's Encrypt)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d scan2service.in -d www.scan2service.in

# Test auto-renewal
sudo certbot renew --dry-run
```

### 6. Update Django Settings

Update `scan2service/settings.py` for production:

```python
DEBUG = False
ALLOWED_HOSTS = ['scan2service.in', 'www.scan2service.in', '142.93.216.76']
CSRF_TRUSTED_ORIGINS = ['https://scan2service.in', 'https://www.scan2service.in']
SITE_URL = 'https://scan2service.in'

# Use PostgreSQL in production (recommended)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'scan2service',
        'USER': 'dbuser',
        'PASSWORD': 'dbpassword',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

### 7. Useful Commands

```bash
# View logs
tail -f /home/punu/scan2service/app.log
sudo tail -f /var/log/nginx/error.log

# Restart services
sudo supervisorctl restart scan2service
sudo systemctl restart nginx

# Update application
cd /home/punu/scan2service
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo supervisorctl restart scan2service
```

### 8. Backup Strategy

```bash
# Backup database
python manage.py dumpdata > backup_$(date +%Y%m%d).json

# Backup media files
tar -czf media_backup_$(date +%Y%m%d).tar.gz media/
```

### 9. Monitoring

Set up monitoring with:
- Uptime monitoring (UptimeRobot, Pingdom)
- Error tracking (Sentry)
- Log aggregation (Papertrail, Loggly)

### 10. Security Checklist

- [ ] Change SECRET_KEY in production
- [ ] Set DEBUG = False
- [ ] Configure ALLOWED_HOSTS properly
- [ ] Enable HTTPS only
- [ ] Set up firewall (ufw)
- [ ] Regular security updates
- [ ] Database backups
- [ ] Rate limiting
- [ ] CSRF protection enabled
- [ ] Secure cookies (HTTPS only)

## DNS Configuration (GoDaddy)

Add these records:

```
Type: A
Name: @
Value: 142.93.216.76
TTL: 600

Type: A
Name: www
Value: 142.93.216.76
TTL: 600
```

Wait 10-30 minutes for DNS propagation.

## Troubleshooting

### Service won't start
```bash
sudo supervisorctl status scan2service
tail -f /home/punu/scan2service/app.log
```

### Nginx errors
```bash
sudo nginx -t
sudo tail -f /var/log/nginx/error.log
```

### Static files not loading
```bash
python manage.py collectstatic --noinput
sudo systemctl restart nginx
```

### WebSocket connection fails
Check that Nginx is properly configured for WebSocket upgrade headers.
