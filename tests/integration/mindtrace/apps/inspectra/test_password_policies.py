"""Integration tests for password policy endpoints."""


def test_list_password_policies_empty(client):
    """
    GET /admin/password-policies should return empty list when no policies exist.

    Verifies:
    - response is a dictionary with items and total
    - initially returns empty list
    """
    resp = client.get("/admin/password-policies")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert isinstance(payload["total"], int)
    assert payload["total"] == 0


def test_create_password_policy(client):
    """
    POST /admin/password-policies should create a new policy.

    Verifies:
    - policy creation succeeds
    - returned payload contains expected fields
    - a non-empty ID is generated
    """
    resp = client.post(
        "/admin/password-policies",
        json={
            "name": "Strong Password Policy",
            "description": "Requires strong passwords",
            "rules": [
                {
                    "rule_type": "min_length",
                    "value": 8,
                    "message": "Password must be at least 8 characters",
                    "is_active": True,
                    "order": 0,
                },
                {
                    "rule_type": "require_uppercase",
                    "value": True,
                    "message": "Password must contain uppercase",
                    "is_active": True,
                    "order": 1,
                },
            ],
            "is_active": True,
            "is_default": True,
        },
    )
    assert resp.status_code == 200, resp.text

    policy = resp.json()
    assert policy["name"] == "Strong Password Policy"
    assert "id" in policy
    assert len(policy["rules"]) == 2


def test_create_and_list_policies(client):
    """
    Creating a policy should increase total count and appear in listings.
    """
    before = client.get("/admin/password-policies")
    assert before.status_code == 200
    before_total = before.json()["total"]

    create_resp = client.post(
        "/admin/password-policies",
        json={
            "name": "Test Policy",
            "description": "Test",
            "rules": [],
            "is_active": True,
            "is_default": False,
        },
    )
    assert create_resp.status_code == 200
    created_id = create_resp.json()["id"]

    after = client.get("/admin/password-policies")
    assert after.status_code == 200
    payload = after.json()

    assert payload["total"] == before_total + 1
    assert any(p["id"] == created_id for p in payload["items"])


def test_get_policy_by_id(client):
    """
    GET /admin/password-policies/{id} should return specific policy.
    """
    # Create a policy first
    create_resp = client.post(
        "/admin/password-policies",
        json={
            "name": "Fetch Test Policy",
            "description": "For get by ID test",
            "rules": [
                {
                    "rule_type": "min_length",
                    "value": 10,
                    "message": "Min 10 chars",
                    "is_active": True,
                    "order": 0,
                }
            ],
            "is_active": True,
            "is_default": False,
        },
    )
    assert create_resp.status_code == 200
    policy_id = create_resp.json()["id"]

    # Fetch by ID
    get_resp = client.get(f"/admin/password-policies/{policy_id}")
    assert get_resp.status_code == 200

    policy = get_resp.json()
    assert policy["id"] == policy_id
    assert policy["name"] == "Fetch Test Policy"
    assert len(policy["rules"]) == 1


def test_update_policy(client):
    """
    PUT /admin/password-policies/{id} should update policy fields.
    """
    # Create a policy
    create_resp = client.post(
        "/admin/password-policies",
        json={
            "name": "Original Name",
            "description": "Original Description",
            "rules": [],
            "is_active": True,
            "is_default": False,
        },
    )
    assert create_resp.status_code == 200
    policy_id = create_resp.json()["id"]

    # Update the policy
    update_resp = client.put(
        f"/admin/password-policies/{policy_id}",
        json={
            "name": "Updated Name",
            "description": "Updated Description",
            "is_active": False,
        },
    )
    assert update_resp.status_code == 200

    updated = update_resp.json()
    assert updated["name"] == "Updated Name"
    assert updated["description"] == "Updated Description"
    assert updated["is_active"] is False


def test_delete_policy(client):
    """
    DELETE /admin/password-policies/{id} should remove policy.
    """
    # Create a policy
    create_resp = client.post(
        "/admin/password-policies",
        json={
            "name": "To Be Deleted",
            "description": "Will be deleted",
            "rules": [],
            "is_active": True,
            "is_default": False,
        },
    )
    assert create_resp.status_code == 200
    policy_id = create_resp.json()["id"]

    # Verify it exists
    get_resp = client.get(f"/admin/password-policies/{policy_id}")
    assert get_resp.status_code == 200

    # Delete it
    delete_resp = client.delete(f"/admin/password-policies/{policy_id}")
    assert delete_resp.status_code == 200

    # Verify it's gone
    get_after = client.get(f"/admin/password-policies/{policy_id}")
    assert get_after.status_code == 404


def test_add_rule_to_policy(client):
    """
    POST /admin/password-policies/{id}/rules should add rule to policy.
    """
    # Create a policy with no rules
    create_resp = client.post(
        "/admin/password-policies",
        json={
            "name": "Add Rule Test",
            "description": "Test adding rules",
            "rules": [],
            "is_active": True,
            "is_default": False,
        },
    )
    assert create_resp.status_code == 200
    policy_id = create_resp.json()["id"]

    # Add a rule
    add_rule_resp = client.post(
        f"/admin/password-policies/{policy_id}/rules",
        json={
            "rule_type": "require_digit",
            "value": True,
            "message": "Must contain a digit",
            "is_active": True,
            "order": 0,
        },
    )
    assert add_rule_resp.status_code == 200

    # Verify rule was added
    get_resp = client.get(f"/admin/password-policies/{policy_id}")
    assert get_resp.status_code == 200
    policy = get_resp.json()
    assert len(policy["rules"]) == 1
    assert policy["rules"][0]["rule_type"] == "require_digit"


def test_validate_password_success(client):
    """
    POST /password/validate should validate password against default policy.
    """
    # Create a default policy with min_length rule
    client.post(
        "/admin/password-policies",
        json={
            "name": "Default Policy",
            "description": "Default for validation",
            "rules": [
                {
                    "rule_type": "min_length",
                    "value": 8,
                    "message": "Password too short",
                    "is_active": True,
                    "order": 0,
                }
            ],
            "is_active": True,
            "is_default": True,
        },
    )

    # Validate a good password
    resp = client.post(
        "/password/validate",
        json={"password": "validpassword123"},
    )
    assert resp.status_code == 200

    result = resp.json()
    assert result["is_valid"] is True
    assert result["errors"] == []


def test_validate_password_failure(client):
    """
    POST /password/validate should return errors for invalid password.
    """
    # Create a default policy with min_length rule
    client.post(
        "/admin/password-policies",
        json={
            "name": "Strict Policy",
            "description": "Default for validation",
            "rules": [
                {
                    "rule_type": "min_length",
                    "value": 12,
                    "message": "Password must be at least 12 characters",
                    "is_active": True,
                    "order": 0,
                }
            ],
            "is_active": True,
            "is_default": True,
        },
    )

    # Validate a short password
    resp = client.post(
        "/password/validate",
        json={"password": "short"},
    )
    assert resp.status_code == 200

    result = resp.json()
    assert result["is_valid"] is False
    assert "Password must be at least 12 characters" in result["errors"]
