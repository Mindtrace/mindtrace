# Inspectra Backend — Modern Service Architecture (MongoDB + Mindtrace)

This backend is a production-ready Inspectra service built using:

- **Mindtrace Service Framework (`mindtrace.services.Service`)**
- **FastAPI**
- **MongoDB** (via motor)
- **JWT-based authentication**
- **Role-based access structure**
- **Separation into routers / services / repositories / schemas / models**
- **Docker Compose with Mongo & Mongo Express**
- **Environment-driven configuration (`.env`)**

This setup is clean, extensible, and aligns with best practices for microservices.

---

## 🚀 Features Included

- Mindtrace-native service (`inspectra.py`)
- Modular FastAPI architecture
- MongoDB-backed repositories
- User authentication (JWT)
- Role management
- Plant & Line CRUD
- Environment-based settings system
- Dockerfile + Compose setup
- Mongo Express admin panel
- Health & config endpoints
- Production-ready folder structure

---

## 📁 Folder Structure

```
mindtrace/apps/inspecttra/
│
├── inspectra.py              # Mindtrace Service definition
├── run.py                    # Service launcher
│
├── app/
│   ├── api/
│   │   ├── core/
│   │   │   ├── settings.py   # Pydantic settings from .env
│   │   │   ├── db.py         # Mongo client
│   │   │   └── security.py   # JWT + password hashing + auth deps
│   │   │
│   │   └── routers/
│   │       ├── auth.py
│   │       ├── roles.py
│   │       ├── plants.py
│   │       └── lines.py
│   │
│   ├── models/
│   │   ├── user.py
│   │   ├── role.py
│   │   ├── plant.py
│   │   └── line.py
│   │
│   ├── schemas/
│   │   ├── auth.py
│   │   ├── role.py
│   │   ├── plant.py
│   │   └── line.py
│   │
│   ├── repositories/
│   │   ├── user_repository.py
│   │   ├── role_repository.py
│   │   ├── plant_repository.py
│   │   └── line_repository.py
│   │
│   └── services/
│       ├── auth_service.py
│       ├── role_service.py
│       ├── plant_service.py
│       └── line_service.py
│
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md  (this file)
```

---

## ⚙️ Environment Variables (`.env.example`)

```
# General
ENVIRONMENT=development
API_PORT=8000

# Service metadata
SERVICE_NAME=inspectra
SERVICE_DESCRIPTION=Inspectra Platform
SERVICE_VERSION=1.0.0
SERVICE_AUTHOR=Inspectra
SERVICE_AUTHOR_EMAIL=inspectra@inspectra.com
SERVICE_URL=https://inspectra.com

# JWT Auth
JWT_SECRET=change_me_super_secret
JWT_ALGORITHM=HS256
JWT_EXPIRES_IN=86400

# MongoDB
MONGO_INITDB_ROOT_USERNAME=inspectra_root
MONGO_INITDB_ROOT_PASSWORD=inspectra_root_password
MONGO_INITDB_DATABASE=inspectra
MONGO_URI=mongodb://inspectra_root:inspectra_root_password@mongo:27017/inspectra?authSource=admin
MONGO_DB_NAME=inspectra

# Mongo Express UI login
ME_CONFIG_MONGODB_ADMINUSERNAME=inspectra_root
ME_CONFIG_MONGODB_ADMINPASSWORD=inspectra_root_password
ME_CONFIG_MONGODB_SERVER=mongo
ME_CONFIG_BASICAUTH_USERNAME=admin
ME_CONFIG_BASICAUTH_PASSWORD=admin
```

---

## 🐳 Docker Compose Setup

Start everything:

```bash
docker compose up --build
```

### API →

```
http://localhost:8000
```

### Mongo Express →

```
http://localhost:8081
```

---

## 🔐 Authentication Flow

### Register:

```
POST /auth/register
{
  "username": "user",
  "password": "secret"
}
```

### Login:

```
POST /auth/login
```

Response:

```
{ "access_token": "<JWT>", "token_type": "bearer" }
```

Include token:

```
Authorization: Bearer <JWT>
```

---

## 🧠 Roles System

- Each user has **one `role_id`**
- Default `user` role created automatically
- Endpoints:

```
GET /roles
POST /roles
```

---

## 🌱 Plant API

```
GET /plants
POST /plants
```

---

## 🔗 Line API

```
GET /lines
POST /lines
```

---

## 🚦 Health Check

```
GET /health
```

---

## 🧪 Config Endpoint

```
GET /config
```

Shows active service config.

---

## 🛠 Development Commands

```
docker compose up --build
docker compose logs -f api
```

---
