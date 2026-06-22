# Hostinger Deployment Guide

This guide explains how to deploy the backend API and admin dashboard to Hostinger shared hosting or VPS.

## Prerequisites

- Hostinger account with VPS or Shared Hosting
- Domain name (optional)
- SSH access to server

## Deployment Options

### Option 1: Hostinger VPS (Recommended)

#### 1. Server Setup

```bash
# Connect to VPS via SSH
ssh root@your-server-ip

# Update system
apt update && apt upgrade -y

# Install Docker
apt install docker.io docker-compose -y

# Clone repository
cd /root
git clone https://github.com/Abhiscience/Abhiscience-Workshop-Click-2-Track.git
cd Abhiscience-Workshop-Click-2-Track
```

#### 2. Configure Environment

```bash
# Copy environment template
cp services/api/.env.example services/api/.env

# Edit with production values
nano services/api/.env
```

Set these values:
- `SECRET_KEY`: Generate with `openssl rand -hex 32`
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection (use Redis addon or external)
- `MINIO_*`: Object storage credentials
- Set `DEBUG=false` and `ENVIRONMENT=production`

#### 3. Deploy with Docker

```bash
# Start services
docker-compose up -d

# Check logs
docker-compose logs -f api
```

#### 4. Configure Nginx Reverse Proxy

```nginx
server {
    listen 80;
    server_name api.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Option 2: Hostinger Shared Hosting

For shared hosting, deploy the FastAPI app as a WSGI service:

#### 1. Build Standalone

```bash
# In services/api directory
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile app/main.py
```

#### 2. Upload to Hostinger

Use File Manager or SFTP to upload:
- `dist/main` (compiled binary)
- `.env` file (rename from .env.example)
- Static files if any

#### 3. Configure Python App

In Hostinger hPanel:
1. Go to "Advanced" → "Python App"
2. Set Python version to 3.11+
3. Set startup file: `/main`
4. Set environment variables from .env

## SSL Certificate

Use Hostinger's free SSL or Let's Encrypt:

```bash
# Install certbot
apt install certbot python3-certbot-nginx -y

# Get certificate
certbot --nginx -d api.yourdomain.com
```

## Monitoring

Access logs location:
- API logs: `/var/log/workshop-api.log`
- Access logs: `/var/log/nginx/access.log`

Set up basic monitoring:
```bash
# Install netdata or use Hostinger monitoring
curl -sL https://raw.githubusercontent.com/netdata/netdata/master/packaging/installer/methods/install.sh | sh
```

## Database Backup

Schedule daily backups:
```bash
# Add to crontab
0 2 * * * pg_dump workshop_db > /backup/workshop_$(date +%Y%m%d).sql
```

## Useful Commands

```bash
# Restart services
docker-compose restart api

# View logs
docker-compose logs -f

# Check status
docker-compose ps

# Database shell
docker-compose exec db psql -U postgres workshop_db
```