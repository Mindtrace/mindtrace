# Inspectra Backend — With Database Support

This backend now includes a minimal database integration layer built on top of **mindtrace-database** and **mindtrace-services**.
The goal is to provide a clean, extendable foundation while keeping the boilerplate minimal.

---

## 🚀 Features Included

- FastAPI backend (`api/main.py`)
- Clean router/service/repository architecture
- Celery worker scaffold
- Mindtrace Service registration (`inspectra.py`)
- Database repository integration (Mongo-like or Document DB through mindtrace-database)
- Dockerfile (multi-stage, production-ready)
- docker-compose with Redis
- Environment template (`.env.example`)
- End-to-end folder structure ready to expand

---

## 📁 Folder Structure

```
inspectra/
│
├── api/
│   ├── main.py
│   ├── routers/
│   │   ├── health.py
│   │   ├── auth.py
│   │   ├── lines.py
│   │   └── plant.py
│   ├── models/
│   │   ├── line.py
│   │   └── plant.py
│   ├── repositories/
│   │   ├── base_repository.py
│   │   ├── line_repository.py
│   │   └── plant_repository.py
│   └── services/
│       ├── line_service.py
│       └── plant_service.py
│
├── workers/
│   └── celery_app.py
│
├── inspectra.py
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 🗄️ Database Integration (mindtrace-database)

Inspectra uses the **mindtrace-database** abstraction layer, which provides:

- Document-based collections
- High-ingest write support
- Fast reads for analytics
- Automatic indexing (depending on backend)
- Multi-database engine compatibility

### Example — Base Repository

```python
from mindtrace.database import Database

class BaseRepository:
    def __init__(self, collection_name: str):
        self.db = Database().collection(collection_name)

    async def get_all(self):
        return await self.db.find({})

    async def insert_one(self, data: dict):
        return await self.db.insert_one(data)

    async def find_by_id(self, id: str):
        return await self.db.find_one({"_id": id})
```

---

## 🌱 Example: Plant Repository

```python
from mindtrace.apps.inspectra.repositories.base_repository import BaseRepository

class PlantRepository(BaseRepository):
    def __init__(self):
        super().__init__("plants")

    async def get_all_plants(self):
        return await self.get_all()

    async def create_plant(self, plant: dict):
        return await self.insert_one(plant)
```

---

## 🧠 Example: Plant Service

```python
from mindtrace.apps.inspectra.repositories.plant_repository import PlantRepository

class PlantService:
    def __init__(self):
        self.repo = PlantRepository()

    async def list_plants(self):
        return await self.repo.get_all_plants()

    async def create_plant(self, plant):
        return await self.repo.create_plant(plant)
```

---

## 🚦 Example Router

```python
from fastapi import APIRouter
from mindtrace.apps.inspectra.services.plant_service import PlantService

router = APIRouter(prefix="/plants", tags=["Plants"])
service = PlantService()

@router.get("/")
async def list_plants():
    return await service.list_plants()

@router.post("/")
async def create_plant(payload: dict):
    return await service.create_plant(payload)
```

---

## ⚙️ Required Environment Variables

```
DATABASE_URL=mindtrace://localhost:9000
DATABASE_NAME=inspectra
REDIS_URL=redis://redis:6379
```

---

## 🐳 Running the Backend

### Build & run with Docker:

```
docker-compose up --build
```

API is available at:

```
http://localhost:8000
```

---

## 🧪 Health Check

```
GET /health
```

Response:

```json
{ "status": "ok" }
```

---
