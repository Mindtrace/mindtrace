# Authenticated CRUD Service Example

A complete example demonstrating an authenticated CRUD API using `mindtrace-services` with MongoDB storage and JWT authentication.

## Quick Start

```bash
cd samples/services/crud_auth
python run_service.py
```

The script automatically starts MongoDB in Docker. Access:
- **Swagger UI**: http://localhost:8080/docs
- **API**: http://localhost:8080

### Get a Token

**Option 1: Login** (recommended)
```bash
curl -X POST "http://localhost:8080/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "email=user@example.com&password=YourPassword123"
```

**Option 2: Generate test token**
```bash
python generate_token.py
```

### Test the API

```bash
# Get token
TOKEN=$(curl -X POST "http://localhost:8080/login" \
  -d "email=user@example.com&password=YourPassword123" \
  | jq -r '.access_token')

# Create user (public - no auth needed)
curl -X POST "http://localhost:8080/create_user" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "email": "alice@example.com", "password": "SecurePass123", "age": 30}'

# List users (public)
curl "http://localhost:8080/list_users"
```

## Usage

```python
from auth_crud_service import AuthenticatedCRUDService
import httpx

# Launch service
cm = AuthenticatedCRUDService.launch(port=8080, host="localhost", wait_for_launch=True)

# Login to get token
response = httpx.post("http://localhost:8080/login", 
    data={"email": "user@example.com", "password": "YourPassword123"})
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Create user (public - no auth needed)
user = httpx.post("http://localhost:8080/create_user", json={
    "name": "Alice", "email": "alice@example.com", 
    "password": "SecurePass123", "age": 30
}).json()

# Login to get token for other operations
response = httpx.post("http://localhost:8080/login", 
    data={"email": "alice@example.com", "password": "SecurePass123"})
token = response.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Other CRUD operations (authenticated)

retrieved = httpx.get(f"http://localhost:8080/get_user?user_id={user['id']}", headers=headers).json()
updated = httpx.put("http://localhost:8080/update_user", json={
    "user_id": user['id'], "age": 31
}, headers=headers).json()

# Public endpoints (no auth)
users = httpx.get("http://localhost:8080/list_users").json()
results = httpx.get("http://localhost:8080/search_users?skill=Python").json()
```

## Endpoints

**Public**: `POST /login`, `POST /create_user`, `GET /list_users`, `GET /search_users`  
**Authenticated**: `GET /get_user`, `PUT /update_user`, `DELETE /delete_user`

**Authentication**: Include `Authorization: Bearer <token>` header. Tokens expire after 30 minutes.

**Authorization**: Users can only update/delete their own data.

## Configuration

**MongoDB**: Defaults to `mongodb://admin:adminpassword@localhost:27017/?authSource=admin`. Override via:
```bash
export MONGO_URI="mongodb://user:pass@host:port/?authSource=admin"
export MONGO_DB_NAME="my_database"
```

**JWT Secret**: Set for production: `export JWT_SECRET=$(openssl rand -hex 32)`

## User Model

Fields: `name`, `email` (unique, used for login), `password` (hashed with Argon2), `age`, `skills`, `disabled`, `created_at`, `updated_at`

**Password Requirements**: Min 8 chars, uppercase, lowercase, digit

## Demo

```bash
python auth_crud_demo.py
```

## Notes

- MongoDB auto-starts/stops via Docker in `run_service.py`
- Passwords hashed with Argon2, never returned in responses
- Tokens expire after 30 minutes
- Users can only modify their own data
- Set `JWT_SECRET` environment variable for production
