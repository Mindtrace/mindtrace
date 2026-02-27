"""Comprehensive unit tests for Redis ODM backend."""

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import Field

from mindtrace.database import MindtraceRedisDocument, RedisMindtraceODM
from mindtrace.database.backends.redis_odm import _ensure_redis_model_indexed


class RedisDocTest(MindtraceRedisDocument):
    name: str = Field(index=True)
    age: int = Field(index=True)
    email: str = Field(index=True)

    class Meta:
        global_key_prefix = "testapp"
        collection_name = "test_docs"


class RedisDocNoIndexTest(MindtraceRedisDocument):
    name: str
    age: int

    class Meta:
        global_key_prefix = "testapp"
        collection_name = "test_docs_no_index"


class RedisDocWithIndexNameTest(MindtraceRedisDocument):
    name: str = Field(index=True)

    class Meta:
        global_key_prefix = "testapp"
        collection_name = "test_docs"
        index_name = "custom_index_name"


class RedisDocWithModelKeyPrefixTest(MindtraceRedisDocument):
    name: str = Field(index=True)

    class Meta:
        global_key_prefix = "testapp"
        collection_name = "test_docs"
        model_key_prefix = "custom_prefix"


class RedisDocMainModuleTest(MindtraceRedisDocument):
    name: str = Field(index=True)

    class Meta:
        global_key_prefix = "testapp"
        collection_name = "test_docs"

    __module__ = "__main__"


def test_ensure_redis_model_indexed_not_type_or_not_subclass():
    """Test _ensure_redis_model_indexed returns early for non-type or non-Redis document."""
    _ensure_redis_model_indexed(None)
    _ensure_redis_model_indexed(str)
    _ensure_redis_model_indexed(int)


def test_ensure_redis_model_indexed_config_index_false():
    """Test _ensure_redis_model_indexed sets Config.index when model has Config class (no model_config dict)."""

    class ConfigModel(MindtraceRedisDocument):
        name: str = Field(index=True)

        class Config:
            index = False

        class Meta:
            global_key_prefix = "test"

    # Force the Config branch: remove model_config so the elif hasattr(Config) runs
    with patch.object(ConfigModel, "model_config", None):
        _ensure_redis_model_indexed(ConfigModel)
        assert ConfigModel.Config.index is True


def test_ensure_redis_model_indexed_expression_proxy_raises():
    """Test _ensure_redis_model_indexed handles Exception when setting ExpressionProxy."""
    # Patch where redis_odm uses it so the except block runs
    with patch("mindtrace.database.backends.redis_odm.ExpressionProxy", side_effect=RuntimeError("mock")):
        _ensure_redis_model_indexed(RedisDocTest)
    # Should not raise (except block catches)


def test_ensure_redis_model_indexed_sets_expression_proxy_on_fields():
    """Test _ensure_redis_model_indexed sets ExpressionProxy on each field."""
    from redis_om.model.model import ExpressionProxy

    class FreshModel(MindtraceRedisDocument):
        name: str = Field(index=True)
        email: str = Field(index=True)

        class Meta:
            global_key_prefix = "testapp"
            collection_name = "test_docs"

    _ensure_redis_model_indexed(FreshModel)
    assert isinstance(getattr(FreshModel, "name"), ExpressionProxy)
    assert isinstance(getattr(FreshModel, "email"), ExpressionProxy)


def test_ensure_redis_model_indexed_registers_model_for_migrator():
    """Test _ensure_redis_model_indexed registers model in redis-om model_registry."""
    from redis_om.model.model import model_registry

    class RegistryModel(MindtraceRedisDocument):
        name: str = Field(index=True)

        class Meta:
            global_key_prefix = "testapp"
            collection_name = "registry_docs"

    key = f"{RegistryModel.__module__}.{RegistryModel.__qualname__}"
    model_registry.pop(key, None)
    try:
        _ensure_redis_model_indexed(RegistryModel)
        assert key in model_registry
        assert model_registry[key] is RegistryModel
    finally:
        model_registry.pop(key, None)


def test_ensure_redis_model_indexed_field_name_mismatch():
    """Test _ensure_redis_model_indexed sets field.name when it differs from model_fields key."""
    # Use a model and patch one field to have .name != key so setattr(field, "name", field_name) runs
    model_fields = getattr(RedisDocTest, "model_fields", None) or getattr(RedisDocTest, "__fields__", None)
    assert model_fields, "RedisDocTest should have model_fields"
    # Use a model and give one field a wrong .name so setattr(field, "name", field_name) runs

    class ModelWithMismatchedFieldName(MindtraceRedisDocument):
        name: str = Field(index=True)
        age: int = Field(index=True)
        email: str = Field(index=True)

        class Meta:
            global_key_prefix = "testapp"
            collection_name = "test_docs"

    # Patch the email field's name to be wrong so getattr(field, "name", None) != "email"
    email_field = ModelWithMismatchedFieldName.model_fields["email"]
    original_name = getattr(email_field, "name", None)
    try:
        setattr(email_field, "name", "other")  # mismatch
        _ensure_redis_model_indexed(ModelWithMismatchedFieldName)
        assert getattr(email_field, "name", None) == "email"
    finally:
        if original_name is not None:
            setattr(email_field, "name", original_name)


def test_redis_ensure_index_ready_no_index():
    """Test _ensure_index_ready when index doesn't exist."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to raise exception (index doesn't exist)
        mock_redis.execute_command.side_effect = Exception("Index not found")

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocTest)
        # Should handle gracefully when index doesn't exist


def test_redis_ensure_index_ready_waits_for_indexing():
    """Test _ensure_index_ready waits when indexing=1 and returns when done."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO: first call returns indexing=1, second returns indexing=0
        call_count = [0]

        def mock_execute_command(*args):
            if args[0] == "FT.INFO":
                call_count[0] += 1
                if call_count[0] <= 2:
                    return ["index_name", "test_index", "indexing", 1]
                return ["index_name", "test_index", "indexing", 0]
            return None

        mock_redis.execute_command.side_effect = mock_execute_command

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        with patch("time.sleep"):  # Mock sleep to speed up test
            backend._ensure_index_ready(RedisDocTest)

        # Should have polled FT.INFO multiple times
        assert call_count[0] == 3


def test_redis_ensure_index_ready_main_module_key_patterns():
    """Test _ensure_index_ready key_patterns for model with __module__ == '__main__'."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.execute_command.side_effect = Exception("Index not found")
        mock_redis.keys.return_value = []

        backend = RedisMindtraceODM(RedisDocMainModuleTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        RedisDocMainModuleTest.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocMainModuleTest)


def test_redis_ensure_index_ready_model_key_prefix():
    """Test _ensure_index_ready key_patterns for model with model_key_prefix."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as _:
        mock_redis = MagicMock()
        mock_redis.execute_command.side_effect = Exception("Index not found")
        mock_redis.keys.return_value = []

        backend = RedisMindtraceODM(RedisDocWithModelKeyPrefixTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        RedisDocWithModelKeyPrefixTest.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocWithModelKeyPrefixTest)


def test_redis_do_initialize_non_connection_error():
    """Test _do_initialize raises when Migrator fails (fail-fast init)."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_cls:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = RuntimeError("Schema error")
            mock_migrator_cls.return_value = mock_migrator

            backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
            backend.logger = MagicMock()
            backend._is_initialized = False
            RedisDocTest.Meta.database = mock_redis

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()
            assert backend._is_initialized is False



def test_redis_ensure_index_ready_no_index_name_empty_module():
    """Test _ensure_index_ready with no Meta.index_name and __module__ == ''."""

    class ModelEmptyModule(MindtraceRedisDocument):
        name: str = Field(index=True)

        class Meta:
            global_key_prefix = "testapp"
            collection_name = "test_docs"

    ModelEmptyModule.__module__ = ""
    # Ensure no index_name so the else branch (470-477) is taken
    if hasattr(ModelEmptyModule.Meta, "index_name"):
        delattr(ModelEmptyModule.Meta, "index_name")
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.execute_command.side_effect = Exception("Index not found")
        mock_redis.keys.return_value = []

        backend = RedisMindtraceODM(ModelEmptyModule, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        ModelEmptyModule.Meta.database = mock_redis

        backend._ensure_index_ready(ModelEmptyModule)


def test_redis_ensure_index_ready_no_index_name_main_module():
    """Test _ensure_index_ready with no index_name and __module__ == '__main__'."""
    if hasattr(RedisDocMainModuleTest.Meta, "index_name"):
        saved = getattr(RedisDocMainModuleTest.Meta, "index_name", None)
        delattr(RedisDocMainModuleTest.Meta, "index_name")
    else:
        saved = None
    try:
        with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as _:
            mock_redis = MagicMock()
            mock_redis.execute_command.side_effect = Exception("Index not found")
            mock_redis.keys.return_value = []
            backend = RedisMindtraceODM(RedisDocMainModuleTest, "redis://localhost:6379")
            backend.logger = MagicMock()
            backend._is_initialized = True
            RedisDocMainModuleTest.Meta.database = mock_redis
            backend._ensure_index_ready(RedisDocMainModuleTest)
    finally:
        if saved is not None:
            setattr(RedisDocMainModuleTest.Meta, "index_name", saved)


def test_redis_ensure_index_ready_no_index_name_regular_module():
    """Test _ensure_index_ready with no index_name and __module__ set."""
    orig_module = getattr(RedisDocTest, "__module__", None)
    if hasattr(RedisDocTest.Meta, "index_name"):
        saved_index = getattr(RedisDocTest.Meta, "index_name", None)
        delattr(RedisDocTest.Meta, "index_name")
    else:
        saved_index = None
    try:
        RedisDocTest.__module__ = "some.module"
        with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as _:
            mock_redis = MagicMock()
            mock_redis.execute_command.side_effect = Exception("Index not found")
            mock_redis.keys.return_value = []
            backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
            backend.logger = MagicMock()
            backend._is_initialized = True
            RedisDocTest.Meta.database = mock_redis
            backend._ensure_index_ready(RedisDocTest)
    finally:
        if orig_module is not None:
            RedisDocTest.__module__ = orig_module
        if saved_index is not None:
            setattr(RedisDocTest.Meta, "index_name", saved_index)


def test_redis_ensure_index_ready_noop_when_already_ready():
    """Test _ensure_index_ready returns immediately when index is not indexing."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # FT.INFO returns indexing=0 → index is ready
        mock_redis.execute_command.return_value = ["index_name", "test_index", "indexing", 0]

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocTest)

        # Should have called FT.INFO exactly once (no polling needed)
        assert mock_redis.execute_command.call_count == 1


def test_redis_find_zero_results_but_ft_search_has_documents():
    """Test find() when it returns 0 results but FT.SEARCH shows documents exist."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock find() to return empty list
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        # Mock FT.SEARCH to show documents exist
        def mock_execute_command(*args):
            if args[0] == "FT.SEARCH":
                return [1, "test_key", ["name", "test"]]  # 1 document found
            return None

        mock_redis.execute_command.side_effect = mock_execute_command

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database and index_name
        RedisDocTest.Meta.database = mock_redis
        RedisDocTest.Meta.index_name = "test_index"

        # Mock Migrator
        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            # After retry, find() should return results
            mock_query_retry = MagicMock()
            mock_query_retry.all.return_value = [MagicMock()]
            RedisDocTest.find.return_value = mock_query_retry

            results = backend.find()
            # Should retry after detecting documents exist
            assert len(results) > 0


def test_redis_find_no_such_index_error():
    """Test find() returns [] on missing index and does not re-init in query path."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("No such index")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.initialize = MagicMock()

        RedisDocTest.Meta.database = mock_redis

        results = backend.find()
        assert results == []
        backend.initialize.assert_not_called()

def test_redis_find_no_such_index_error_retry_fails():
    """Test find() when 'No such index' error and re-init retry also fails."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock find() to always raise "No such index" error
        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("No such index")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock initialize to be a no-op (re-init doesn't fix the problem)
        backend.initialize = MagicMock()

        results = backend.find()
        # Should return empty list after retry fails
        assert results == []


def test_redis_find_other_error_fallback():
    """Test find() when query fails for other reasons, tries fallback."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock find() to raise non-index error
        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("Connection error")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Fallback find() also fails
        mock_query_fallback = MagicMock()
        mock_query_fallback.all.side_effect = Exception("Fallback also fails")
        RedisDocTest.find.return_value = mock_query_fallback

        results = backend.find()
        # Should return empty list after fallback fails
        assert results == []


def test_redis_find_other_error_returns_empty():
    """Test find() returns empty list on non-index errors (no fallback to full scan)."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock find() to raise non-index error
        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("Connection error")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        results = backend.find()
        # Non-index errors return empty — no fallback to unfiltered scan
        assert results == []


def test_redis_find_with_dict_query():
    """Test find() with dict query uses _dict_to_find_expressions and returns results."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        mock_query = MagicMock()
        mock_query.all.return_value = [MagicMock(name="doc1")]
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        RedisDocTest.Meta.database = mock_redis

        results = backend.find({"name": "Charlie"})
        assert len(results) == 1
        RedisDocTest.find.assert_called_once()
        call_args = RedisDocTest.find.call_args[0]
        assert len(call_args) == 1
        assert getattr(call_args[0], "op", None) is not None or call_args[0] == "Charlie"


def test_redis_dict_to_find_expressions():
    """Test _dict_to_find_expressions converts dict to expressions and rejects unknown fields."""
    from mindtrace.database.core.exceptions import QueryNotSupported

    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend._is_initialized = True

        exprs = backend._dict_to_find_expressions({"name": "Alice"})
        assert len(exprs) == 1
        exprs_empty = backend._dict_to_find_expressions({})
        assert exprs_empty == []
        with pytest.raises(QueryNotSupported):
            backend._dict_to_find_expressions({"name": "Alice", "nonexistent": 1})
        with pytest.raises(QueryNotSupported):
            backend._dict_to_find_expressions({"$and": [{"name": "Alice"}]})


# ── Query-shape tests for _dict_to_find_expressions ────────────────────────
# Verify expression tree structure for every shape the ODM must support:
# flat equality, multi-field AND, list-as-IN, $or, combined $or+equality.


def _make_backend():
    """Create a backend wired to RedisDocTest without hitting Redis."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock:
        mock.return_value = MagicMock()
        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend._is_initialized = True
        return backend


def test_dict_expr_flat_equality():
    """Single field equality → one EQ expression."""
    from redis_om.model.model import Operators

    b = _make_backend()
    exprs = b._dict_to_find_expressions({"name": "Alice"})
    assert len(exprs) == 1
    assert exprs[0].op == Operators.EQ
    assert exprs[0].right == "Alice"


def test_dict_expr_multi_field_and():
    """Multiple fields → separate EQ expressions (implicit AND)."""
    from redis_om.model.model import Operators

    b = _make_backend()
    exprs = b._dict_to_find_expressions({"name": "Alice", "age": 30})
    assert len(exprs) == 2
    ops = {e.op for e in exprs}
    assert ops == {Operators.EQ}


def test_dict_expr_list_in():
    """List value → IN expression via << operator."""
    from redis_om.model.model import Operators

    b = _make_backend()
    exprs = b._dict_to_find_expressions({"name": ["Alice", "Bob"]})
    assert len(exprs) == 1
    assert exprs[0].op == Operators.IN
    assert exprs[0].right == ["Alice", "Bob"]


def test_dict_expr_or():
    """$or with two clauses → OR expression tree."""
    from redis_om.model.model import Operators

    b = _make_backend()
    exprs = b._dict_to_find_expressions({
        "$or": [{"name": "Alice"}, {"name": "Bob"}]
    })
    assert len(exprs) == 1
    assert exprs[0].op == Operators.OR
    assert exprs[0].left.op == Operators.EQ
    assert exprs[0].right.op == Operators.EQ


def test_dict_expr_or_with_multi_field_clauses():
    """$or where each clause has two fields → OR of ANDs."""
    from redis_om.model.model import Operators

    b = _make_backend()
    exprs = b._dict_to_find_expressions({
        "$or": [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
    })
    assert len(exprs) == 1
    assert exprs[0].op == Operators.OR
    # Each branch is an AND of two EQ expressions
    assert exprs[0].left.op == Operators.AND
    assert exprs[0].right.op == Operators.AND


def test_dict_expr_equality_plus_or():
    """Flat equality combined with $or → two expressions (AND at query level)."""
    from redis_om.model.model import Operators

    b = _make_backend()
    exprs = b._dict_to_find_expressions({
        "email": "x@example.com",
        "$or": [{"name": "Alice"}, {"name": "Bob"}],
    })
    assert len(exprs) == 2
    ops = {e.op for e in exprs}
    assert Operators.EQ in ops
    assert Operators.OR in ops


def test_dict_expr_or_three_clauses():
    """$or with three clauses → nested OR tree."""
    from redis_om.model.model import Operators

    b = _make_backend()
    exprs = b._dict_to_find_expressions({
        "$or": [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    })
    assert len(exprs) == 1
    # (A | B) | C  →  top-level OR, left is OR, right is EQ
    top = exprs[0]
    assert top.op == Operators.OR
    assert top.left.op == Operators.OR
    assert top.right.op == Operators.EQ


def test_dict_expr_rejects_dict_style_in():
    """{"field": {"$in": [...]}} style is rejected."""
    from mindtrace.database.core.exceptions import QueryNotSupported

    b = _make_backend()
    with pytest.raises(QueryNotSupported, match="Dict-style operators"):
        b._dict_to_find_expressions({"name": {"$in": ["Alice", "Bob"]}})


def test_dict_expr_rejects_unsupported_dollar_op():
    """$nor, $and etc. are rejected."""
    from mindtrace.database.core.exceptions import QueryNotSupported

    b = _make_backend()
    with pytest.raises(QueryNotSupported, match="Unsupported query operator"):
        b._dict_to_find_expressions({"$nor": [{"name": "Alice"}]})
    with pytest.raises(QueryNotSupported, match="Unsupported query operator"):
        b._dict_to_find_expressions({"$and": [{"name": "Alice"}]})


# ── End-to-end ODM method tests with mocked redis-om find() ────────────────
# These verify that find/delete_many/update_one/distinct actually call
# model_cls.find() with the right expressions, not just that
# _dict_to_find_expressions builds them.


def test_find_passes_or_expressions_to_model():
    """find(where={...$or...}) passes combined expressions to model_cls.find()."""
    b = _make_backend()
    b.redis = MagicMock()

    mock_query = MagicMock()
    mock_query.all.return_value = []
    with patch.object(RedisDocTest, "find", return_value=mock_query) as mock_find:
        b.find(where={"email": "x@y.com", "$or": [{"name": "A"}, {"name": "B"}]})
        # model_cls.find() should have been called with 2 expression args
        assert mock_find.called
        args = mock_find.call_args[0]
        assert len(args) == 2  # one EQ for email, one OR tree


def test_find_passes_list_in_to_model():
    """find(where={"field": [v1, v2]}) passes IN expression."""
    from redis_om.model.model import Operators

    b = _make_backend()
    b.redis = MagicMock()

    mock_query = MagicMock()
    mock_query.all.return_value = []
    with patch.object(RedisDocTest, "find", return_value=mock_query) as mock_find:
        b.find(where={"name": ["Alice", "Bob"]})
        args = mock_find.call_args[0]
        assert len(args) == 1
        assert args[0].op == Operators.IN


def test_delete_many_calls_find_query_delete():
    """delete_many delegates to model_cls.find(*exprs).delete()."""
    b = _make_backend()
    b.redis = MagicMock()

    mock_query = MagicMock()
    mock_query.delete.return_value = 3
    with patch.object(RedisDocTest, "find", return_value=mock_query) as mock_find:
        count = b.delete_many({"name": "Alice"})
        assert mock_find.called
        mock_query.delete.assert_called_once()
        assert count == 3


def test_delete_many_with_or():
    """delete_many with $or passes correct expressions."""
    b = _make_backend()
    b.redis = MagicMock()

    mock_query = MagicMock()
    mock_query.delete.return_value = 2
    with patch.object(RedisDocTest, "find", return_value=mock_query) as mock_find:
        count = b.delete_many({"$or": [{"name": "A"}, {"name": "B"}]})
        args = mock_find.call_args[0]
        assert len(args) == 1  # single OR expression
        assert count == 2


def test_delete_many_with_empty_filter_deletes_all():
    """delete_many({}) should delete all docs (Mongo parity)."""
    b = _make_backend()
    b.redis = MagicMock()

    mock_query = MagicMock()
    mock_query.delete.return_value = 4
    with patch.object(RedisDocTest, "find", return_value=mock_query):
        count = b.delete_many({})
        assert count == 4
        mock_query.delete.assert_called_once()


def test_delete_one_with_empty_filter_deletes_first():
    """delete_one({}) should remove one document (Mongo parity)."""
    b = _make_backend()
    b.redis = MagicMock()

    doc = MagicMock()
    doc.pk = "doc-1"
    mock_query = MagicMock()
    mock_query.all.return_value = [doc]

    with (
        patch.object(RedisDocTest, "find", return_value=mock_query),
        patch.object(RedisDocTest, "delete") as mock_delete,
    ):
        count = b.delete_one({})
        assert count == 1
        mock_delete.assert_called_once_with("doc-1")


def test_update_one_upsert_inserts_when_no_match():
    """update_one with upsert=True inserts when find returns empty."""
    b = _make_backend()
    b.redis = MagicMock()

    mock_query = MagicMock()
    mock_query.all.return_value = []
    with patch.object(RedisDocTest, "find", return_value=mock_query):
        mock_doc = MagicMock()
        mock_doc.pk = "new-pk"
        mock_doc.model_dump.return_value = {"name": "Alice", "age": 30}
        with patch.object(b, "insert_one", return_value=mock_doc):
            result = b.update_one(
                where={"name": "Alice"},
                set_fields={"age": 30},
                upsert=True,
                return_document="after",
            )
            assert result == {"name": "Alice", "age": 30}


def test_update_one_modifies_existing():
    """update_one finds a doc and saves updates."""
    b = _make_backend()
    b.redis = MagicMock()

    mock_doc = MagicMock()
    mock_doc.model_dump.return_value = {"name": "Alice", "age": 25}
    mock_query = MagicMock()
    mock_query.all.return_value = [mock_doc]
    with patch.object(RedisDocTest, "find", return_value=mock_query):
        result = b.update_one(
            where={"name": "Alice"},
            set_fields={"age": 31},
            return_document="before",
        )
        # return_document="before" returns the old dump
        assert result == {"name": "Alice", "age": 25}
        mock_doc.save.assert_called_once()


def test_distinct_with_filter():
    """distinct uses find() for the fallback when FT.AGGREGATE fails."""
    b = _make_backend()
    b.redis = MagicMock()

    # Make FT.AGGREGATE fail so it falls back to find()
    b.redis.execute_command.side_effect = Exception("no index")

    mock_doc1 = MagicMock()
    mock_doc1.name = "Alice"
    mock_doc2 = MagicMock()
    mock_doc2.name = "Bob"
    mock_doc3 = MagicMock()
    mock_doc3.name = "Alice"

    mock_query = MagicMock()
    mock_query.all.return_value = [mock_doc1, mock_doc2, mock_doc3]
    with patch.object(RedisDocTest, "find", return_value=mock_query):
        RedisDocTest.Meta.index_name = "test:index"
        values = b.distinct("name", {"email": "x@y.com"})
        assert values == ["Alice", "Bob"]


def test_distinct_with_or_uses_or_filter_for_ft_aggregate():
    """distinct(where={$or: ...}) should not silently drop $or in FT filter."""
    b = _make_backend()
    b.redis = MagicMock()
    RedisDocTest.Meta.index_name = "test:index"

    b.redis.execute_command.return_value = [
        2,
        ["name", "Alice"],
        ["name", "Bob"],
    ]

    values = b.distinct("name", {"$or": [{"name": "Alice"}, {"name": "Bob"}]})

    assert values == ["Alice", "Bob"]
    call = b.redis.execute_command.call_args[0]
    assert call[0] == "FT.AGGREGATE"
    # Query filter argument should include OR, not fallback to '*'
    assert "|" in call[2]
    assert call[2] != "*"


def test_redis_getattr_preinit_does_not_recurse():
    """__getattr__ should fail cleanly even before __init__ populated attrs."""
    backend = RedisMindtraceODM.__new__(RedisMindtraceODM)
    with pytest.raises(AttributeError):
        backend.__getattr__("user")


def test_redis_find_with_args_zero_results_but_ft_search_has_documents():
    """Test find() with args when it returns 0 results but FT.SEARCH shows documents exist."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock find() to return empty list
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        # Mock FT.SEARCH to show documents exist
        def mock_execute_command(*args):
            if args[0] == "FT.SEARCH":
                return [1, "test_key", ["name", "test"]]  # 1 document found
            return None

        mock_redis.execute_command.side_effect = mock_execute_command

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database and index_name
        RedisDocTest.Meta.database = mock_redis
        RedisDocTest.Meta.index_name = "test_index"

        # Mock Migrator
        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            # After retry, find() should return results
            mock_query_retry = MagicMock()
            mock_query_retry.all.return_value = [MagicMock()]
            RedisDocTest.find.return_value = mock_query_retry

            results = backend.find(RedisDocTest.name == "test")
            # Should retry after detecting documents exist
            assert len(results) > 0


def test_redis_find_no_such_index_error_with_args():
    """Test find(args) returns [] on missing index and does not re-init in query path."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("No such index")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.initialize = MagicMock()

        RedisDocTest.Meta.database = mock_redis

        results = backend.find(RedisDocTest.name == "test")
        assert results == []
        backend.initialize.assert_not_called()

def test_redis_init_empty_redis_url():
    """Test __init__ with empty redis_url raises ValueError."""
    with pytest.raises(ValueError, match="redis_url is required"):
        RedisMindtraceODM(RedisDocTest, "")


def test_redis_ensure_index_ft_info_exception():
    """Test _ensure_index_ready when FT.INFO raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to raise exception
        mock_redis.execute_command.side_effect = Exception("FT.INFO failed")

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocTest)
        # Should handle exception gracefully


def test_redis_ensure_index_ready_timeout_warning():
    """Test _ensure_index_ready logs warning when index still indexing after timeout."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # FT.INFO always returns indexing=1 (never finishes)
        mock_redis.execute_command.return_value = ["index_name", "test_index", "indexing", 1]

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        with patch("time.sleep"):
            backend._ensure_index_ready(RedisDocTest, timeout=0.3)

        # Should have logged a warning
        backend.logger.warning.assert_called_once()
        call_msg = str(backend.logger.warning.call_args[0][0])
        assert "still indexing" in call_msg


def test_redis_do_initialize_connections_exception():
    """Test _do_initialize when connections.URL setting raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Mock the import inside the try block to raise exception
        with patch("redis_om.connections", side_effect=Exception("Cannot import connections")):
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                # Set Meta.database
                RedisDocTest.Meta.database = mock_redis

                backend._do_initialize()
                # Should handle exception gracefully


def test_redis_do_initialize_model_registry_port_check():
    """Test _do_initialize no longer mutates redis-om global model_registry databases."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6381")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        registry_db = MagicMock()
        mock_registry_model = MagicMock()
        mock_registry_model.Meta.database = registry_db

        with patch("redis_om.model.model.model_registry", {"TestModel": mock_registry_model}):
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator
                backend._do_initialize()

        assert mock_registry_model.Meta.database is registry_db

def test_redis_do_initialize_model_registry_exception():
    """Test _do_initialize when model_registry access raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock model_registry import to raise exception
        with patch("redis_om.model.model.model_registry", side_effect=Exception("Registry error")):
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should handle exception gracefully


def test_redis_do_initialize_migrator_connection_error():
    """Test _do_initialize raises RuntimeError when Migrator fails."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = Exception("Connection refused 111")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()
            assert backend._is_initialized is False

def test_redis_ensure_index_ready_no_module():
    """Test _ensure_index_ready when model has no __module__."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to raise exception (index doesn't exist)
        mock_redis.execute_command.side_effect = Exception("Index not found")

        # Create a model without __module__
        class RedisDocNoModuleTest(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

        # Remove __module__ attribute
        if hasattr(RedisDocNoModuleTest, "__module__"):
            delattr(RedisDocNoModuleTest, "__module__")

        backend = RedisMindtraceODM(RedisDocNoModuleTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocNoModuleTest.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocNoModuleTest)
        # Should handle no module gracefully


def test_redis_ensure_index_ready_main_module():
    """Test _ensure_index_ready with __main__ module."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to raise exception (index doesn't exist)
        mock_redis.execute_command.side_effect = Exception("Index not found")

        backend = RedisMindtraceODM(RedisDocMainModuleTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocMainModuleTest.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocMainModuleTest)
        # Should handle __main__ module


def test_redis_ensure_index_ready_regular_module():
    """Test _ensure_index_ready with regular module."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to raise exception (index doesn't exist)
        mock_redis.execute_command.side_effect = Exception("Index not found")

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database and ensure module is set
        RedisDocTest.Meta.database = mock_redis
        RedisDocTest.__module__ = "test_module"

        backend._ensure_index_ready(RedisDocTest)
        # Should handle regular module


def test_redis_do_initialize_connection_error():
    """Test _do_initialize when ping() raises ConnectionError."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.side_effect = Exception("Connection refused")

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        with pytest.raises(ConnectionError):
            backend._do_initialize()
        # Should raise ConnectionError


def test_redis_all_no_such_index_retry_succeeds():
    """Test all() does not re-init on missing index query errors."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis

        RedisDocTest.Meta.database = mock_redis

        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("No such index")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend.initialize = MagicMock()

        result = backend.all()
        assert result == []
        backend.initialize.assert_not_called()

def test_redis_all_other_exception_returns_empty():
    """Test all() delegates to find(), which returns [] on non-index errors."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock find() to raise non-index error
        mock_query = MagicMock()
        mock_query.all.side_effect = ValueError("Other error")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        result = backend.all()
        assert result == []


def test_redis_insert_no_ensure_index_side_effect():
    """Test insert() does not call _ensure_index_ready (moved to init)."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock save()
        mock_doc = MagicMock()
        mock_doc.pk = "test_pk"
        RedisDocTest.__call__ = MagicMock(return_value=mock_doc)

        # Spy on _ensure_index_ready to verify it's NOT called
        backend._ensure_index_ready = MagicMock()

        result = backend.insert({"name": "test", "age": 30, "email": "test@test.com"})
        assert result is not None
        backend._ensure_index_ready.assert_not_called()


def test_redis_insert_migrator_env_var_deletion():
    """Test insert() when Migrator runs and REDIS_OM_URL needs to be deleted."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock save()
        mock_doc = MagicMock()
        mock_doc.pk = "test_pk"
        RedisDocTest.__call__ = MagicMock(return_value=mock_doc)

        # Mock Migrator
        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            import os

            original_env = os.environ.get("REDIS_OM_URL", None)
            if "REDIS_OM_URL" in os.environ:
                del os.environ["REDIS_OM_URL"]

            try:
                result = backend.insert({"name": "test", "age": 30, "email": "test@test.com"})
                # Should delete REDIS_OM_URL if it was set
                assert result is not None
            finally:
                if original_env is not None:
                    os.environ["REDIS_OM_URL"] = original_env


def test_redis_get_raw_model_multi_model_error():
    """Test get_raw_model() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")

        with pytest.raises(ValueError, match="Cannot use get_raw_model"):
            backend.get_raw_model()
        # Should raise ValueError


def test_redis_get_multi_model_error():
    """Test get() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")

        with pytest.raises(ValueError, match="Cannot use get\\(\\) in multi-model mode"):
            backend.get("test_id")
        # Should raise ValueError


def test_redis_update_multi_model_error():
    """Test update() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")

        mock_obj = MagicMock()
        with pytest.raises(ValueError, match="Cannot use update\\(\\) in multi-model mode"):
            backend.update(mock_obj)
        # Should raise ValueError


def test_redis_delete_multi_model_error():
    """Test delete() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")

        with pytest.raises(ValueError, match="Cannot use delete\\(\\) in multi-model mode"):
            backend.delete("test_id")
        # Should raise ValueError


def test_redis_all_multi_model_error():
    """Test all() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")

        with pytest.raises(ValueError, match="Cannot use all\\(\\) in multi-model mode"):
            backend.all()
        # Should raise ValueError


def test_redis_find_multi_model_error():
    """Test find() raises ValueError in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")

        with pytest.raises(ValueError, match="Cannot use find\\(\\) in multi-model mode"):
            backend.find()
        # Should raise ValueError


def test_redis_ensure_index_no_module():
    """Test _ensure_index_ready with no module."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Create model without __module__
        class RedisDocNoModule(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

        # Set __module__ to empty string
        RedisDocNoModule.__module__ = ""

        # Mock FT.INFO to raise exception (index doesn't exist)
        mock_redis.execute_command.side_effect = Exception("Index not found")

        backend = RedisMindtraceODM(RedisDocNoModule, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocNoModule.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocNoModule)
        # Should handle no module


def test_redis_ensure_index_main_module():
    """Test _ensure_index_ready with __main__ module."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to raise exception (index doesn't exist)
        mock_redis.execute_command.side_effect = Exception("Index not found")

        backend = RedisMindtraceODM(RedisDocMainModuleTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocMainModuleTest.Meta.database = mock_redis

        backend._ensure_index_ready(RedisDocMainModuleTest)
        # Should handle __main__ module


def test_redis_ensure_index_regular_module():
    """Test _ensure_index_ready with regular module."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to raise exception (index doesn't exist)
        mock_redis.execute_command.side_effect = Exception("Index not found")

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database and ensure module is set
        RedisDocTest.Meta.database = mock_redis
        RedisDocTest.__module__ = "test_module"

        backend._ensure_index_ready(RedisDocTest)
        # Should handle regular module


def test_redis_ensure_index_outer_exception():
    """Test _ensure_index_ready when outer try raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock execute_command to raise exception on FT.INFO
        mock_redis.execute_command.side_effect = Exception("FT.INFO failed")

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock model to raise exception when accessing __module__
        def get_module():
            raise Exception("Module access failed")

        with patch.object(RedisDocTest, "__module__", property(get_module)):
            backend._ensure_index_ready(RedisDocTest)
        # Should handle outer exception gracefully


def test_redis_do_initialize_connections_exception_first():
    """Test _do_initialize when connections.URL setting raises exception first time."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock connections to raise exception on first access
        with patch("redis_om.connections") as mock_connections:
            mock_connections.URL = "original"
            # First access raises exception
            call_count = [0]
            original_connections = None
            try:
                from redis_om import connections as orig_conn

                original_connections = orig_conn
            except ImportError:
                pass

            def mock_set_url(value):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise Exception("Cannot set URL first time")
                if original_connections:
                    original_connections.URL = value

            from unittest.mock import PropertyMock

            url_property = PropertyMock(side_effect=mock_set_url)
            type(mock_connections).URL = url_property

            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should handle exception gracefully


def test_redis_do_initialize_model_registry_loop():
    """Test _do_initialize no longer iterates and rewrites redis-om global model_registry."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6381")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        original_db_1 = MagicMock()
        original_db_2 = MagicMock()
        mock_registry_model1 = MagicMock()
        mock_registry_model1.Meta.database = original_db_1
        mock_registry_model2 = MagicMock()
        mock_registry_model2.Meta.database = original_db_2

        with patch(
            "redis_om.model.model.model_registry",
            {"TestModel1": mock_registry_model1, "TestModel2": mock_registry_model2},
        ):
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator
                backend._do_initialize()

        assert mock_registry_model1.Meta.database is original_db_1
        assert mock_registry_model2.Meta.database is original_db_2

def test_redis_do_initialize_env_var_deletion_condition():
    """Test _do_initialize when REDIS_OM_URL needs to be deleted."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        import os

        original_env = os.environ.get("REDIS_OM_URL", None)
        # Ensure REDIS_OM_URL is not set
        if "REDIS_OM_URL" in os.environ:
            del os.environ["REDIS_OM_URL"]

        try:
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should delete REDIS_OM_URL if it was set
        finally:
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env


def test_redis_do_initialize_mark_odms_initialized():
    """Test _do_initialize marks all model ODMs as initialized."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        # Create multi-model backend
        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            backend._do_initialize()
            # Should mark all model ODMs as initialized
            assert backend.user._is_initialized is True


def test_redis_do_initialize_connection_error_handling():
    """Test _do_initialize raises on Migrator errors with connection-like exception names."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        class ConnectionErrorType(Exception):
            pass

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = ConnectionErrorType("Error")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()

def test_redis_find_no_such_index_with_args():
    """Test find(args) returns [] on missing index errors."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("No such index")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        RedisDocTest.Meta.database = mock_redis

        results = backend.find(RedisDocTest.name == "test")
        assert results == []

def test_redis_do_initialize_model_odms_loop():
    """Test _do_initialize when model ODMs need to be added to models_to_migrate."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        # Create multi-model backend
        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Ensure the child ODM has a model_cls
        backend.user.model_cls = RedisDocTest

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            backend._do_initialize()
            # Should add model from child ODM to models_to_migrate


def test_redis_do_initialize_env_var_deletion_with_redis_url():
    """Test _do_initialize when REDIS_OM_URL needs to be deleted and redis_url is set."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        import os

        original_env = os.environ.get("REDIS_OM_URL", None)
        # Set REDIS_OM_URL to something, then it should be deleted
        os.environ["REDIS_OM_URL"] = "redis://localhost:6379"

        try:
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should delete REDIS_OM_URL if it was set and redis_url is set
                # Note: The logic checks if original_redis_url is None, and if REDIS_OM_URL is in env and redis_url is set
                # Since we set it before, original_env will be the value we set, so it won't be deleted
                # Let's test the case where it wasn't set before
        finally:
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env
            elif "REDIS_OM_URL" in os.environ:
                del os.environ["REDIS_OM_URL"]


def test_redis_do_initialize_env_var_deletion_no_original():
    """Test _do_initialize when REDIS_OM_URL needs to be deleted (no original value)."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        import os

        original_env = os.environ.get("REDIS_OM_URL", None)
        # Ensure REDIS_OM_URL is not set initially
        if "REDIS_OM_URL" in os.environ:
            del os.environ["REDIS_OM_URL"]

        try:
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                # Mock os.environ to track deletions
                env_deletions = []
                original_del = os.environ.__delitem__

                def mock_del(key):
                    if key == "REDIS_OM_URL":
                        env_deletions.append(key)
                    return original_del(key)

                with patch.object(os.environ, "__delitem__", mock_del):
                    backend._do_initialize()
                    # Should delete REDIS_OM_URL if it was set during initialization
        finally:
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env


def test_redis_do_initialize_connection_error_in_exception():
    """Test _do_initialize raises RuntimeError when Migrator raises connection-related errors."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = Exception("Connection error occurred")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()

def test_redis_ensure_index_outer_exception_handler():
    """Test _ensure_index_ready when outer exception handler is triggered."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock getattr to raise exception when accessing __module__
        def mock_getattr(obj, name, default=None):
            if obj == RedisDocTest and name == "__module__":
                raise Exception("Module access failed")
            return getattr(obj, name, default)

        with patch("builtins.getattr", side_effect=mock_getattr):
            backend._ensure_index_ready(RedisDocTest)
        # Should handle outer exception gracefully


def test_redis_do_initialize_model_registry_has_models():
    """Test _do_initialize when model_registry has models to process."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock model_registry to have a model that raises exception when accessing Meta
        mock_registry_model = MagicMock()

        # Make accessing Meta.database raise exception
        def get_meta():
            raise Exception("Meta access failed")

        mock_registry_model.__getattribute__ = lambda self, name: (
            get_meta() if name == "Meta" else object.__getattribute__(self, name)
        )

        with patch("redis_om.model.model.model_registry", {"TestModel": mock_registry_model}):
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should handle exception gracefully


def test_redis_do_initialize_env_var_deletion_elif_path():
    """Test _do_initialize when REDIS_OM_URL deletion path is taken."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        import os

        original_env = os.environ.get("REDIS_OM_URL", None)
        # Ensure REDIS_OM_URL is not set initially (so original_redis_url will be None)
        if "REDIS_OM_URL" in os.environ:
            del os.environ["REDIS_OM_URL"]

        # Track if deletion happens
        deletion_happened = [False]
        original_del = os.environ.__delitem__

        def mock_del(key):
            if key == "REDIS_OM_URL":
                deletion_happened[0] = True
            return original_del(key)

        try:
            with patch.object(os.environ, "__delitem__", mock_del):
                with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                    mock_migrator = MagicMock()
                    mock_migrator_class.return_value = mock_migrator

                    backend._do_initialize()
                    # Should delete REDIS_OM_URL if it was set during init
        finally:
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env


def test_redis_ensure_index_outer_exception_getattr():
    """Test _ensure_index_ready when getattr raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock getattr to raise exception when accessing __module__
        def mock_getattr(obj, name, default=None):
            if obj == RedisDocTest and name == "__module__":
                raise Exception("Module access failed")
            return getattr(obj, name, default)

        with patch("builtins.getattr", side_effect=mock_getattr):
            backend._ensure_index_ready(RedisDocTest)
        # Should handle outer exception gracefully


def test_redis_do_initialize_model_registry_exception_during_iteration():
    """Test _do_initialize when model_registry iteration raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Create a mock registry that raises exception when iterating
        class ExceptionDict(dict):
            def items(self):
                raise Exception("Registry iteration failed")

        mock_registry = ExceptionDict()
        mock_registry["TestModel"] = MagicMock()

        with patch("redis_om.model.model.model_registry", mock_registry):
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should handle exception gracefully


def test_redis_do_initialize_env_var_deletion_elif_branch():
    """Test _do_initialize when REDIS_OM_URL deletion elif branch is taken."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        import os

        original_env = os.environ.get("REDIS_OM_URL", None)
        # Ensure REDIS_OM_URL is not set initially (so original_redis_url will be None)
        if "REDIS_OM_URL" in os.environ:
            del os.environ["REDIS_OM_URL"]

        # Track deletions
        deletions = []
        original_del = os.environ.__delitem__

        def mock_del(key):
            deletions.append(key)
            return original_del(key)

        try:
            with patch.object(os.environ, "__delitem__", mock_del):
                with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                    mock_migrator = MagicMock()
                    mock_migrator_class.return_value = mock_migrator

                    backend._do_initialize()
                    # Should delete REDIS_OM_URL in elif branch
                    # The elif checks: original_redis_url is None AND REDIS_OM_URL in os.environ AND self.redis_url
        finally:
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env


def test_redis_do_initialize_connection_refused_string():
    """Test _do_initialize raises RuntimeError when Migrator raises connection-refused errors."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = Exception("Connection refused")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()

def test_redis_do_initialize_model_database_mismatch():
    """Test _do_initialize when model.Meta.database is not self.redis."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set a different database
        other_redis = MagicMock()
        RedisDocTest.Meta.database = other_redis

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            backend._do_initialize()
            # Should update database to self.redis


def test_redis_do_initialize_connections_url_exception():
    """Test _do_initialize when connections.URL setting raises exception (second try)."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock connections module to raise exception when URL is set (second time)
        call_count = [0]
        original_connections = None
        try:
            from redis_om import connections as orig_conn

            original_connections = orig_conn
        except ImportError:
            pass

        def mock_set_url(value):
            call_count[0] += 1
            if call_count[0] > 1:  # Second call raises exception
                raise Exception("Cannot set URL")
            if original_connections:
                original_connections.URL = value

        # Patch redis_om.connections where it's imported
        with patch("redis_om.connections") as mock_connections:
            # Use PropertyMock to intercept URL assignment
            from unittest.mock import PropertyMock

            url_property = PropertyMock(side_effect=mock_set_url)
            type(mock_connections).URL = url_property

            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should handle exception gracefully


def test_redis_do_initialize_model_registry_no_database():
    """Test _do_initialize when model_registry model has no database."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock model_registry to have a model with None database
        mock_registry_model = MagicMock()
        mock_registry_model.Meta.database = None

        with patch("redis_om.model.model.model_registry", {"TestModel": mock_registry_model}):
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should update model_registry model's database


def test_redis_do_initialize_env_var_deletion():
    """Test _do_initialize when REDIS_OM_URL needs to be deleted."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Set REDIS_OM_URL to None (simulating it wasn't set before)
        import os

        original_env = os.environ.get("REDIS_OM_URL", None)
        if "REDIS_OM_URL" in os.environ:
            del os.environ["REDIS_OM_URL"]

        try:
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                # Should delete REDIS_OM_URL if it was set
        finally:
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env


def test_redis_do_initialize_connection_error_not_initialized():
    """Test _do_initialize when ConnectionError is raised, doesn't mark as initialized."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.side_effect = ConnectionError("Connection refused")

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        with pytest.raises(ConnectionError):
            backend._do_initialize()
        # Should not mark as initialized


def test_redis_do_initialize_other_exception_connection_refused():
    """Test _do_initialize raises RuntimeError for non-ping migrator failures."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = Exception("Random exception with Connection refused")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()

def test_redis_initialize_parent_delegation():
    """Test initialize() delegates to parent in multi-model mode."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Create parent ODM with multi-model
        parent = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")
        parent.logger = MagicMock()
        parent._do_initialize = MagicMock()

        # Get child ODM
        child = parent.user

        # Call initialize on child
        child.initialize()

        # Should call parent's _do_initialize
        parent._do_initialize.assert_called_once()


def test_redis_insert_migrator_exception():
    """Test insert() when Migrator.run() raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock find() to return empty (no duplicates)
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        # Mock save()
        mock_doc = MagicMock()
        mock_doc.pk = "test_pk"
        RedisDocTest.return_value = mock_doc
        RedisDocTest.__call__ = MagicMock(return_value=mock_doc)

        # Mock _ensure_index_ready
        backend._ensure_index_ready = MagicMock()

        # Mock Migrator to raise exception
        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = Exception("Migrator failed")
            mock_migrator_class.return_value = mock_migrator

            # Mock os.environ
            import os

            with patch.dict(os.environ, {}, clear=False):
                backend.insert({"name": "test", "age": 30, "email": "test@test.com"})
                # Should handle exception gracefully


def test_redis_all_not_initialized_retry():
    """Test all() when not initialized, retries with _do_initialize."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = False
        backend.redis = mock_redis

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock initialize to not set _is_initialized
        def mock_initialize():
            backend._is_initialized = False

        backend.initialize = mock_initialize
        backend._do_initialize = MagicMock()

        # Mock find() to return empty list
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend.all()
        # Should call _do_initialize


def test_redis_all_no_such_index_retry_fails():
    """Test all() when 'No such index' error and re-init retry also fails."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock find() to always raise "No such index" error
        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("No such index")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        # Mock initialize to be a no-op (re-init doesn't fix the problem)
        backend.initialize = MagicMock()

        result = backend.all()
        # Should return empty list after retry fails
        assert result == []


def test_redis_find_not_initialized_retry():
    """Test find() when not initialized, retries with _do_initialize."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = False
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock initialize to not set _is_initialized
        def mock_initialize():
            backend._is_initialized = False

        backend.initialize = mock_initialize
        backend._do_initialize = MagicMock()

        # Mock find() to return empty list
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend.find()
        # Should call _do_initialize


def test_redis_find_no_index_name():
    """Test find() when index_name is not set."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database but remove index_name
        RedisDocTest.Meta.database = mock_redis
        if hasattr(RedisDocTest.Meta, "index_name"):
            delattr(RedisDocTest.Meta, "index_name")

        # Mock find() to return empty list
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend.find()
        # Should handle no index_name gracefully


def test_redis_find_ft_search_no_results():
    """Test find() when FT.SEARCH returns no results."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database and index_name
        RedisDocTest.Meta.database = mock_redis
        RedisDocTest.Meta.index_name = "test_index"

        # Mock find() to return empty list
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        # Mock FT.SEARCH to return no results (list with only count)
        def mock_execute_command(*args):
            if args[0] == "FT.SEARCH":
                return [0]  # No documents
            return None

        mock_redis.execute_command.side_effect = mock_execute_command

        backend.find()
        # Should return empty list


def test_redis_find_ft_search_exception():
    """Test find() when FT.SEARCH raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database and index_name
        RedisDocTest.Meta.database = mock_redis
        RedisDocTest.Meta.index_name = "test_index"

        # Mock find() to return empty list
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        # Mock FT.SEARCH to raise exception
        def mock_execute_command(*args):
            if args[0] == "FT.SEARCH":
                raise Exception("FT.SEARCH failed")
            return None

        mock_redis.execute_command.side_effect = mock_execute_command

        backend.find()
        # Should handle exception gracefully


def test_redis_find_migrator_retry_exception():
    """Test find() when Migrator retry raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database and index_name
        RedisDocTest.Meta.database = mock_redis
        RedisDocTest.Meta.index_name = "test_index"

        # Mock find() to return empty list
        mock_query = MagicMock()
        mock_query.all.return_value = []
        RedisDocTest.find = MagicMock(return_value=mock_query)

        # Mock FT.SEARCH to show documents exist
        def mock_execute_command(*args):
            if args[0] == "FT.SEARCH":
                return [1, "test_key", ["name", "test"]]
            return None

        mock_redis.execute_command.side_effect = mock_execute_command

        # Mock Migrator to raise exception
        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = Exception("Migrator failed")
            mock_migrator_class.return_value = mock_migrator

            import os

            with patch.dict(os.environ, {}, clear=False):
                backend.find()
                # Should handle exception gracefully


def test_redis_find_migrator_retry_with_args():
    """Test find() with args when Migrator retry succeeds."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.redis_url = "redis://localhost:6379"

        # Set Meta.database and index_name
        RedisDocTest.Meta.database = mock_redis
        RedisDocTest.Meta.index_name = "test_index"

        # Mock find() to return empty list first, then results
        call_count = [0]

        def mock_find(*args):
            mock_query = MagicMock()
            if call_count[0] == 0:
                call_count[0] += 1
                mock_query.all.return_value = []
            else:
                mock_query.all.return_value = [MagicMock()]
            return mock_query

        RedisDocTest.find = MagicMock(side_effect=mock_find)

        # Mock FT.SEARCH to show documents exist
        def mock_execute_command(*args):
            if args[0] == "FT.SEARCH":
                return [1, "test_key", ["name", "test"]]
            return None

        mock_redis.execute_command.side_effect = mock_execute_command

        # Mock Migrator
        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            import os

            with patch.dict(os.environ, {}, clear=False):
                backend.find(RedisDocTest.name == "test")
                # Should retry with args


def test_redis_find_no_such_index_reinit_recovery():
    """Test find() no longer performs re-init recovery on missing index errors."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        mock_query = MagicMock()
        mock_query.all.side_effect = Exception("No such index")
        RedisDocTest.find = MagicMock(return_value=mock_query)

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis
        backend.initialize = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        results = backend.find()
        assert results == []
        backend.initialize.assert_not_called()

def test_redis_find_other_error_fallback_with_args():
    """Test find() with args when query fails, tries fallback."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        backend.redis = mock_redis

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis

        # Mock find() to raise non-index error
        call_count = [0]

        def mock_find(*args):
            mock_query = MagicMock()
            if call_count[0] == 0:
                call_count[0] += 1
                mock_query.all.side_effect = Exception("Connection error")
            else:
                mock_query.all.return_value = [MagicMock()]
            return mock_query

        RedisDocTest.find = MagicMock(side_effect=mock_find)

        backend.find(RedisDocTest.name == "test")
        # Should try fallback


def test_redis_initialize_async_exception():
    """Test initialize_async() when initialize() raises exception."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Mock initialize to raise exception
        backend.initialize = MagicMock(side_effect=Exception("Initialize failed"))

        import pytest

        with pytest.raises(Exception, match="Initialize failed"):
            import asyncio

            asyncio.run(backend.initialize_async())
        # Should propagate exception


# Additional tests to reach 100% coverage


def test_redis_ensure_index_module_paths():
    """Test _ensure_index_ready with different module configurations."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Create models with different module configurations
        class ModelMainModule(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

            __module__ = "__main__"

        class ModelNoModule(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

            __module__ = ""

        class ModelRegularModule(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

            __module__ = "test_module"

        # Mock FT.INFO to raise exception (index doesn't exist)
        mock_redis.execute_command.side_effect = Exception("Index not found")

        for model_class in [ModelMainModule, ModelNoModule, ModelRegularModule]:
            backend = RedisMindtraceODM(model_class, "redis://localhost:6379")
            backend.logger = MagicMock()
            backend._is_initialized = True
            model_class.Meta.database = mock_redis

            backend._ensure_index_ready(model_class)
            # Should handle different module configurations


def test_redis_do_initialize_model_odms_not_in_models_to_migrate():
    """Test _do_initialize when model ODM's model_cls is not in models_to_migrate."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        # Create a separate model for the child ODM
        class ChildModel(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

        # Create multi-model backend
        backend = RedisMindtraceODM(models={"user": RedisDocTest}, redis_url="redis://localhost:6379")
        backend.logger = MagicMock()

        # Set Meta.database
        RedisDocTest.Meta.database = mock_redis
        ChildModel.Meta.database = mock_redis

        # Set child ODM's model_cls to a different model
        backend.user.model_cls = ChildModel

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            backend._do_initialize()
            # Should add ChildModel to models_to_migrate


def test_redis_do_initialize_exception_with_connection_in_type_name():
    """Test _do_initialize raises RuntimeError for migrator exceptions regardless of type name."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        class SomeConnectionProblem(Exception):
            pass

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = SomeConnectionProblem("boom")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()

def test_redis_ensure_index_module_main_path():
    """Test _ensure_index_ready with __main__ module."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.execute_command.side_effect = Exception("Index not found")

        class ModelMain(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

        ModelMain.__module__ = "__main__"

        backend = RedisMindtraceODM(ModelMain, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        ModelMain.Meta.database = mock_redis

        backend._ensure_index_ready(ModelMain)


def test_redis_ensure_index_module_regular_with_module():
    """Test _ensure_index_ready with regular module that has module name."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.execute_command.side_effect = Exception("Index not found")

        class ModelReg(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

        ModelReg.__module__ = "test_module"

        backend = RedisMindtraceODM(ModelReg, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        ModelReg.Meta.database = mock_redis

        backend._ensure_index_ready(ModelReg)


def test_redis_do_initialize_env_var_deletion_elif_branch_execution():
    """Test _do_initialize when elif branch for REDIS_OM_URL deletion executes."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend.redis_url = "redis://localhost:6379"
        RedisDocTest.Meta.database = mock_redis

        import os

        original_env = os.environ.get("REDIS_OM_URL", None)
        # Ensure REDIS_OM_URL is not set initially
        if "REDIS_OM_URL" in os.environ:
            del os.environ["REDIS_OM_URL"]

        # Track deletions
        deletions = []
        original_del = os.environ.__delitem__

        def mock_del(key):
            deletions.append(key)
            return original_del(key)

        try:
            with patch.object(os.environ, "__delitem__", mock_del):
                with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                    mock_migrator = MagicMock()
                    mock_migrator_class.return_value = mock_migrator

                    backend._do_initialize()
                    # The elif branch: original_redis_url is None AND REDIS_OM_URL in os.environ AND self.redis_url
                    # Since REDIS_OM_URL is set during init, it should be deleted
        finally:
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env


def test_redis_do_initialize_exception_connection_in_type():
    """Test _do_initialize raises RuntimeError for connection-like exception types."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        class ConnectionErrorType(Exception):
            pass

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = ConnectionErrorType("Error")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()

def test_redis_do_initialize_env_var_deletion_elif_executes():
    """Test _do_initialize elif branch for REDIS_OM_URL deletion."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend.redis_url = "redis://localhost:6379"
        RedisDocTest.Meta.database = mock_redis

        import os

        original_env = os.environ.get("REDIS_OM_URL", None)
        # Ensure REDIS_OM_URL is not set initially
        if "REDIS_OM_URL" in os.environ:
            del os.environ["REDIS_OM_URL"]

        # Track if deletion happens
        deletion_happened = [False]
        original_del = os.environ.__delitem__

        def mock_del(key):
            if key == "REDIS_OM_URL":
                deletion_happened[0] = True
            return original_del(key)

        try:
            with patch.object(os.environ, "__delitem__", mock_del):
                with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                    mock_migrator = MagicMock()
                    mock_migrator_class.return_value = mock_migrator

                    backend._do_initialize()
                    # The elif branch: original_redis_url is None AND REDIS_OM_URL in os.environ AND self.redis_url
                    # Since REDIS_OM_URL is set during init, it should be deleted
        finally:
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env


def test_redis_do_initialize_exception_connection_in_type_name():
    """Test _do_initialize raises RuntimeError for migrator failures."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        class ConnectionNamedError(Exception):
            pass

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = ConnectionNamedError("Error")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()

def test_redis_ensure_index_key_patterns_main_module():
    """Test _ensure_index_ready to execute for __main__ module.

    This test ensures:
    - if model_module == "__main__" check
    - key_patterns.append for __main__.{model_name}
    - key_patterns.append for {model_name}
    """
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to return index info (index exists with docs)
        def mock_execute_command(*args):
            if args[0] == "FT.INFO":
                return ["index_name", "test_index", "num_docs", 5]
            return None

        mock_redis.execute_command.side_effect = mock_execute_command
        mock_redis.keys.return_value = []

        class ModelMain(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"
                # NO model_key_prefix - ensures else branch

        ModelMain.__module__ = "__main__"  # Set in class definition

        # Verify it's set - use getattr to match what the code does
        model_module = getattr(ModelMain, "__module__", "")
        assert model_module == "__main__", f"Expected __main__, got {model_module}"

        backend = RedisMindtraceODM(ModelMain, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        ModelMain.Meta.database = mock_redis

        # Verify module is still set
        model_module_after = getattr(ModelMain, "__module__", "")
        assert model_module_after == "__main__", f"Expected __main__, got {model_module_after}"

        # redis-om may set model_key_prefix automatically during initialization
        # We need to patch getattr to return None for model_key_prefix to ensure else branch
        def mock_getattr(obj, name, default=None):
            if obj is ModelMain.Meta and name == "model_key_prefix":
                return None  # Force else branch at return original_getattr(obj, name, default)

        with patch("builtins.getattr", side_effect=mock_getattr):
            # Call the method - should execute# are executed when:
            # 1. model_key_prefix is None (else branch at 434)
            # 2. model_module == "__main__" (if at 435)
            backend._ensure_index_ready(ModelMain)

        # Verify the module was used
        assert getattr(ModelMain, "__module__", "") == "__main__"


def test_redis_ensure_index_key_patterns_regular_module():
    """Test _ensure_index_ready to execute for regular module."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.execute_command.side_effect = Exception("Index not found")

        class ModelReg(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"
                # NO model_key_prefix

        ModelReg.__module__ = "test_module"

        backend = RedisMindtraceODM(ModelReg, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        ModelReg.Meta.database = mock_redis

        backend._ensure_index_ready(ModelReg)
        # Should execute (regular module with model_module set)


def test_redis_do_initialize_exception_connection_type():
    """Test _do_initialize raises RuntimeError on migrator failures (connection-like type)."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        RedisDocTest.Meta.database = mock_redis

        class ConnectionErrorType(Exception):
            pass

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = ConnectionErrorType("Error")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()

def test_redis_do_initialize_database_assignment():
    """Test model.Meta.database assignment in loop.

    This executes in the loop when processing models_to_migrate.
    This happens after models are added to models_to_migrate.
    """
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()

        # Ensure models_to_migrate is not empty
        # In single-model mode, model_cls is added to models_to_migrate. Then loops through models_to_migrate
        # sets model.Meta.database = self.redis
        RedisDocTest.Meta.database = None  # Reset to ensure it executes

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator_class.return_value = mock_migrator

            backend._do_initialize()

            assert RedisDocTest.Meta.database == mock_redis


def test_redis_do_initialize_database_reassignment():
    """Test _do_initialize completes even when Meta.database access is customized."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        access_count = [0]

        class CustomMeta(type):
            def __getattribute__(self, name):
                if name == "database":
                    access_count[0] += 1
                    dct = object.__getattribute__(self, "__dict__")
                    return dct.get("database", None)
                return object.__getattribute__(self, name)

        class ModelWithCustomMeta(MindtraceRedisDocument):
            name: str = Field(index=True)
            age: int = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

        ModelWithCustomMeta.Meta = CustomMeta(
            "Meta", (type(ModelWithCustomMeta.Meta),), {"global_key_prefix": "testapp"}
        )

        backend = RedisMindtraceODM(ModelWithCustomMeta, "redis://localhost:6379")
        backend.logger = MagicMock()

        try:
            with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                mock_migrator = MagicMock()
                mock_migrator_class.return_value = mock_migrator

                backend._do_initialize()
                assert backend._is_initialized is True
        finally:
            pass

def test_redis_ensure_index():
    """Testkey patterns for __main__ module when model_key_prefix is None."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to return index info (index exists)
        def mock_execute_command(*args):
            if args[0] == "FT.INFO":
                return ["index_name", "test_index", "num_docs", 5]
            return None

        mock_redis.execute_command.side_effect = mock_execute_command
        mock_redis.keys.return_value = []

        class ModelMain(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

            __module__ = "__main__"

        backend = RedisMindtraceODM(ModelMain, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        ModelMain.Meta.database = mock_redis

        # Ensure model_key_prefix is None by deleting it if it exists
        # Delete it if it exists (redis-om might set it automatically)
        if hasattr(ModelMain.Meta, "model_key_prefix"):
            delattr(ModelMain.Meta, "model_key_prefix")

        # Verify it's None
        assert getattr(ModelMain.Meta, "model_key_prefix", None) is None, "model_key_prefix should be None"

        # Call the method - should execute(__main__ module, model_key_prefix is None)
        # The getattr call atwill return None since we deleted the attribute
        backend._ensure_index_ready(ModelMain)


def test_redis_ensure_index_lines_regular_module():
    """Testkey patterns for regular module when model_key_prefix is None."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis

        # Mock FT.INFO to return index info (index exists)
        def mock_execute_command(*args):
            if args[0] == "FT.INFO":
                return ["index_name", "test_index", "num_docs", 5]
            return None

        mock_redis.execute_command.side_effect = mock_execute_command
        mock_redis.keys.return_value = []

        class ModelReg(MindtraceRedisDocument):
            name: str = Field(index=True)

            class Meta:
                global_key_prefix = "testapp"

            __module__ = "test_module"

        backend = RedisMindtraceODM(ModelReg, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = True
        ModelReg.Meta.database = mock_redis

        # Ensure model_key_prefix is None by deleting it if it exists
        if hasattr(ModelReg.Meta, "model_key_prefix"):
            delattr(ModelReg.Meta, "model_key_prefix")

        # Verify it's None
        assert getattr(ModelReg.Meta, "model_key_prefix", None) is None, "model_key_prefix should be None"

        # Call the method - should execute(regular module, model_key_prefix is None)
        # The getattr call atwill return None since we deleted the attribute
        backend._ensure_index_ready(ModelReg)


def test_redis_do_initialize_lines_env_var_deletion():
    """Testelif branch for REDIS_OM_URL deletion.

    This test ensures the elif branch executes when:
    - original_redis_url is None (REDIS_OM_URL not set initially)
    - REDIS_OM_URL is set during _do_initialize
    - The finally block deletes it
    """
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend.redis_url = "redis://localhost:6379"
        RedisDocTest.Meta.database = mock_redis

        # Ensure original_redis_url is None (REDIS_OM_URL not set initially)
        original_env = os.environ.get("REDIS_OM_URL", None)
        if "REDIS_OM_URL" in os.environ:
            del os.environ["REDIS_OM_URL"]

        # Verify REDIS_OM_URL is not set before the test
        assert "REDIS_OM_URL" not in os.environ, "REDIS_OM_URL should not be set initially"

        # Patch os.environ.get to return None ateven thoughsets it
        # This simulates the case where original_redis_url is None
        original_get = os.environ.get
        call_count = [0]

        def mock_get(key, default=None):
            if key == "REDIS_OM_URL":
                call_count[0] += 1
                # At return None to simulate original_redis_url being None
                # This is the call that sets original_redis_url
                if call_count[0] == 1:  # First call
                    return None
            return original_get(key, default)

        try:
            with patch.object(os.environ, "get", mock_get):
                with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
                    mock_migrator = MagicMock()
                    mock_migrator_class.return_value = mock_migrator

                    # Call _do_initialize which should:
                    # 1. Set REDIS_OM_URL. 2. Get original_redis_url (returns None due to mock)
                    # 3. Set REDIS_OM_URL again. 4. In finally block:
                    #    - if original_redis_url is not None -> False (skip, because we mocked it to return None)
                    #    - elif "REDIS_OM_URL" in os.environ and self.redis_url -> True
                    #    - del os.environ["REDIS_OM_URL"] (deletes it)
                    backend._do_initialize()

                    # Verify the elif branch was executed by checking that REDIS_OM_URL was deleted
                    # If the elif branch executed, REDIS_OM_URL should not be in os.environ
                    assert "REDIS_OM_URL" not in os.environ, (
                        f"Current value: {os.environ.get('REDIS_OM_URL', 'not set')}"
                    )
        finally:
            # Restore original environment
            if original_env is not None:
                os.environ["REDIS_OM_URL"] = original_env
            elif "REDIS_OM_URL" in os.environ:
                del os.environ["REDIS_OM_URL"]


def test_redis_do_initialize_connection_error_pass():
    """Test _do_initialize raises RuntimeError on migrator failures (no swallow)."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = False
        RedisDocTest.Meta.database = mock_redis

        class ConnectionErrorType(Exception):
            pass

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_class:
            mock_migrator = MagicMock()
            mock_migrator.run.side_effect = ConnectionErrorType("Connection error")
            mock_migrator_class.return_value = mock_migrator

            with pytest.raises(RuntimeError, match="Redis initialization failed during migration"):
                backend._do_initialize()
            assert backend._is_initialized is False


def test_redis_do_initialize_runs_migrator_and_checks_index_ready():
    """Initialization should run Migrator once and then check index readiness."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(RedisDocTest, "redis://localhost:6379")
        backend.logger = MagicMock()
        backend._is_initialized = False
        RedisDocTest.Meta.database = mock_redis

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_cls:
            mock_migrator = MagicMock()
            mock_migrator_cls.return_value = mock_migrator

            backend._ensure_index_ready = MagicMock()
            backend._do_initialize()

            mock_migrator.run.assert_called_once()
            backend._ensure_index_ready.assert_called_once_with(RedisDocTest)
            assert backend._is_initialized is True


def test_redis_do_initialize_multimodel_runs_single_migrator():
    """Parent multi-model init should run one migration pass and mark children initialized."""
    with patch("mindtrace.database.backends.redis_odm.get_redis_connection") as mock_get_redis:
        mock_redis = MagicMock()
        mock_get_redis.return_value = mock_redis
        mock_redis.ping.return_value = True

        backend = RedisMindtraceODM(
            models={"user": RedisDocTest, "main": RedisDocMainModuleTest},
            redis_url="redis://localhost:6379",
        )
        backend.logger = MagicMock()

        with patch("mindtrace.database.backends.redis_odm.Migrator") as mock_migrator_cls:
            mock_migrator = MagicMock()
            mock_migrator_cls.return_value = mock_migrator

            backend._ensure_index_ready = MagicMock()
            backend._do_initialize()

            mock_migrator.run.assert_called_once()
            assert backend.user._is_initialized is True
            assert backend.main._is_initialized is True
            assert backend._ensure_index_ready.call_count == 2
