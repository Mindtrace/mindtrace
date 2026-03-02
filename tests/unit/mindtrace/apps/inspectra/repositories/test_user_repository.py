"""Unit tests for UserRepository and _build_search_filter (mocked ODM)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import DuplicateKeyError

from mindtrace.apps.inspectra.models import User
from mindtrace.apps.inspectra.models.enums import UserRole, UserStatus
from mindtrace.apps.inspectra.repositories import user_repository as user_repo_mod
from mindtrace.apps.inspectra.repositories.user_repository import (
    SEARCH_QUERY_MAX_LEN,
    SEARCH_QUERY_MIN_LEN,
    UserRepository,
    _build_search_filter,
)


def test_build_search_filter_none_returns_none():
    assert _build_search_filter(None) is None


def test_build_search_filter_empty_returns_none():
    assert _build_search_filter("") is None
    assert _build_search_filter("   ") is None


def test_build_search_filter_too_short_returns_none():
    assert _build_search_filter("") is None
    assert _build_search_filter("a" * (SEARCH_QUERY_MIN_LEN - 1)) is None


def test_build_search_filter_too_long_returns_none():
    assert _build_search_filter("a" * (SEARCH_QUERY_MAX_LEN + 1)) is None


def test_build_search_filter_valid_returns_or_filter():
    result = _build_search_filter("john")
    assert result is not None
    assert "$or" in result
    assert {"$regex": "john", "$options": "i"} in result["$or"][0].values()


@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_get_by_id_found(mock_get_odm):
    user = MagicMock(spec=User)
    odm = MagicMock()
    odm.user.get = AsyncMock(return_value=user)
    mock_get_odm.return_value = odm
    repo = UserRepository()
    result = await repo.get_by_id("507f1f77bcf86cd799439011")
    assert result is user


@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_get_by_id_exception_returns_none(mock_get_odm):
    odm = MagicMock()
    odm.user.get = AsyncMock(side_effect=Exception("error"))
    mock_get_odm.return_value = odm
    repo = UserRepository()
    result = await repo.get_by_id("507f1f77bcf86cd799439011")
    assert result is None


@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_get_by_email_found(mock_get_odm):
    user = MagicMock(spec=User)
    odm = MagicMock()
    odm.user.find = AsyncMock(return_value=[user])
    mock_get_odm.return_value = odm
    repo = UserRepository()
    result = await repo.get_by_email("a@b.com")
    assert result is user
    odm.user.find.assert_called_once()
    call_kw = odm.user.find.call_args[1]
    assert call_kw["fetch_links"] is True


@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_get_by_email_not_found(mock_get_odm):
    odm = MagicMock()
    odm.user.find = AsyncMock(return_value=[])
    mock_get_odm.return_value = odm
    repo = UserRepository()
    result = await repo.get_by_email("a@b.com")
    assert result is None


@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_create_org_not_found_raises(mock_get_odm):
    repo = UserRepository()
    with patch.object(repo, "_org_repo") as mock_org:
        mock_org.get = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="Organization.*not found"):
            await repo.create(
                email="u@b.com",
                pw_hash="h",
                role=UserRole.USER,
                organization_id="507f1f77bcf86cd799439011",
                first_name="F",
                last_name="L",
            )


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_create_success(mock_get_odm, mock_user_cls):
    org = MagicMock()
    repo = UserRepository()
    with patch.object(repo, "_org_repo") as mock_org:
        mock_org.get = AsyncMock(return_value=org)
        inserted = MagicMock(spec=User)
        mock_user_instance = MagicMock()
        mock_user_cls.return_value = mock_user_instance
        odm = MagicMock()
        odm.user.insert = AsyncMock(return_value=inserted)
        mock_get_odm.return_value = odm
        result = await repo.create(
            email="u@b.com",
            pw_hash="h",
            role=UserRole.USER,
            organization_id="507f1f77bcf86cd799439011",
            first_name="F",
            last_name="L",
        )
        assert result is inserted
        odm.user.insert.assert_called_once_with(mock_user_instance)


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_create_duplicate_key_raises(mock_get_odm, mock_user_cls):
    org = MagicMock()
    repo = UserRepository()
    with patch.object(repo, "_org_repo") as mock_org:
        mock_org.get = AsyncMock(return_value=org)
        mock_user_cls.return_value = MagicMock()
        odm = MagicMock()
        odm.user.insert = AsyncMock(side_effect=DuplicateKeyError("dup"))
        mock_get_odm.return_value = odm
        with pytest.raises(ValueError, match="Email already registered"):
            await repo.create(
                email="u@b.com",
                pw_hash="h",
                role=UserRole.USER,
                organization_id="507f1f77bcf86cd799439011",
                first_name="F",
                last_name="L",
            )


@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_update_not_found(mock_get_odm):
    repo = UserRepository()
    with patch.object(repo, "get_by_id", new_callable=AsyncMock, return_value=None):
        result = await repo.update("507f1f77bcf86cd799439011", first_name="X")
        assert result is None


@pytest.mark.asyncio
async def test_user_repo_update_found():
    user = MagicMock(spec=User)
    user.first_name = "Old"
    updated = MagicMock(spec=User)
    odm = MagicMock()
    odm.user.update = AsyncMock(return_value=updated)
    repo = UserRepository()
    with (
        patch.object(repo, "get_by_id", new_callable=AsyncMock, return_value=user),
        patch.object(user_repo_mod, "get_odm", return_value=odm),
    ):
        result = await repo.update(
            "507f1f77bcf86cd799439011",
            first_name="New",
            status=UserStatus.ACTIVE,
            role=UserRole.SUPER_ADMIN,
        )
        assert result is updated
        assert user.first_name == "New"
        assert user.status == UserStatus.ACTIVE
        assert user.role == UserRole.SUPER_ADMIN
    odm.user.update.assert_called_once_with(user)


def _make_query_mock(to_list_result=None, count_result=0):
    mock = MagicMock()
    mock.sort.return_value = mock
    mock.skip.return_value = mock
    mock.limit.return_value = mock
    mock.to_list = AsyncMock(return_value=to_list_result if to_list_result is not None else [])
    mock.count = AsyncMock(return_value=count_result)
    return mock


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_list_by_organization_no_search(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(to_list_result=[])
    repo = UserRepository()
    result = await repo.list_by_organization("507f1f77bcf86cd799439011")
    assert result == []
    mock_user.find.assert_called_once()


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_list_by_organization_with_search(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(to_list_result=[])
    repo = UserRepository()
    result = await repo.list_by_organization("507f1f77bcf86cd799439011", search="john")
    assert result == []
    assert mock_user.find.call_count == 1


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_list_by_organization_skip_limit(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(to_list_result=[])
    repo = UserRepository()
    await repo.list_by_organization("507f1f77bcf86cd799439011", skip=2, limit=5)
    chain = mock_user.find.return_value
    chain.skip.assert_called_once_with(2)
    chain.limit.assert_called_once_with(5)


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_count_by_organization(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(count_result=5)
    repo = UserRepository()
    result = await repo.count_by_organization("507f1f77bcf86cd799439011")
    assert result == 5


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_count_by_organization_with_search(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(count_result=2)
    repo = UserRepository()
    result = await repo.count_by_organization("507f1f77bcf86cd799439011", search="alice")
    assert result == 2


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_list_all(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(to_list_result=[])
    repo = UserRepository()
    result = await repo.list_all(skip=0, limit=10)
    assert result == []


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_list_all_with_search(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(to_list_result=[])
    repo = UserRepository()
    result = await repo.list_all(search="bob")
    assert result == []


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_list_all_skip_limit(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(to_list_result=[])
    repo = UserRepository()
    await repo.list_all(skip=1, limit=20)
    chain = mock_user.find.return_value
    chain.skip.assert_called_once_with(1)
    chain.limit.assert_called_once_with(20)


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_count_all(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.count = AsyncMock(return_value=7)
    repo = UserRepository()
    result = await repo.count_all()
    assert result == 7


@patch("mindtrace.apps.inspectra.repositories.user_repository.User")
@patch("mindtrace.apps.inspectra.repositories.user_repository.get_odm")
@pytest.mark.asyncio
async def test_user_repo_count_all_with_search(mock_get_odm, mock_user):
    mock_get_odm.return_value = MagicMock()
    mock_user.find.return_value = _make_query_mock(count_result=3)
    repo = UserRepository()
    result = await repo.count_all(search="jane")
    assert result == 3
