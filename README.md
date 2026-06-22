# Workshop Click-2-Track

A production-ready Android-first vehicle movement tracking platform for automobile workshops.

## Overview

This platform provides **physical workflow visibility** for vehicle service operations by mandating photo capture at every handoff point, automatically recognizing number plates, and linking events to job cards in your existing DMS system.

## Key Features

- 📸 **Mandatory photo capture** at every workshop stage
- 🔢 **Number plate recognition** (UAE + India formats) via pluggable ANPR providers
- 🔗 **Job card matching** with existing DMS systems
- 👥 **Role-based tracking** for ALL manpower (security, advisor, tech, washing, parts, QC, delivery, manager)
- 📊 **Live workshop tracking** - see where every vehicle is right now
- ⚖️ **Deviation detection** - actual vs DMS workflow comparison
- 📈 **Analytics dashboard** - utilization, bottlenecks, productivity metrics
- 📱 **Offline-first mobile app** - queue events when offline, sync when online
- 🔌 **DMS integration adapters** - connect to your existing system

## Tech Stack

| Component | Technology |
|-----------|------------|
| Mobile App | Kotlin + Android Jetpack |
| Backend API | Python FastAPI + PostgreSQL |
| Dashboard | Next.js + TypeScript + Tailwind |
| ANPR | Provider abstraction (Pluggable) |
| Auth | JWT + OAuth2 |

## Repository Structure

```
workshop-click-2-track/
├── apps/
│   ├── mobile-android/      # Android Kotlin app
│   └── admin-web/           # Next.js admin dashboard
├── services/
│   ├── api/                 # FastAPI backend
│   └── integration-adapters/  # DMS connectors
├── packages/
│   ├── shared-types/        # Shared models (TS/Python)
│   ├── workflow-engine/       # Workflow logic
│   └── anpr-providers/      # ANPR abstraction layer
├── docs/
│   ├── setup/               # Setup guides
│   ├── api/                 # API documentation
│   └── deployment/            # Deployment guides
├── infra/                   # Docker, migrations
└── scripts/seed/            # Test data
```

## Quick Start

### Backend (API)

```bash
cd services/api
cp .env.example .env
docker-compose up -d  # Starts PostgreSQL, Redis, MinIO
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Mobile (Android)

```bash
cd apps/mobile-android
# Open in Android Studio
# Run on emulator or device
```

### Dashboard (Admin)

```bash
cd apps/admin-web
cp .env.example .env
npm install
npm run dev
```

## Documentation

- [Setup Guide](docs/setup/README.md) - Local development setup
- [API Reference](docs/api/openapi.yaml) - REST API documentation
- [Deployment Guide](docs/deployment/hostinger.md) - Hostinger deployment
- [APK Build Guide](docs/deployment/apk-build.md) - Building the Android APK
- [EMulator Testing](docs/setup/emulator.md) - MacBook emulator testing

## License

MIT License - See [LICENSE](LICENSE) file