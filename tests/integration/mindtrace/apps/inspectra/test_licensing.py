"""Integration tests for licensing endpoints."""

from datetime import datetime, timedelta

from mindtrace.apps.inspectra.core.license_validator import LicenseValidator
from mindtrace.apps.inspectra.core.machine_id import get_machine_id


def test_get_machine_id(client):
    """
    GET /license/machine-id should return the current machine's ID.

    Verifies:
    - endpoint returns 200
    - machine_id is a 64-character hex string
    """
    resp = client.get("/license/machine-id")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert "machine_id" in payload
    assert isinstance(payload["machine_id"], str)
    assert len(payload["machine_id"]) == 64


def test_machine_id_consistent(client):
    """
    Multiple calls to GET /license/machine-id should return same value.
    """
    resp1 = client.get("/license/machine-id")
    resp2 = client.get("/license/machine-id")

    assert resp1.json()["machine_id"] == resp2.json()["machine_id"]


def test_license_status_not_activated(client):
    """
    GET /license/status should indicate no license when not activated.
    """
    resp = client.get("/license/status")
    # Could be 404 or 200 with not_activated status
    assert resp.status_code in [200, 404], resp.text

    if resp.status_code == 200:
        payload = resp.json()
        assert payload.get("status") in ["not_activated", None]


def test_activate_license_valid(client):
    """
    POST /license/activate should activate a valid license.
    """
    machine_id = get_machine_id()

    # Create a valid license file
    license_content = LicenseValidator.create_license_file(
        license_key="TEST-LICENSE-001",
        license_type="standard",
        expires_at=datetime.utcnow() + timedelta(days=30),
        features=["feature1", "feature2"],
        max_users=10,
        max_plants=5,
        max_lines=20,
        allowed_machine_ids=[machine_id],
    )

    resp = client.post(
        "/license/activate",
        json={"license_file": license_content},
    )
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert payload["license_key"] == "TEST-LICENSE-001"
    assert payload["license_type"] == "standard"


def test_activate_license_invalid_signature(client):
    """
    POST /license/activate should reject license with invalid signature.
    """
    import base64
    import json

    # Create a license with tampered signature
    machine_id = get_machine_id()
    fake_license = {
        "payload": {
            "license_key": "FAKE-KEY",
            "license_type": "standard",
            "issued_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
            "features": [],
            "max_users": 10,
            "max_plants": 5,
            "max_lines": 20,
            "allowed_machine_ids": [machine_id],
        },
        "signature": "invalid-signature-00000000000000000000000000000000",
    }
    license_content = base64.b64encode(json.dumps(fake_license).encode()).decode()

    resp = client.post(
        "/license/activate",
        json={"license_file": license_content},
    )
    assert resp.status_code == 400, resp.text
    assert "invalid" in resp.json()["detail"].lower() or "signature" in resp.json()["detail"].lower()


def test_activate_license_wrong_machine(client):
    """
    POST /license/activate should reject license for different machine.
    """
    # Create a license for wrong machine
    license_content = LicenseValidator.create_license_file(
        license_key="WRONG-MACHINE-KEY",
        license_type="standard",
        expires_at=datetime.utcnow() + timedelta(days=30),
        features=[],
        max_users=10,
        max_plants=5,
        max_lines=20,
        allowed_machine_ids=["wrong-machine-id-12345"],
    )

    resp = client.post(
        "/license/activate",
        json={"license_file": license_content},
    )
    assert resp.status_code == 400, resp.text
    assert "machine" in resp.json()["detail"].lower()


def test_activate_license_expired(client):
    """
    POST /license/activate should reject expired license.
    """
    machine_id = get_machine_id()

    # Create an expired license
    license_content = LicenseValidator.create_license_file(
        license_key="EXPIRED-KEY",
        license_type="standard",
        expires_at=datetime.utcnow() - timedelta(days=1),  # Already expired
        features=[],
        max_users=10,
        max_plants=5,
        max_lines=20,
        allowed_machine_ids=[machine_id],
    )

    resp = client.post(
        "/license/activate",
        json={"license_file": license_content},
    )
    assert resp.status_code == 400, resp.text
    assert "expired" in resp.json()["detail"].lower()


def test_license_status_after_activation(client):
    """
    GET /license/status should return license info after activation.
    """
    machine_id = get_machine_id()

    # Activate a license
    license_content = LicenseValidator.create_license_file(
        license_key="STATUS-TEST-KEY",
        license_type="enterprise",
        expires_at=datetime.utcnow() + timedelta(days=90),
        features=["advanced", "analytics"],
        max_users=50,
        max_plants=20,
        max_lines=100,
        allowed_machine_ids=[machine_id],
    )

    activate_resp = client.post(
        "/license/activate",
        json={"license_file": license_content},
    )
    assert activate_resp.status_code == 200

    # Check status
    status_resp = client.get("/license/status")
    assert status_resp.status_code == 200

    payload = status_resp.json()
    assert payload["license_key"] == "STATUS-TEST-KEY"
    assert payload["license_type"] == "enterprise"
    assert payload["max_users"] == 50


def test_validate_license(client):
    """
    GET /license/validate should validate the activated license.
    """
    machine_id = get_machine_id()

    # Activate a license
    license_content = LicenseValidator.create_license_file(
        license_key="VALIDATE-TEST-KEY",
        license_type="standard",
        expires_at=datetime.utcnow() + timedelta(days=60),
        features=["feature1"],
        max_users=10,
        max_plants=5,
        max_lines=20,
        allowed_machine_ids=[machine_id],
    )

    client.post(
        "/license/activate",
        json={"license_file": license_content},
    )

    # Validate
    resp = client.get("/license/validate")
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["is_valid"] is True
    assert payload["status"] == "valid"
    assert payload["days_remaining"] >= 59


def test_license_features(client):
    """
    Activated license should expose its features.
    """
    machine_id = get_machine_id()

    license_content = LicenseValidator.create_license_file(
        license_key="FEATURES-KEY",
        license_type="enterprise",
        expires_at=datetime.utcnow() + timedelta(days=30),
        features=["advanced_reporting", "api_access", "custom_themes"],
        max_users=100,
        max_plants=50,
        max_lines=200,
        allowed_machine_ids=[machine_id],
    )

    client.post(
        "/license/activate",
        json={"license_file": license_content},
    )

    status_resp = client.get("/license/status")
    assert status_resp.status_code == 200

    features = status_resp.json()["features"]
    assert "advanced_reporting" in features
    assert "api_access" in features
    assert "custom_themes" in features
