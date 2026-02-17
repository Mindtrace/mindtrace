"""Integration tests for user management endpoints."""


def _register_user(client, username: str, password: str) -> dict:
    """Helper to register a user and return the token response."""
    resp = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _get_auth_header(client, username: str, password: str) -> dict:
    """Helper to get auth headers for a user."""
    resp = client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_admin_user(client) -> dict:
    """Helper to create an admin user and return auth headers."""
    # First create admin role
    client.post(
        "/roles",
        json={
            "name": "admin",
            "description": "Administrator role",
            "permissions": ["*"],
        },
    )

    # Register a user
    _register_user(client, "admin_user", "adminpass123")

    # Get the user and update their role to admin
    # Since we don't have direct access, we'll login and verify
    return _get_auth_header(client, "admin_user", "adminpass123")


def test_list_users(client):
    """
    GET /admin/users should list all users with pagination.
    """
    # Create some users
    _register_user(client, "user1", "password1")
    _register_user(client, "user2", "password2")

    resp = client.get("/admin/users")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert isinstance(payload, dict)
    assert "items" in payload
    assert "total" in payload
    assert payload["total"] >= 2


def test_list_users_pagination(client):
    """
    GET /admin/users should support page and page_size pagination.
    """
    # Create 5 users
    for i in range(5):
        _register_user(client, f"paguser{i}", f"password{i}")

    # Get first page with 2 items
    resp = client.get("/admin/users?page=1&page_size=2")
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload["items"]) == 2
    assert payload["total"] >= 5

    # Get second page with 2 items
    resp2 = client.get("/admin/users?page=2&page_size=2")
    assert resp2.status_code == 200
    payload2 = resp2.json()
    assert len(payload2["items"]) == 2

    # Ensure different users
    first_ids = {u["id"] for u in payload["items"]}
    second_ids = {u["id"] for u in payload2["items"]}
    assert first_ids.isdisjoint(second_ids)


def test_get_user_by_id(client):
    """
    GET /admin/users/{id} should return specific user.
    """
    # Register a user
    _register_user(client, "fetchme", "password123")

    # List to get the ID
    list_resp = client.get("/admin/users")
    users = list_resp.json()["items"]
    user = next(u for u in users if u["username"] == "fetchme")
    user_id = user["id"]

    # Get by ID
    resp = client.get(f"/admin/users/{user_id}")
    assert resp.status_code == 200

    fetched = resp.json()
    assert fetched["id"] == user_id
    assert fetched["username"] == "fetchme"


def test_create_user_via_admin(client):
    """
    POST /admin/users should create a new user.
    """
    # First create a role
    role_resp = client.post(
        "/roles",
        json={"name": "operator", "description": "Operator role"},
    )
    role_id = role_resp.json()["id"]

    # Create user via admin endpoint
    resp = client.post(
        "/admin/users",
        json={
            "username": "newadminuser",
            "password": "securepass123",
            "role_id": role_id,
        },
    )
    assert resp.status_code == 200, resp.text

    user = resp.json()
    assert user["username"] == "newadminuser"
    assert user["role_id"] == role_id
    assert "id" in user


def test_update_user(client):
    """
    PUT /admin/users/{id} should update user fields.
    """
    # Register a user
    _register_user(client, "updateme", "password123")

    # Get user ID
    list_resp = client.get("/admin/users")
    users = list_resp.json()["items"]
    user = next(u for u in users if u["username"] == "updateme")
    user_id = user["id"]

    # Create a new role
    role_resp = client.post(
        "/roles",
        json={"name": "supervisor", "description": "Supervisor role"},
    )
    new_role_id = role_resp.json()["id"]

    # Update the user
    update_resp = client.put(
        f"/admin/users/{user_id}",
        json={"role_id": new_role_id, "is_active": False},
    )
    assert update_resp.status_code == 200

    updated = update_resp.json()
    assert updated["role_id"] == new_role_id
    assert updated["is_active"] is False


def test_deactivate_user(client):
    """
    POST /admin/users/{id}/deactivate should deactivate user.
    """
    # Register a user
    _register_user(client, "deactivateme", "password123")

    # Get user ID
    list_resp = client.get("/admin/users")
    users = list_resp.json()["items"]
    user = next(u for u in users if u["username"] == "deactivateme")
    user_id = user["id"]

    # Verify initially active
    assert user["is_active"] is True

    # Deactivate
    resp = client.post(f"/admin/users/{user_id}/deactivate")
    assert resp.status_code == 200

    # Verify deactivated
    get_resp = client.get(f"/admin/users/{user_id}")
    assert get_resp.json()["is_active"] is False


def test_activate_user(client):
    """
    POST /admin/users/{id}/activate should activate user.
    """
    # Register and deactivate a user
    _register_user(client, "activateme", "password123")

    list_resp = client.get("/admin/users")
    users = list_resp.json()["items"]
    user = next(u for u in users if u["username"] == "activateme")
    user_id = user["id"]

    client.post(f"/admin/users/{user_id}/deactivate")

    # Activate
    resp = client.post(f"/admin/users/{user_id}/activate")
    assert resp.status_code == 200

    # Verify activated
    get_resp = client.get(f"/admin/users/{user_id}")
    assert get_resp.json()["is_active"] is True


def test_admin_reset_password(client):
    """
    POST /admin/users/{id}/reset-password should allow admin to reset password.
    """
    # Register a user
    _register_user(client, "resetpwuser", "oldpassword")

    # Get user ID
    list_resp = client.get("/admin/users")
    users = list_resp.json()["items"]
    user = next(u for u in users if u["username"] == "resetpwuser")
    user_id = user["id"]

    # Reset password
    resp = client.post(
        f"/admin/users/{user_id}/reset-password",
        json={"new_password": "newpassword123"},
    )
    assert resp.status_code == 200

    # Verify can login with new password
    login_resp = client.post(
        "/auth/login",
        json={"username": "resetpwuser", "password": "newpassword123"},
    )
    assert login_resp.status_code == 200


def test_delete_user(client):
    """
    DELETE /admin/users/{id} should remove user.
    """
    # Register a user
    _register_user(client, "deleteme", "password123")

    # Get user ID
    list_resp = client.get("/admin/users")
    users = list_resp.json()["items"]
    user = next(u for u in users if u["username"] == "deleteme")
    user_id = user["id"]

    # Delete
    resp = client.delete(f"/admin/users/{user_id}")
    assert resp.status_code == 200

    # Verify gone
    get_resp = client.get(f"/admin/users/{user_id}")
    assert get_resp.status_code == 404


def test_get_own_profile(client):
    """
    GET /me should return current user's profile.
    """
    # Register and login
    _register_user(client, "meuser", "password123")
    headers = _get_auth_header(client, "meuser", "password123")

    # Get own profile
    resp = client.get("/me", headers=headers)
    assert resp.status_code == 200

    profile = resp.json()
    assert profile["username"] == "meuser"
    assert "id" in profile


def test_change_own_password(client):
    """
    PUT /me/password should allow user to change their own password.
    """
    # Register and login
    _register_user(client, "changepwuser", "oldpass123")
    headers = _get_auth_header(client, "changepwuser", "oldpass123")

    # Change password
    resp = client.put(
        "/me/password",
        headers=headers,
        json={
            "current_password": "oldpass123",
            "new_password": "newpass456",
        },
    )
    assert resp.status_code == 200

    # Verify can login with new password
    login_resp = client.post(
        "/auth/login",
        json={"username": "changepwuser", "password": "newpass456"},
    )
    assert login_resp.status_code == 200


def test_change_own_password_wrong_current(client):
    """
    PUT /me/password should fail with wrong current password.
    """
    # Register and login
    _register_user(client, "wrongpwuser", "correctpass")
    headers = _get_auth_header(client, "wrongpwuser", "correctpass")

    # Try to change with wrong current password
    resp = client.put(
        "/me/password",
        headers=headers,
        json={
            "current_password": "wrongpass",
            "new_password": "newpass456",
        },
    )
    assert resp.status_code == 400
    assert "incorrect" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# User-Plant linking tests
# ---------------------------------------------------------------------------


def test_create_user_with_plant_link(client):
    """
    POST /admin/users should allow creating a user linked to a plant.
    """
    # Create a plant first
    plant_resp = client.post(
        "/plants",
        json={"name": "Assembly Plant", "code": "AP", "location": "Factory 1"},
    )
    assert plant_resp.status_code == 200
    plant_id = plant_resp.json()["id"]

    # Create a role
    role_resp = client.post(
        "/roles",
        json={"name": "floor_supervisor", "description": "Floor supervisor"},
    )
    role_id = role_resp.json()["id"]

    # Create user linked to plant
    user_resp = client.post(
        "/admin/users",
        json={
            "username": "plant_operator_1",
            "password": "SecurePass123",
            "role_id": role_id,
            "plant_id": plant_id,
        },
    )
    assert user_resp.status_code == 200, user_resp.text

    user = user_resp.json()
    assert user["plant_id"] == plant_id
    assert user["username"] == "plant_operator_1"


def test_create_user_without_plant_link(client):
    """
    POST /admin/users should allow creating a user without plant link.
    """
    # Create a role
    role_resp = client.post(
        "/roles",
        json={"name": "global_admin", "description": "Global admin"},
    )
    role_id = role_resp.json()["id"]

    # Create user without plant
    user_resp = client.post(
        "/admin/users",
        json={
            "username": "global_user_1",
            "password": "SecurePass123",
            "role_id": role_id,
        },
    )
    assert user_resp.status_code == 200, user_resp.text

    user = user_resp.json()
    assert user["plant_id"] is None


def test_update_user_plant_link(client):
    """
    PUT /admin/users/{id} should allow updating a user's plant link.
    """
    # Create two plants
    plant1_resp = client.post(
        "/plants",
        json={"name": "Plant 1", "code": "P1", "location": "Location 1"},
    )
    plant1_id = plant1_resp.json()["id"]

    plant2_resp = client.post(
        "/plants",
        json={"name": "Plant 2", "code": "P2", "location": "Location 2"},
    )
    plant2_id = plant2_resp.json()["id"]

    # Register a user
    _register_user(client, "movable_user", "Pass123")

    # Get user ID
    list_resp = client.get("/admin/users")
    users = list_resp.json()["items"]
    user = next(u for u in users if u["username"] == "movable_user")
    user_id = user["id"]

    # Update to plant1
    update_resp = client.put(
        f"/admin/users/{user_id}",
        json={"plant_id": plant1_id},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["plant_id"] == plant1_id

    # Move to plant2
    move_resp = client.put(
        f"/admin/users/{user_id}",
        json={"plant_id": plant2_id},
    )
    assert move_resp.status_code == 200
    assert move_resp.json()["plant_id"] == plant2_id


def test_list_users_filtered_by_plant(client):
    """
    GET /admin/users?plant_id=xxx should filter users by plant.
    """
    # Create plants
    plant_a_resp = client.post(
        "/plants",
        json={"name": "Plant A", "code": "PA"},
    )
    plant_a = plant_a_resp.json()["id"]

    plant_b_resp = client.post(
        "/plants",
        json={"name": "Plant B", "code": "PB"},
    )
    plant_b = plant_b_resp.json()["id"]

    # Create role
    role_resp = client.post(
        "/roles",
        json={"name": "operator_role"},
    )
    role_id = role_resp.json()["id"]

    # Create users in different plants
    for i in range(3):
        client.post(
            "/admin/users",
            json={
                "username": f"operator_a_{i}",
                "password": "Pass123",
                "role_id": role_id,
                "plant_id": plant_a,
            },
        )

    for i in range(2):
        client.post(
            "/admin/users",
            json={
                "username": f"operator_b_{i}",
                "password": "Pass123",
                "role_id": role_id,
                "plant_id": plant_b,
            },
        )

    # List users for plant_a
    resp_a = client.get(f"/admin/users?plant_id={plant_a}")
    assert resp_a.status_code == 200

    users_a = resp_a.json()["items"]
    usernames_a = {u["username"] for u in users_a}

    # Should include plant_a users
    assert any(name.startswith("operator_a_") for name in usernames_a)
    # Should not include plant_b users
    assert not any(name.startswith("operator_b_") for name in usernames_a)


def test_user_response_includes_plant_id(client):
    """
    GET /admin/users/{id} should include plant_id in response.
    """
    # Create plant
    plant_resp = client.post(
        "/plants",
        json={"name": "Test Plant", "code": "TP"},
    )
    plant_id = plant_resp.json()["id"]

    # Create role
    role_resp = client.post(
        "/roles",
        json={"name": "test_role"},
    )
    role_id = role_resp.json()["id"]

    # Create user with plant
    user_resp = client.post(
        "/admin/users",
        json={
            "username": "plant_test_user",
            "password": "Pass123",
            "role_id": role_id,
            "plant_id": plant_id,
        },
    )
    user_id = user_resp.json()["id"]

    # Get user by ID
    get_resp = client.get(f"/admin/users/{user_id}")
    assert get_resp.status_code == 200

    user = get_resp.json()
    assert "plant_id" in user
    assert user["plant_id"] == plant_id


def test_get_own_profile_includes_plant_id(client):
    """
    GET /me should include plant_id in the profile response.
    """
    # Create plant
    plant_resp = client.post(
        "/plants",
        json={"name": "Profile Test Plant", "code": "PTP"},
    )
    plant_id = plant_resp.json()["id"]

    # Create role
    role_resp = client.post(
        "/roles",
        json={"name": "profile_test_role"},
    )
    role_id = role_resp.json()["id"]

    # Create user with plant via admin endpoint
    client.post(
        "/admin/users",
        json={
            "username": "profile_plant_user",
            "password": "Pass123",
            "role_id": role_id,
            "plant_id": plant_id,
        },
    )

    # Login and get own profile
    headers = _get_auth_header(client, "profile_plant_user", "Pass123")
    resp = client.get("/me", headers=headers)
    assert resp.status_code == 200

    profile = resp.json()
    assert "plant_id" in profile
    assert profile["plant_id"] == plant_id
