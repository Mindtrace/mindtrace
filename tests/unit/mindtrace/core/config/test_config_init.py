"""Test cases for the config module __init__.py file."""

from mindtrace.core.config import Config, ConfigModel, CoreConfig


class TestConfigModule:
    """Test cases for the config module imports and __all__."""

    def test_module_imports(self):
        """Test that all expected classes are importable."""
        assert Config is not None
        assert ConfigModel is not None
        assert CoreConfig is not None

    def test_core_config_is_alias(self):
        """Test that CoreConfig is an alias for Config."""
        assert CoreConfig is Config

    def test_config_has_dict_access(self):
        """Test that Config has ConfigModel's dict-access methods."""
        assert hasattr(Config, "__getitem__")
        assert hasattr(Config, "get")
        assert hasattr(Config, "get_secret")

    def test_module_all_attribute(self):
        """Test that __all__ is properly defined."""
        from mindtrace.core.config import __all__

        assert "Config" in __all__
        assert "ConfigModel" in __all__
        assert "CoreConfig" in __all__

    def test_import_from_module(self):
        """Test importing specific items from the module."""
        from mindtrace.core.config import Config as C
        from mindtrace.core.config import ConfigModel as CM
        from mindtrace.core.config import CoreConfig as CC

        assert C is Config
        assert CM is ConfigModel
        assert CC is CoreConfig

    def test_config_instantiation(self):
        """Test that Config can be instantiated."""
        assert hasattr(Config, "model_config")
        assert hasattr(Config, "settings_customise_sources")

    def test_module_metadata(self):
        """Test that the module has expected metadata."""
        import mindtrace.core.config as config_module

        assert hasattr(config_module, "__file__")
        assert config_module.__file__.endswith("__init__.py")
        assert config_module.__package__ == "mindtrace.core.config"
        assert config_module.__name__ == "mindtrace.core.config"
