# Local Setup Guide

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/Abhiscience/Abhiscience-Workshop-Click-2-Track.git
cd Abhiscience-Workshop-Click-2-Track
```

### 2. Start Backend Services (Docker)

```bash
# Start PostgreSQL, Redis, MinIO
docker-compose up -d

# Wait for services to start
sleep 10

# Setup database
cd services/api
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The backend will be available at: http://localhost:8000

### 3. Start Admin Dashboard

```bash
cd apps/admin-web
npm install
npm run dev
```

The dashboard will be available at: http://localhost:3000

### 4. Run Android App (MacBook)

See [Emulator Testing Guide](emulator.md) for detailed MacBook instructions.

## Environment Variables

### Backend (.env)

```bash
# Required
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/workshop_db
SECRET_KEY=your-secret-key-here
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin

# Optional
ANPR_PROVIDER=mock
DMS_PROVIDER=mock
DEBUG=true
```

### Dashboard (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

## Database Setup

The system uses PostgreSQL. Database schema is auto-created on startup.

For manual migration:
```bash
# Using Alembic (when configured)
alembic upgrade head
```

## Running Tests

```bash
# Backend tests
cd services/api
pytest

# Dashboard tests
cd apps/admin-web
npm test
```

## Default Accounts

For development/testing, use these credentials:
- Security Guard: +971500000001 / password
- Service Advisor: +971500000002 / password
- Technician: +971500000003 / password

(These will be created when seed data is loaded)