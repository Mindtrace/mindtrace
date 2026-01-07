# Inspectra Backend — Mindtrace Service Architecture (MongoDB + TaskSchemas)

This is the **official Inspectra backend**, built using the **Mindtrace Service Framework**.  
It provides a clean, modular and production-ready architecture with:

- **Mindtrace `Service` framework**
- **JSON-schema-driven TaskSchemas**
- **MongoDB (Motor async driver)**
- **JWT-based authentication**
- **Role-based access**
- **Plants / Lines CRUD**
- **Repository + Model architecture**
- **Environment-driven configuration**
- **Zero FastAPI routers — everything is handled via `Service.add_endpoint()`**

---

# 🚀 Overview

Inspectra is built around a **single service**:

```
InspectraService
```

This service registers all endpoints using Mindtrace’s built-in routing layer (not FastAPI routes):

```python
self.add_endpoint("/plants", self.list_plants, schema=ListPlantsSchema, methods=["GET"])
```

All endpoints have:

- **input schemas**
- **output schemas**
- **internal repositories**
- **Mongo-backed models**
- **JWT-protected auth**

---

# 📁 Final Folder Structure

```
mindtrace/apps/inspectra/
│
├── __init__.py
├── __main__.py
├── db.py                  # MongoDB client (Motor)
├── inspectra.py           # Main Inspectra Mindtrace Service
│
├── core/
│   ├── __init__.py
│   ├── settings.py            # Environment-based config (INSPECTRA__*)
│   ├── security.py            # JWT + password hashing + auth dependencies
│
├── models/
│   ├── plant.py
│   ├── line.py
│   ├── role.py
│   └── user.py
│
├── repositories/
│   ├── user_repository.py
│   ├── role_repository.py
│   ├── plant_repository.py
│   └── line_repository.py
│
├── schemas/
│   ├── auth.py
│   ├── plant.py
│   ├── line.py
│   └── role.py
│
└── README.md
```

✔ Clean  
✔ Extensible  
✔ Fully service-based  
✔ Aligned with Mindtrace standards  

---

# ⚙️ Environment Variables (`.env.example`)

The Inspectra backend loads its config from environment variables using:

```
INSPECTRA__<SETTING_NAME>
```

Example `.env.example`:

```
# Inspectra Service Config
INSPECTRA__URL=http://localhost:8082

# MongoDB
INSPECTRA__DB_URI=mongodb://localhost:27017
INSPECTRA__DB_NAME=inspectra

# Auth
INSPECTRA__AUTH_SECRET_KEY=super_secret_key
INSPECTRA__AUTH_ENABLED=True

# Logging
INSPECTRA__LOG_LEVEL=INFO
INSPECTRA__DEBUG=False
```

---

# 🧱 Core Components

## 1. **Settings System**

`core/settings.py` provides fully dynamic settings loaded via Mindtrace `Config`.

```python
get_inspectra_config().INSPECTRA.URL
```

Supports environment overrides like:

```
INSPECTRA__DB_URI=mongodb://mongo:27017
```

---

## 2. **MongoDB (`motor`) Integration**

`core/db.py` provides:

```python
get_client()
get_db()
close_client()
```

This creates a reusable async Mongo client for all repositories.

---

## 3. **Security**

`core/security.py` includes:

- PBKDF2 password hashing
- JWT generation & decoding
- FastAPI-style dependency wrapper for Mindtrace auth (`require_user`)
- TokenData model

---

## 4. **Models (dataclasses)**

Every domain object is a lightweight `@dataclass`, e.g.:

```python
@dataclass
class Plant:
    id: str
    name: str
    code: str
    location: Optional[str]
    is_active: bool
```

---

## 5. **Repositories**

Each repository:

- Connects to Mongo
- Performs CRUD
- Converts raw BSON → dataclass models

Example:

```python
class PlantRepository:
    async def list(self):
        cursor = self.collection.find({})
```

---

## 6. **TaskSchemas**

Schemas describe API contracts:

```python
CreatePlantSchema = TaskSchema(
    name="create_plant",
    input_schema=PlantCreateRequest,
    output_schema=PlantResponse,
)
```

These are used by the service when defining endpoints.

---

## 7. **InspectraService**

`inspectra.py` is the heart of the system.

It:

- Registers all endpoints (auth, plants, lines, roles)
- Assigns schemas
- Calls repository methods
- Handles authentication
- Uses Mindtrace logging & middleware
- Supports MCP tools

Example endpoint:

```python
self.add_endpoint(
    "/plants",
    self.create_plant,
    schema=CreatePlantSchema,
    methods=["POST"],
)
```

---

# 📡 Endpoints

### 🔐 **Authentication**
```
POST /auth/register
POST /auth/login
```

### 👥 **Roles**
```
GET /roles
POST /roles
GET /roles/{id}
PUT /roles/{id}
```

### 🌱 **Plants**
```
GET /plants
POST /plants
GET /plants/{id}
PUT /plants/{id}
```

### 🔗 **Lines**
```
GET /lines
POST /lines
```

Each endpoint uses proper:

- request models  
- response models  
- repository methods  
- error handling via HTTPException  
- JWT enforcement using `require_user` when desired  

---

# 🐳 Docker Support

A minimal docker-compose example:

```
docker compose up --build
```

Mongo shell:

```
docker exec -it inspectra-mongo mongosh
```

---

# 🛠 Development Commands

```
python -m mindtrace.apps.inspectra          # Run service directly
docker compose up --build                   # Run with Mongo
```

---

# 🧪 Health + Config Endpoints

Mindtrace services automatically exposes:

```
GET /health
GET /config
```

---

# 🎯 Summary

The Inspectra backend is:

- Lightweight  
- Fully service-based  
- MongoDB-backed  
- JWT-secured  
- Extensible  
- Production-ready  
