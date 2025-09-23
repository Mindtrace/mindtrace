import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel, SecretStr

from mindtrace.core.config import Config, CoreConfig
from mindtrace.core.config.config import _AttrView


class TestConfig:
    """Test cases for the Config class."""

    def test_config_init_empty(self):
        """Test Config initialization with no arguments."""
        config = Config()
        assert isinstance(config, dict)
        assert len(config) == 0

    def test_config_init_with_dict(self):
        """Test Config initialization with dictionary."""
        data = {"key1": "value1", "key2": {"nested": "value"}}
        config = Config(data)
        assert config["key1"] == "value1"
        assert config["key2"]["nested"] == "value"

    def test_config_init_with_list(self):
        """Test Config initialization with list of settings."""
        data1 = {"key1": "value1"}
        data2 = {"key2": "value2", "key1": "override"}
        config = Config([data1, data2])
        assert config["key1"] == "override"  # Second should override first
        assert config["key2"] == "value2"

    def test_config_dict_access(self):
        """Test dictionary-style access."""
        data = {"section": {"key": "value"}}
        config = Config(data)
        assert config["section"]["key"] == "value"

    def test_config_attr_access(self):
        """Test attribute-style access."""
        data = {"section": {"key": "value"}}
        config = Config(data)
        assert hasattr(config, "section")
        assert config.section.key == "value"

    def test_config_attr_access_missing(self):
        """Test AttributeError for missing attributes."""
        config = Config()
        with pytest.raises(AttributeError, match="No such attribute: missing"):
            config.missing

    def test_config_deep_update(self):
        """Test deep update functionality."""
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"b": 3, "d": 4}}
        config = Config()
        result = config._deep_update(base, override)
        assert result["a"]["b"] == 3
        assert result["a"]["c"] == 2
        assert result["a"]["d"] == 4

    def test_config_deep_update_static(self):
        """Test static deep update functionality."""
        base = {"a": {"b": 1, "c": 2}}
        override = {"a": {"b": 3, "d": 4}}
        result = Config._deep_update_dict(base, override)
        assert result["a"]["b"] == 3
        assert result["a"]["c"] == 2
        assert result["a"]["d"] == 4

    def test_config_coerce_env_value(self):
        """Test environment value coercion."""
        assert Config._coerce_env_value("true") is True
        assert Config._coerce_env_value("false") is False
        assert Config._coerce_env_value("123") == 123
        assert Config._coerce_env_value("-456") == -456
        assert Config._coerce_env_value("3.14") == 3.14
        assert Config._coerce_env_value("hello") == "hello"

    def test_config_apply_env_overrides_static(self):
        """Test static environment variable override application."""
        base = {"section": {"key": "original"}}
        with patch.dict(os.environ, {"section__key": "override"}):
            result = Config._apply_env_overrides_static(base)
            assert result["section"]["key"] == "override"

    def test_config_apply_env_overrides_nested(self):
        """Test nested environment variable overrides."""
        base = {"level1": {"level2": {"key": "original"}}}
        with patch.dict(os.environ, {"level1__level2__key": "override"}):
            result = Config._apply_env_overrides_static(base)
            assert result["level1"]["level2"]["key"] == "override"

    def test_config_apply_env_overrides_multiple(self):
        """Test multiple environment variable overrides."""
        base = {"a": {"b": "original1"}, "c": {"d": "original2"}}
        with patch.dict(os.environ, {"a__b": "override1", "c__d": "override2"}):
            result = Config._apply_env_overrides_static(base)
            assert result["a"]["b"] == "override1"
            assert result["c"]["d"] == "override2"

    def test_config_apply_env_overrides_ignore_invalid(self):
        """Test that invalid environment variables are ignored."""
        base = {"section": {"key": "original"}}
        with patch.dict(os.environ, {"INVALID": "value", "section__key": "override"}):
            result = Config._apply_env_overrides_static(base)
            assert result["section"]["key"] == "override"
            assert "INVALID" not in result

    def test_config_apply_env_overrides_empty_parts(self):
        """Test environment variables with empty parts are ignored."""
        base = {"section": {"key": "original"}}
        with patch.dict(os.environ, {"__section__key": "override", "section____key": "override2"}):
            result = Config._apply_env_overrides_static(base)
            assert result["section"]["key"] == "original"  # Should remain unchanged

    def test_config_apply_env_overrides_instance(self):
        """Test instance method for environment overrides."""
        config = Config()
        base = {"section": {"key": "original"}}
        with patch.dict(os.environ, {"section__key": "override"}):
            result = config._apply_env_overrides(base)
            assert result["section"]["key"] == "override"

    def test_config_apply_env_overrides_disabled(self):
        """Test that environment overrides can be disabled."""
        data = {"key": "value"}
        config = Config(data, apply_env_overrides=False)
        with patch.dict(os.environ, {"key": "override"}):
            assert config["key"] == "value"  # Should not be overridden

    def test_config_apply_env_overrides_enabled(self):
        """Test that environment overrides are applied when enabled."""
        data = {"key": "value"}
        with patch.dict(os.environ, {"key": "override"}):
            config = Config(data, apply_env_overrides=True)
            assert config["key"] == "override"

    def test_config_stringify_dict_static(self):
        """Test static stringify functionality."""
        data = {"key": "value", "nested": {"inner": "test"}}
        result = Config._stringify_dict_static(data)
        assert result["key"] == "value"
        assert result["nested"]["inner"] == "test"

    def test_config_stringify_with_tilde_expansion(self):
        """Test that tilde expansion works in stringify."""
        data = {"path": "~/test/path"}
        result = Config._stringify_dict_static(data)
        expected_path = os.path.expanduser("~/test/path")
        assert result["path"] == expected_path

    def test_config_repr(self):
        """Test Config string representation."""
        config = Config({"key": "value"})
        repr_str = repr(config)
        assert "Config" in repr_str or "{" in repr_str  # Should show dict-like representation


class TestConfigSecrets:
    """Test cases for secret handling in Config."""

    def test_config_with_secret_str(self):
        """Test Config with SecretStr fields."""

        class TestModel(BaseModel):
            api_key: SecretStr
            normal_field: str

        model = TestModel(api_key="secret123", normal_field="normal")
        config = Config(model)

        # Secret should be masked
        assert config.api_key == "********"
        assert config.normal_field == "normal"

        # Should be able to get the real secret
        assert config.get_secret("api_key") == "secret123"

    def test_config_secret_paths(self):
        """Test secret path tracking."""

        class TestModel(BaseModel):
            api_key: SecretStr
            nested: dict

        model = TestModel(api_key="secret123", nested={"other": "value"})
        config = Config(model)

        paths = config.secret_paths()
        assert "api_key" in paths

    def test_config_get_secret_nested(self):
        """Test getting secrets from nested paths."""

        class NestedModel(BaseModel):
            key: SecretStr

        class TestModel(BaseModel):
            nested: NestedModel

        model = TestModel(nested=NestedModel(key="secret123"))
        config = Config(model)

        assert config.get_secret("nested", "key") == "secret123"

    def test_config_get_secret_missing(self):
        """Test getting non-existent secret."""
        config = Config({"key": "value"})
        assert config.get_secret("missing") is None
        assert config.get_secret("key") is None  # Not a secret field


class TestConfigLoading:
    """Test cases for Config.load method."""

    def test_config_load_with_defaults(self):
        """Test Config.load with defaults."""
        defaults = {"key": "value"}
        config = Config.load(defaults=defaults)
        assert config["key"] == "value"

    def test_config_load_with_overrides(self):
        """Test Config.load with overrides."""
        defaults = {"key": "original"}
        overrides = {"key": "override"}
        config = Config.load(defaults=defaults, overrides=overrides)
        assert config["key"] == "override"

    def test_config_load_with_base_model(self):
        """Test Config.load with BaseModel."""

        class TestModel(BaseModel):
            key: str = "default"

        config = Config.load(defaults=TestModel())
        assert config["key"] == "default"

    def test_config_load_with_list_overrides(self):
        """Test Config.load with list of overrides."""
        defaults = {"key": "original"}
        overrides = [{"key": "override1"}, {"key": "override2"}]
        config = Config.load(defaults=defaults, overrides=overrides)
        assert config["key"] == "override2"  # Last override wins

    def test_config_load_with_file_loader(self):
        """Test Config.load with file loader."""

        def mock_loader():
            return {"loaded": "value"}

        config = Config.load(file_loader=mock_loader)
        assert config["loaded"] == "value"

    def test_config_load_json(self):
        """Test Config.load_json method."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"key": "value"}, f)
            temp_path = f.name

        try:
            config = Config.load_json(temp_path)
            assert config["key"] == "value"
        finally:
            os.unlink(temp_path)


class TestConfigCloning:
    """Test cases for Config cloning and overrides."""

    def test_config_clone_with_overrides(self):
        """Test cloning with overrides."""
        original = Config({"key": "original"})
        clone = original.clone_with_overrides({"key": "override"})

        assert original["key"] == "original"  # Original unchanged
        assert clone["key"] == "override"  # Clone has override

    def test_config_clone_with_multiple_overrides(self):
        """Test cloning with multiple overrides."""
        original = Config({"key": "original"})
        clone = original.clone_with_overrides({"key": "override1"}, {"key": "override2"})
        assert clone["key"] == "override2"  # Last override wins

    def test_config_clone_with_base_model(self):
        """Test cloning with BaseModel override."""

        class TestModel(BaseModel):
            key: str = "model_value"

        original = Config({"key": "original"})
        clone = original.clone_with_overrides(TestModel())
        assert clone["key"] == "model_value"

    def test_config_clone_with_none(self):
        """Test cloning with None override (should be ignored)."""
        original = Config({"key": "original"})
        clone = original.clone_with_overrides(None)
        assert clone["key"] == "original"  # Should remain unchanged

    def test_config_clone_with_invalid_type(self):
        """Test cloning with invalid override type."""
        original = Config({"key": "original"})
        with pytest.raises(TypeError, match="Unsupported override type"):
            original.clone_with_overrides("invalid")


class TestConfigJSON:
    """Test cases for JSON save/load functionality."""

    def test_config_save_json(self):
        """Test saving config to JSON."""
        config = Config({"key": "value", "nested": {"inner": "test"}})

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            config.save_json(temp_path)
            with open(temp_path, "r") as f:
                data = json.load(f)
            assert data["key"] == "value"
            assert data["nested"]["inner"] == "test"
        finally:
            os.unlink(temp_path)

    def test_config_save_json_masked_secrets(self):
        """Test saving config with masked secrets."""

        class TestModel(BaseModel):
            api_key: SecretStr

        model = TestModel(api_key="secret123")
        config = Config(model)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            config.save_json(temp_path, reveal_secrets=False)
            with open(temp_path, "r") as f:
                data = json.load(f)
            assert data["api_key"] == "********"  # Should be masked
        finally:
            os.unlink(temp_path)

    def test_config_save_json_create_directories(self):
        """Test that save_json creates parent directories."""
        config = Config({"key": "value"})

        with tempfile.TemporaryDirectory() as temp_dir:
            nested_path = Path(temp_dir) / "nested" / "deep" / "config.json"
            config.save_json(nested_path)
            assert nested_path.exists()

    def test_config_save_json_error_handling(self):
        """Test error handling in save_json."""
        config = Config({"key": "value"})

        # Test with invalid path (should raise RuntimeError)
        with pytest.raises(RuntimeError, match="Failed to save config"):
            config.save_json("/invalid/path/that/does/not/exist/config.json")


class TestCoreConfig:
    """Test cases for CoreConfig class."""

    def test_core_config_init_empty(self):
        """Test CoreConfig initialization with no arguments."""
        config = CoreConfig()
        assert isinstance(config, Config)
        # Should have CoreSettings loaded
        assert hasattr(config, "MINDTRACE_API_KEYS")

    def test_core_config_init_with_extra_settings(self):
        """Test CoreConfig with extra settings."""
        extra = {"custom_key": "custom_value"}
        config = CoreConfig(extra)
        assert config["custom_key"] == "custom_value"

    def test_core_config_init_with_list(self):
        """Test CoreConfig with list of extra settings."""
        extra1 = {"key1": "value1"}
        extra2 = {"key2": "value2"}
        config = CoreConfig([extra1, extra2])
        assert config["key1"] == "value1"
        assert config["key2"] == "value2"

    def test_core_config_init_with_base_model(self):
        """Test CoreConfig with BaseModel extra settings."""

        class TestModel(BaseModel):
            custom_key: str = "model_value"

        config = CoreConfig(TestModel())
        assert config["custom_key"] == "model_value"

    def test_core_config_override_precedence(self):
        """Test that extra settings override CoreSettings."""
        extra = {"MINDTRACE_TEST_PARAM": "override_value"}
        config = CoreConfig(extra)
        assert config["MINDTRACE_TEST_PARAM"] == "override_value"


class TestAttrView:
    """Test cases for _AttrView class."""

    def test_attr_view_init(self):
        """Test _AttrView initialization."""
        data = {"key": "value"}
        view = _AttrView(data)
        assert view._data == data

    def test_attr_view_getattr(self):
        """Test _AttrView attribute access."""
        data = {"key": "value", "nested": {"inner": "test"}}
        view = _AttrView(data)
        assert view.key == "value"
        assert view.nested.inner == "test"

    def test_attr_view_getattr_missing(self):
        """Test _AttrView missing attribute."""
        data = {"key": "value"}
        view = _AttrView(data)
        with pytest.raises(AttributeError, match="No such attribute: missing"):
            view.missing

    def test_attr_view_getitem(self):
        """Test _AttrView item access."""
        data = {"key": "value", "nested": {"inner": "test"}}
        view = _AttrView(data)
        assert view["key"] == "value"
        assert view["nested"]["inner"] == "test"

    def test_attr_view_with_lists(self):
        """Test _AttrView with lists."""
        data = {"items": [{"name": "item1"}, {"name": "item2"}]}
        view = _AttrView(data)
        items = view.items
        assert len(items) == 2
        assert items[0].name == "item1"
        assert items[1].name == "item2"

    def test_attr_view_repr(self):
        """Test _AttrView string representation."""
        data = {"key": "value"}
        view = _AttrView(data)
        repr_str = repr(view)
        assert "_AttrView" in repr_str
        assert "key" in repr_str


class TestConfigEdgeCases:
    """Test cases for edge cases and error conditions."""

    def test_config_with_none_values(self):
        """Test Config with None values."""
        data = {"key": None, "nested": {"inner": None}}
        config = Config(data)
        # Config converts None to string "None"
        assert config["key"] == "None"
        assert config["nested"]["inner"] == "None"

    def test_config_with_empty_dict(self):
        """Test Config with empty dictionary."""
        data = {}
        config = Config(data)
        assert len(config) == 0

    def test_config_with_empty_list(self):
        """Test Config with empty list."""
        data = {"items": []}
        config = Config(data)
        assert config["items"] == []

    def test_config_with_mixed_types(self):
        """Test Config with mixed data types - all converted to strings."""
        data = {
            "string": "value",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        }
        config = Config(data)
        # All values are converted to strings by _stringify_and_mask
        assert config["string"] == "value"
        assert config["int"] == "42"  # Converted to string
        assert config["float"] == "3.14"  # Converted to string
        assert config["bool"] == "True"  # Converted to string
        assert config["list"] == ["1", "2", "3"]  # All elements converted to strings
        assert config["dict"]["nested"] == "value"

    def test_config_deep_nesting(self):
        """Test Config with deep nesting."""
        data = {"level1": {"level2": {"level3": {"level4": "deep_value"}}}}
        config = Config(data)
        assert config.level1.level2.level3.level4 == "deep_value"

    def test_config_unicode_values(self):
        """Test Config with unicode values."""
        data = {"unicode": "测试", "emoji": "🚀"}
        config = Config(data)
        assert config["unicode"] == "测试"
        assert config["emoji"] == "🚀"


class TestConfigUtils:
    def test_config_deep_update_nested_merge(self):
        """Test _deep_update with nested dictionary merging."""
        config = Config()
        base = {"level1": {"level2": {"key": "original"}}}
        override = {"level1": {"level2": {"new_key": "new_value"}}}
        result = config._deep_update(base, override)
        assert result["level1"]["level2"]["key"] == "original"
        assert result["level1"]["level2"]["new_key"] == "new_value"

    def test_config_attr_access_with_lists(self):
        """Test attribute access with list values containing dicts."""
        data = {"items": [{"name": "item1", "value": 1}, {"name": "item2", "value": 2}]}
        config = Config(data)
        items = config["items"]
        assert len(items) == 2
        assert items[0]["name"] == "item1"
        assert items[1]["name"] == "item2"

    def test_config_load_with_base_model_defaults(self):
        """Test Config.load with BaseModel as defaults."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            field1: str = "default_value"
            field2: int = 42

        model = TestModel()
        config = Config.load(defaults=model)
        assert config["field1"] == "default_value"
        assert config["field2"] == "42"

    def test_config_load_with_list_overrides(self):
        """Test Config.load with list of overrides."""
        overrides = [{"key1": "value1"}, {"key2": "value2", "key1": "override"}]
        config = Config.load(overrides=overrides)
        assert config["key1"] == "override"
        assert config["key2"] == "value2"

    def test_config_clone_with_dict_override(self):
        """Test clone_with_overrides with dictionary."""
        config = Config({"original": "value"})
        cloned = config.clone_with_overrides({"new_key": "new_value"})
        assert cloned["original"] == "value"
        assert cloned["new_key"] == "new_value"

    def test_config_clone_with_base_model_override(self):
        """Test clone_with_overrides with BaseModel."""
        from pydantic import BaseModel

        class OverrideModel(BaseModel):
            override_field: str = "override_value"

        config = Config({"original": "value"})
        cloned = config.clone_with_overrides(OverrideModel())
        assert cloned["original"] == "value"
        assert cloned["override_field"] == "override_value"

    def test_config_clone_with_list_override(self):
        """Test clone_with_overrides with list."""
        config = Config({"original": "value"})
        cloned = config.clone_with_overrides([{"list1": "value1"}, {"list2": "value2"}])
        assert cloned["original"] == "value"
        assert cloned["list1"] == "value1"
        assert cloned["list2"] == "value2"

    def test_config_clone_with_tuple_override(self):
        """Test clone_with_overrides with tuple."""
        config = Config({"original": "value"})
        cloned = config.clone_with_overrides(({"tuple_key": "tuple_value"},))
        assert cloned["original"] == "value"
        assert cloned["tuple_key"] == "tuple_value"

    def test_config_clone_with_none_override(self):
        """Test clone_with_overrides with None."""
        config = Config({"original": "value"})
        cloned = config.clone_with_overrides(None)
        assert cloned["original"] == "value"
        assert len(cloned) == 1

    def test_config_clone_with_invalid_type(self):
        """Test clone_with_overrides with invalid type."""
        config = Config({"original": "value"})
        with pytest.raises(TypeError, match="Unsupported override type"):
            config.clone_with_overrides("invalid_string")

    def test_config_stringify_dict_static_with_secret_str(self):
        """Test _stringify_dict_static with SecretStr."""
        from pydantic import SecretStr

        data = {"secret": SecretStr("secret_value"), "normal": "normal_value"}
        result = Config._stringify_dict_static(data)
        assert result["secret"] == "secret_value"
        assert result["normal"] == "normal_value"

    def test_config_stringify_dict_static_with_anyurl(self):
        """Test _stringify_dict_static with AnyUrl."""
        from pydantic import AnyUrl

        data = {"url": AnyUrl("https://example.com"), "normal": "normal_value"}
        result = Config._stringify_dict_static(data)
        assert result["url"] == "https://example.com/"
        assert result["normal"] == "normal_value"

    def test_config_stringify_dict_static_with_list(self):
        """Test _stringify_dict_static with list."""
        data = {"items": [1, 2, 3], "nested": [{"key": "value"}]}
        result = Config._stringify_dict_static(data)
        assert result["items"] == ["1", "2", "3"]
        assert result["nested"] == [{"key": "value"}]

    def test_config_stringify_dict_static_with_tuple(self):
        """Test _stringify_dict_static with tuple."""
        data = {"items": (1, 2, 3), "normal": "value"}
        result = Config._stringify_dict_static(data)
        assert result["items"] == ["1", "2", "3"]  # Tuple converted to list
        assert result["normal"] == "value"

    def test_config_stringify_dict_static_with_set(self):
        """Test _stringify_dict_static with set."""
        data = {"items": {1, 2, 3}, "normal": "value"}
        result = Config._stringify_dict_static(data)
        assert set(result["items"]) == {"1", "2", "3"}
        assert result["normal"] == "value"

    def test_config_collect_secret_paths_from_model(self):
        """Test _collect_secret_paths_from_model."""
        from pydantic import BaseModel, SecretStr

        class TestModel(BaseModel):
            normal_field: str
            secret_field: SecretStr
            nested: "TestNestedModel"

        class TestNestedModel(BaseModel):
            nested_secret: SecretStr

        config = Config()
        paths = config._collect_secret_paths_from_model(TestModel)
        assert ("secret_field",) in paths
        # Note: nested model paths might not be collected the same way
        assert ("normal_field",) not in paths

    def test_config_is_secret_annotation_with_union(self):
        """Test _is_secret_annotation with Union type."""
        from typing import Union

        config = Config()
        # Test Union with SecretStr
        assert config._is_secret_annotation(Union[str, SecretStr])
        # Test Union without SecretStr
        assert not config._is_secret_annotation(Union[str, int])
        # Test None annotation
        assert not config._is_secret_annotation(None)

    def test_config_extract_model_class_with_union(self):
        """Test _extract_model_class with Union type."""
        from typing import Union

        from pydantic import BaseModel

        class TestModel(BaseModel):
            field: str

        config = Config()
        # Test Union with BaseModel
        model_class = config._extract_model_class(Union[str, TestModel])
        assert model_class == TestModel
        # Test Union without BaseModel
        assert config._extract_model_class(Union[str, int]) is None
        # Test invalid type
        assert config._extract_model_class("not_a_type") is None

    def test_config_save_json_with_revealed_secrets(self):
        """Test save_json with reveal_secrets=True."""
        import os
        import tempfile

        from pydantic import SecretStr

        config = Config({"secret": SecretStr("secret_value")})

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            temp_path = f.name

        try:
            config.save_json(temp_path, reveal_secrets=True)
            with open(temp_path, "r") as f:
                data = json.load(f)
            assert data["secret"] == "secret_value"
        finally:
            os.unlink(temp_path)

    def test_config_save_json_error_handling_os_error(self):
        """Test save_json error handling for OSError."""
        config = Config({"key": "value"})

        # Try to save to a path that will cause OSError (permission denied)
        with pytest.raises(RuntimeError, match="Failed to save config"):
            config.save_json("/root/forbidden_path.json")

    def test_config_load_json_file_not_found(self):
        """Test load_json with non-existent file."""
        with pytest.raises(FileNotFoundError):
            Config.load_json("/non/existent/path.json")

    def test_config_load_with_file_loader_returning_none(self):
        """Test Config.load with file_loader returning None."""

        def none_loader():
            return None

        config = Config.load(file_loader=none_loader)
        assert len(config) == 0

    def test_config_load_with_file_loader_returning_empty(self):
        """Test Config.load with file_loader returning empty dict."""

        def empty_loader():
            return {}

        config = Config.load(file_loader=empty_loader)
        assert len(config) == 0

    def test_config_stringify_and_mask_with_secret_paths(self):
        """Test _stringify_and_mask with secret paths."""

        config = Config()
        config._secret_paths = {("secret_field",)}
        config._secrets = {("secret_field",): "real_secret"}

        data = {"secret_field": "masked_value", "normal_field": "normal_value"}
        result = config._stringify_and_mask(data)
        assert result["secret_field"] == "********"
        assert result["normal_field"] == "normal_value"

    def test_config_stringify_and_mask_with_anyurl_secret(self):
        """Test _stringify_and_mask with AnyUrl in secret path."""
        from pydantic import AnyUrl

        config = Config()
        config._secret_paths = {("url_field",)}

        data = {"url_field": AnyUrl("https://secret.com")}
        result = config._stringify_and_mask(data)
        assert result["url_field"] == "********"

    def test_config_stringify_and_mask_with_tilde_expansion(self):
        """Test _stringify_and_mask with tilde expansion."""
        config = Config()
        data = {"path": "~/test/path", "normal": "value"}
        result = config._stringify_and_mask(data)
        # Should expand ~ to home directory
        assert result["path"].startswith("/")
        assert result["normal"] == "value"

    def test_config_coerce_env_value_edge_cases(self):
        """Test _coerce_env_value with edge cases."""
        # Test empty string
        assert Config._coerce_env_value("") == ""
        # Test string that looks like number but has extra chars
        assert Config._coerce_env_value("123abc") == "123abc"
        # Test negative zero
        assert Config._coerce_env_value("-0") == 0
        # Test very large number
        assert Config._coerce_env_value("999999999999999999") == 999999999999999999

    def test_config_apply_env_overrides_static_with_empty_parts_edge_cases(self):
        """Test _apply_env_overrides_static with various empty parts edge cases."""
        base = {"section": {"key": "original"}}

        # Test multiple consecutive delimiters
        with patch.dict(os.environ, {"section____key": "value1", "section______key": "value2"}):
            result = Config._apply_env_overrides_static(base)
            assert result["section"]["key"] == "original"  # Should be ignored

        # Test leading and trailing delimiters
        with patch.dict(os.environ, {"__section__key": "value1", "section__key__": "value2"}):
            result = Config._apply_env_overrides_static(base)
            assert result["section"]["key"] == "original"  # Should be ignored

    def test_config_apply_env_overrides_static_with_whitespace_parts(self):
        """Test _apply_env_overrides_static with whitespace in parts."""
        base = {"section": {"key": "original"}}

        # Test with whitespace that gets stripped
        with patch.dict(os.environ, {" section __ key ": "value"}):
            result = Config._apply_env_overrides_static(base)
            assert result["section"]["key"] == "value"

    def test_config_apply_env_overrides_static_nested_path_does_not_exist(self):
        """Test _apply_env_overrides_static when nested path doesn't exist."""
        base = {"section": {"key": "original"}}

        # Test with path that doesn't exist
        with patch.dict(os.environ, {"nonexistent__key": "value"}):
            result = Config._apply_env_overrides_static(base)
            assert result == base  # Should remain unchanged

    def test_config_apply_env_overrides_static_nested_path_not_dict(self):
        """Test _apply_env_overrides_static when nested path is not a dict."""
        base = {"section": "not_a_dict"}

        # Test with path that exists but is not a dict
        with patch.dict(os.environ, {"section__key": "value"}):
            result = Config._apply_env_overrides_static(base)
            assert result == base  # Should remain unchanged
