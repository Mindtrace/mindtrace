# Pytest fixtures are used by name injection; Pyright reports them as unused.
# pyright: reportUnusedFunction=false

import os
from datetime import datetime, timezone
from typing import Generator, List, Optional

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from mindtrace.apps.inspectra.core import hash_password, reset_inspectra_config
from mindtrace.apps.inspectra.db import close_db
from mindtrace.apps.inspectra.inspectra import InspectraService

# ---------------------------------------------------------------------------
# Test database configuration
# ---------------------------------------------------------------------------

TEST_MONGO_URI = "mongodb://localhost:27018"
"""MongoDB URI used exclusively for Inspectra integration tests."""

TEST_DB_NAME = "inspectra_test"
"""Database name used for Inspectra integration tests."""

TEST_COLLECTIONS: List[str] = ["users", "organizations"]
"""Collections that are wiped before and after each test to ensure isolation."""


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _set_inspectra_test_env() -> Generator[None, None, None]:
    """
    Configure Inspectra to use the test MongoDB instance.

    This fixture:
    - Sets INSPECTRA Mongo environment variables
    - Resets cached Inspectra config so env vars are reloaded
    - Runs once per test session
    - Is autouse to guarantee it executes before any Inspectra code runs

    This prevents accidental use of development or production databases.
    """
    os.environ["MONGO_URI"] = TEST_MONGO_URI
    os.environ["MONGO_DB_NAME"] = TEST_DB_NAME
    os.environ["INSPECTRA__JWT_SECRET"] = "inspectra-test-jwt-secret-at-least-32-bytes"
    reset_inspectra_config()

    yield


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------


def _create_test_user_sync() -> tuple[str, str]:
    """Create one org and one super_admin user in the test DB using sync pymongo; return (email, password)."""
    email = "super@inspectra-test.example.com"
    password = "SuperAdminPass12!"
    client = MongoClient(TEST_MONGO_URI)
    db = client[TEST_DB_NAME]
    try:
        now = datetime.now(timezone.utc)
        org_doc = {
            "name": "Test Org",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        res = db.organizations.insert_one(org_doc)
        org_id = res.inserted_id
        user_doc = {
            "email": email,
            "email_norm": email.lower(),
            "role": "super_admin",
            "first_name": "Super",
            "last_name": "Admin",
            "pw_hash": hash_password(password),
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "organization": {"$ref": "organizations", "$id": org_id},
        }
        db.users.insert_one(user_doc)
    finally:
        client.close()
    return email, password


@pytest.fixture(scope="function")
def client(_set_inspectra_test_env) -> Generator[TestClient, None, None]:
    """
    Provide a FastAPI TestClient backed by a fresh InspectraService instance.

    Scope: function
    - Ensures a clean ASGI app per test
    - Prevents event loop reuse issues
    - Ensures middleware and lifespan hooks run correctly

    Uses a context-managed TestClient to guarantee proper startup/shutdown.
    """
    service = InspectraService()
    with TestClient(service.app) as c:
        yield c


@pytest.fixture(scope="function")
def auth_headers(client: TestClient) -> dict:
    """Create test user, login, and return Authorization headers for subsequent requests."""
    email, password = _create_test_user_sync()
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    token = data["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_admin_user_sync() -> tuple[str, str]:
    """Create second org and an admin user; return (email, password)."""
    email = "admin@inspectra-test.example.com"
    password = "AdminUserPass12!"
    client = MongoClient(TEST_MONGO_URI)
    db = client[TEST_DB_NAME]
    try:
        now = datetime.now(timezone.utc)
        org_doc = {"name": "Org2", "status": "active", "created_at": now, "updated_at": now}
        res = db.organizations.insert_one(org_doc)
        org_id = res.inserted_id
        user_doc = {
            "email": email,
            "email_norm": email.lower(),
            "role": "admin",
            "first_name": "Admin",
            "last_name": "User",
            "pw_hash": hash_password(password),
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "organization": {"$ref": "organizations", "$id": org_id},
        }
        db.users.insert_one(user_doc)
    finally:
        client.close()
    return email, password


@pytest.fixture(scope="function")
def auth_headers_admin(client: TestClient) -> dict:
    """Create admin user (not super_admin), login, return Authorization headers."""
    email, password = _create_admin_user_sync()
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_regular_user_sync() -> tuple[str, str]:
    """Create a regular user (role=user) in Org2; return (email, password)."""
    email = "user@inspectra-test.example.com"
    password = "UserPass12!"
    client = MongoClient(TEST_MONGO_URI)
    db = client[TEST_DB_NAME]
    try:
        org = db.organizations.find_one({"name": "Org2"})
        if not org:
            now = datetime.now(timezone.utc)
            db.organizations.insert_one({"name": "Org2", "status": "active", "created_at": now, "updated_at": now})
            org = db.organizations.find_one({"name": "Org2"})
        now = datetime.now(timezone.utc)
        user_doc = {
            "email": email,
            "email_norm": email.lower(),
            "role": "user",
            "first_name": "Plain",
            "last_name": "User",
            "pw_hash": hash_password(password),
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "organization": {"$ref": "organizations", "$id": org["_id"]},
        }
        db.users.insert_one(user_doc)
    finally:
        client.close()
    return email, password


@pytest.fixture(scope="function")
def auth_headers_user(client: TestClient) -> dict:
    """Create regular user (role=user), login, return Authorization headers."""
    _create_admin_user_sync()  # ensure Org2 exists
    email, password = _create_regular_user_sync()
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# MongoDB helpers
# ---------------------------------------------------------------------------


def _get_test_db() -> Optional[MongoClient]:
    """
    Attempt to connect to the test MongoDB database.

    Returns:
        MongoClient if MongoDB is reachable,
        None if the server is unavailable.

    This helper allows tests to degrade gracefully when Mongo
    is not running instead of hard-failing.
    """
    client = MongoClient(TEST_MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[TEST_DB_NAME]
    try:
        _ = db.list_collection_names()
    except ServerSelectionTimeoutError:
        client.close()
        return None
    return client


def _wipe_test_collections() -> None:
    """
    Remove all documents from Inspectra test collections.

    - Deletes data only from known test collections
    - Never raises if MongoDB is unavailable
    - Ensures deterministic test isolation
    """
    client = _get_test_db()
    if client is None:
        return

    try:
        db = client[TEST_DB_NAME]
        collections = set(db.list_collection_names())
        for name in TEST_COLLECTIONS:
            if name in collections:
                db[name].delete_many({})
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Per-test cleanup
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_inspectra_collections(_set_inspectra_test_env):
    """
    Ensure Inspectra tests run with a clean database state.

    This fixture:
    - Closes any existing Motor client (prevents event loop issues)
    - Wipes test collections before each test
    - Wipes test collections again after each test

    Scope: function
    Autouse: ensures isolation even if a test crashes.
    """
    close_db()
    _wipe_test_collections()
    yield
    close_db()
    _wipe_test_collections()
