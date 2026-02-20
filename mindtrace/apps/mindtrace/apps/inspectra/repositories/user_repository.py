"""
User repository for Inspectra using Mindtrace ODM.

Provides CRUD and query operations for User documents via MongoMindtraceODM.
Supports listing by organization, search, and pagination.
"""

import re
from typing import Any, Dict, List, Optional

from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import User
from mindtrace.apps.inspectra.models.enums import UserRole, UserStatus
from mindtrace.apps.inspectra.repositories.organization_repository import OrganizationRepository

SEARCH_QUERY_MAX_LEN = 150
SEARCH_QUERY_MIN_LEN = 1


def _build_search_filter(search: str) -> Optional[Dict[str, Any]]:
    """Build MongoDB $or filter for partial, case-insensitive match on name and email.

    Args:
        search: Query string to match against first_name, last_name, email.

    Returns:
        Dict suitable for MongoDB find, or None if search is empty or out of length bounds.
    """
    q = (search or "").strip()
    if len(q) < SEARCH_QUERY_MIN_LEN or len(q) > SEARCH_QUERY_MAX_LEN:
        return None
    escaped = re.escape(q)
    pattern = f"{escaped}"
    regex = {"$regex": pattern, "$options": "i"}
    return {
        "$or": [
            {"first_name": regex},
            {"last_name": regex},
            {"email": regex},
        ]
    }


class UserRepository:
    """User CRUD and queries via MongoMindtraceODM.

    All operations use the global ODM (user and organization models). Supports
    get by id or email, list by organization, list all, and pagination with
    optional search.
    """

    def __init__(self) -> None:
        self._org_repo = OrganizationRepository()

    async def get_by_id(self, user_id: str, fetch_links: bool = True) -> Optional[User]:
        """Get a user by id.

        Args:
            user_id: The user's document id.
            fetch_links: If True, resolve linked documents (e.g. organization). Defaults to True.

        Returns:
            The User if found, otherwise None.
        """
        odm = get_odm()
        try:
            return await odm.user.get(user_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def get_by_email(self, email: str, fetch_links: bool = True) -> Optional[User]:
        """Get a user by email (case-insensitive, via email_norm index).

        Args:
            email: Email address (normalized to lowercase for lookup).
            fetch_links: If True, resolve linked documents. Defaults to True.

        Returns:
            The User if found, otherwise None.
        """
        odm = get_odm()
        email_norm = email.casefold().strip()
        found = await odm.user.find({"email_norm": email_norm}, fetch_links=fetch_links)
        return found[0] if found else None

    async def list_by_organization(
        self,
        organization_id: str,
        fetch_links: bool = False,
        skip: int = 0,
        limit: int = 0,
        search: Optional[str] = None,
    ) -> List[User]:
        """List users that belong to the given organization.

        Results are ordered by created_at descending. Optional search filters
        by first_name, last_name, or email (case-insensitive partial match).

        Args:
            organization_id: Organization document id.
            fetch_links: If True, resolve linked documents. Defaults to False.
            skip: Number of records to skip. Defaults to 0.
            limit: Max records to return; 0 means no limit. Defaults to 0.
            search: Optional search string for name/email. Defaults to None.

        Returns:
            List of User documents.
        """
        get_odm()
        oid = PydanticObjectId(organization_id)
        search_filter = _build_search_filter(search) if search else None
        if search_filter:
            base = {"organization.$id": oid}
            filter_dict: Dict[str, Any] = {"$and": [base, search_filter]}
            query = User.find(filter_dict, fetch_links=fetch_links)
        else:
            query = User.find(User.organization.id == oid, fetch_links=fetch_links)
        query = query.sort([("created_at", -1)])
        if skip > 0:
            query = query.skip(skip)
        if limit > 0:
            query = query.limit(limit)
        return await query.to_list()

    async def count_by_organization(self, organization_id: str, search: Optional[str] = None) -> int:
        """Count users in the given organization.

        Args:
            organization_id: Organization document id.
            search: Optional search string for name/email. Defaults to None.

        Returns:
            Total count of matching users.
        """
        get_odm()
        oid = PydanticObjectId(organization_id)
        search_filter = _build_search_filter(search) if search else None
        if search_filter:
            base = {"organization.$id": oid}
            filter_dict: Dict[str, Any] = {"$and": [base, search_filter]}
            return await User.find(filter_dict).count()
        return await User.find(User.organization.id == oid).count()

    async def list_all(
        self,
        fetch_links: bool = False,
        skip: int = 0,
        limit: int = 0,
        search: Optional[str] = None,
    ) -> List[User]:
        """List all users (intended for super_admin).

        Results ordered by created_at descending. Optional search filters
        by first_name, last_name, or email.

        Args:
            fetch_links: If True, resolve linked documents. Defaults to False.
            skip: Number of records to skip. Defaults to 0.
            limit: Max records to return; 0 means no limit. Defaults to 0.
            search: Optional search string. Defaults to None.

        Returns:
            List of User documents.
        """
        get_odm()
        search_filter = _build_search_filter(search) if search else None
        if search_filter:
            query = User.find(search_filter, fetch_links=fetch_links)
        else:
            query = User.find(fetch_links=fetch_links)
        query = query.sort([("created_at", -1)])
        if skip > 0:
            query = query.skip(skip)
        if limit > 0:
            query = query.limit(limit)
        return await query.to_list()

    async def count_all(self, search: Optional[str] = None) -> int:
        """Count all users.

        Args:
            search: Optional search string for name/email. Defaults to None.

        Returns:
            Total count of users.
        """
        get_odm()
        search_filter = _build_search_filter(search) if search else None
        if search_filter:
            return await User.find(search_filter).count()
        return await User.count()

    async def create(
        self,
        *,
        email: str,
        pw_hash: str,
        role: UserRole,
        organization_id: str,
        first_name: str,
        last_name: str,
    ) -> User:
        """Create a user.

        The organization must already exist. email_norm is set automatically
        via the User model's before_save.

        Args:
            email: User email (stored and normalized for lookup).
            pw_hash: Pre-hashed password (use core.security.hash_password).
            role: User role (e.g. admin, user).
            organization_id: Id of the organization the user belongs to.
            first_name: Given name.
            last_name: Family name.

        Returns:
            The inserted User document.

        Raises:
            ValueError: If organization_id is not found or email is already registered.
        """
        org = await self._org_repo.get(organization_id)
        if not org:
            raise ValueError(f"Organization {organization_id} not found")
        odm = get_odm()
        user = User(
            organization=org,
            email=email,
            role=role,
            first_name=first_name,
            last_name=last_name,
            pw_hash=pw_hash,
        )
        try:
            return await odm.user.insert(user)
        except DuplicateKeyError as exc:
            raise ValueError("Email already registered") from exc

    async def update(
        self,
        user_id: str,
        *,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> Optional[User]:
        """Update a user's role, status, or name fields.

        Only provided keyword arguments are updated.

        Args:
            user_id: The user's document id.
            role: New role; if None, not updated.
            status: New status (UserStatus); if None, not updated.
            first_name: New first name; if None, not updated.
            last_name: New last name; if None, not updated.

        Returns:
            The updated User, or None if the user was not found.
        """
        user = await self.get_by_id(user_id)
        if not user:
            return None
        if role is not None:
            user.role = role
        if status is not None:
            user.status = status
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        odm = get_odm()
        return await odm.user.update(user)
