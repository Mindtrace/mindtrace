from typing import Any, Type

import pytest

from mindtrace.registry import Archiver


class TestArchiver:
    def test_archiver_initialization(self):
        """Test that Archiver can be initialized with required arguments."""
        # Create a concrete implementation for testing
        class TestArchiverImpl(Archiver):
            ASSOCIATED_TYPES = {str, int}
            
            def load(self, data_type: Type[Any]) -> Any:
                return None
                
            def save(self, obj: Any) -> None:
                pass
        
        # Test initialization
        archiver = TestArchiverImpl(uri="test://path")
        assert archiver is not None
        assert hasattr(archiver, 'logger')

    def test_archiver_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError when not implemented."""
        class IncompleteArchiver(Archiver):
            ASSOCIATED_TYPES = {str}
            
            def load(self, data_type: Type[Any]) -> Any:
                return None
        
        archiver = IncompleteArchiver(uri="test://path")
        
        # Test that save() raises NotImplementedError
        with pytest.raises(NotImplementedError, match="Subclasses must implement save()"):
            archiver.save("test")

    def test_archiver_load_abstract_method(self):
        """Test that the load abstract method raises NotImplementedError when not implemented."""
        class IncompleteArchiver(Archiver):
            ASSOCIATED_TYPES = {str}
            
            def save(self, obj: Any) -> None:
                pass
        
        archiver = IncompleteArchiver(uri="test://path")
        
        # Test that load() raises NotImplementedError
        with pytest.raises(NotImplementedError, match="Subclasses must implement load()"):
            archiver.load(str)

    def test_archiver_base_class_exception(self):
        """Test that the base Archiver class itself doesn't require ASSOCIATED_TYPES."""
        # This should not raise an error
        class BaseArchiver(Archiver):
            def load(self, data_type: Type[Any]) -> Any:
                return None
                
            def save(self, obj: Any) -> None:
                pass
        
        # Test initialization
        archiver = BaseArchiver(uri="test://path")
        assert archiver is not None
