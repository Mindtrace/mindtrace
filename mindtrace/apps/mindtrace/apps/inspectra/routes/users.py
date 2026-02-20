"""User CRUD endpoints (ADMIN scoped to org, SUPER_ADMIN global)."""

from typing import Optional

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import (
    get_inspectra_service,
    hash_password,
    require_admin_or_super,
    validate_password_strength,
)
from mindtrace.apps.inspectra.models import User
from mindtrace.apps.inspectra.models.enums import UserRole
from mindtrace.apps.inspectra.schemas.user import (
    CreateUserRequest,
    CreateUserSchema,
    GetUserSchema,
    ListUsersSchema,
    UpdateUserRequest,
    UpdateUserSchema,
    UserListResponse,
    UserResponse,
)


def user_to_response(user: User) -> UserResponse:
    """Build UserResponse from a User document."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        role=user.role,
        organization_id=user.organization_id,
        first_name=user.first_name,
        last_name=user.last_name,
        status=user.status,
    )


def register(service):
    """Register user routes on the given InspectraService."""
    deps = [Depends(require_admin_or_super)]
    service.add_endpoint(
        "/users",
        list_users,
        schema=ListUsersSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/users",
        create_user,
        schema=CreateUserSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/users/{id}",
        get_user,
        schema=GetUserSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/users/{id}",
        update_user,
        schema=UpdateUserSchema,
        methods=["PUT", "PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_users(
    user: User = Depends(require_admin_or_super),
    organization_id: Optional[str] = Query(
        None,
        description="Filter by organization (SUPER_ADMIN only). Omit for all.",
    ),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=500, description="Max items per page"),
    search: Optional[str] = Query(
        None,
        max_length=150,
        description="Partial search in first name, last name, and email (case-insensitive).",
    ),
    service=Depends(get_inspectra_service),
) -> UserListResponse:
    """List users. SUPER_ADMIN can filter by org or get all; ADMIN sees only their org."""
    search_trimmed = (search or "").strip() or None
    if user.role == UserRole.SUPER_ADMIN:
        if organization_id:
            total = await service.user_repo.count_by_organization(organization_id, search=search_trimmed)
            users = await service.user_repo.list_by_organization(
                organization_id,
                fetch_links=True,
                skip=skip,
                limit=limit,
                search=search_trimmed,
            )
        else:
            total = await service.user_repo.count_all(search=search_trimmed)
            users = await service.user_repo.list_all(
                fetch_links=True,
                skip=skip,
                limit=limit,
                search=search_trimmed,
            )
    else:
        org_id = user.organization_id
        total = await service.user_repo.count_by_organization(org_id, search=search_trimmed)
        users = await service.user_repo.list_by_organization(
            org_id,
            fetch_links=True,
            skip=skip,
            limit=limit,
            search=search_trimmed,
        )
    items = [user_to_response(u) for u in users]
    return UserListResponse(items=items, total=total)


async def create_user(
    payload: CreateUserRequest,
    user: User = Depends(require_admin_or_super),
    service=Depends(get_inspectra_service),
) -> UserResponse:
    """Create a user. ADMIN: own org only; cannot create SUPER_ADMIN."""
    if user.role == UserRole.ADMIN and payload.role == UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin cannot create super_admin users",
        )
    if user.role == UserRole.ADMIN and payload.organization_id != user.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin can only create users in their organization",
        )
    errors = validate_password_strength(payload.password)
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Password does not meet requirements", "errors": errors},
        )
    email = (payload.email or "").strip().lower()
    existing = await service.user_repo.get_by_email(email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    pw_hash = hash_password(payload.password)
    try:
        new_user = await service.user_repo.create(
            email=email,
            pw_hash=pw_hash,
            role=payload.role,
            organization_id=payload.organization_id,
            first_name=payload.first_name,
            last_name=payload.last_name,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return user_to_response(new_user)


async def get_user(
    id_: str = Path(alias="id"),
    user: User = Depends(require_admin_or_super),
    service=Depends(get_inspectra_service),
) -> UserResponse:
    """Get a user by id. ADMIN: only users in own organization."""
    target = await service.user_repo.get_by_id(id_)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role == UserRole.ADMIN and target.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not in your organization")
    return user_to_response(target)


async def update_user(
    id_: str = Path(alias="id"),
    payload: UpdateUserRequest = ...,
    user: User = Depends(require_admin_or_super),
    service=Depends(get_inspectra_service),
) -> UserResponse:
    """Update a user's role, status, or name. ADMIN: own org only; cannot set SUPER_ADMIN."""
    target = await service.user_repo.get_by_id(id_)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role == UserRole.ADMIN and target.organization_id != user.organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not in your organization")
    new_role = getattr(payload, "role", None)
    if user.role == UserRole.ADMIN and new_role == UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin cannot assign super_admin role",
        )
    updated = await service.user_repo.update(
        id_,
        role=new_role,
        status=getattr(payload, "status", None),
        first_name=getattr(payload, "first_name", None),
        last_name=getattr(payload, "last_name", None),
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user_to_response(updated)
