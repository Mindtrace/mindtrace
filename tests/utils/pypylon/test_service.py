"""Pytest test suite for the pypylon service functionality."""

import pytest
from tests.utils.pypylon.client import PyPylonProxy, PyPylonClientError, is_pypylon_available


class TestPyPylonService:
    """Test suite for pypylon service functionality."""

    @pytest.fixture(scope="class")
    def proxy(self):
        """Fixture providing a PyPylonProxy instance for service tests."""
        if not is_pypylon_available():
            pytest.skip("pypylon is not available through any backend")
        
        try:
            proxy = PyPylonProxy()
            backend_type = proxy.get_backend_type()
            print(f"Proxy created successfully using backend: {backend_type}")
            return proxy
        except Exception as e:
            pytest.skip(f"Failed to create proxy: {e}")

    def test_pypylon_availability(self):
        """Test if pypylon is available through the proxy."""
        print("Testing pypylon availability...")
        
        available = is_pypylon_available()
        if not available:
            pytest.skip("pypylon is not available through any backend")
        
        print("pypylon is available")
        assert available

    def test_proxy_creation(self):
        """Test creating a pypylon proxy."""
        print("Testing proxy creation...")
        
        if not is_pypylon_available():
            pytest.skip("pypylon is not available")
        
        try:
            proxy = PyPylonProxy()
            backend_type = proxy.get_backend_type()
            print(f"Proxy created successfully using backend: {backend_type}")
            assert proxy is not None
            assert backend_type == 'service'  # Should always be service now
        except Exception as e:
            pytest.fail(f"Failed to create proxy: {e}")

    def test_import_functionality(self, proxy):
        """Test basic import functionality."""
        print("Testing import functionality...")
        
        try:
            result = proxy.import_test()
            if result.get('success'):
                print("Import test passed")
                assert result['success'] is True
            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"Import test failed: {error_msg}")
                pytest.fail(f"Import test failed: {error_msg}")
        except Exception as e:
            print(f"Import test exception: {e}")
            pytest.fail(f"Import test exception: {e}")

    def test_device_enumeration(self, proxy):
        """Test device enumeration."""
        print("Testing device enumeration...")
        
        try:
            devices = proxy.enumerate_devices()
            device_count = devices.get('device_count', 0)

            if isinstance(devices, dict) and 'device_count' in devices:
                print(f"Device enumeration successful: {device_count} devices found")

                # Print device details if any found
                if device_count > 0:
                    for i, device in enumerate(devices.get('devices', [])):
                        print(f"  Device {i+1}: {device.get('model_name', 'Unknown')} "
                              f"(Serial: {device.get('serial_number', 'Unknown')})")
                
                assert isinstance(devices, dict)
                assert 'device_count' in devices
                assert isinstance(device_count, int)
                assert device_count >= 0
            else:
                print("Device enumeration returned unexpected format")
                pytest.fail("Device enumeration returned unexpected format")
        except Exception as e:
            print(f"Device enumeration failed: {e}")
            pytest.fail(f"Device enumeration failed: {e}")

    def test_factory_access(self, proxy):
        """Test factory access."""
        print("Testing factory access...")
        
        try:
            factory_info = proxy.get_factory()
            if factory_info:
                print("Factory access successful")
                assert factory_info is not None
            else:
                print("Factory access failed")
                pytest.fail("Factory access failed")
        except Exception as e:
            print(f"Factory access exception: {e}")
            pytest.fail(f"Factory access exception: {e}")

    def test_pixel_formats(self, proxy):
        """Test pixel format access."""
        print("Testing pixel format access...")
        
        try:
            formats = proxy.get_pixel_formats()
            if isinstance(formats, dict):
                print(f"Pixel formats retrieved: {len(formats)} formats")
                for name in list(formats.keys())[:3]:  # Show first 3
                    print(f"  {name}: {formats[name]}")
                
                assert isinstance(formats, dict)
                assert len(formats) > 0  # Should have at least some pixel formats
            else:
                print("Pixel format test returned unexpected format")
                pytest.fail("Pixel format test returned unexpected format")
        except Exception as e:
            print(f"Pixel format test failed: {e}")
            pytest.fail(f"Pixel format test failed: {e}")

    def test_grabbing_strategies(self, proxy):
        """Test grabbing strategy access."""
        print("Testing grabbing strategy access...")
        
        try:
            strategies = proxy.get_grabbing_strategies()
            if isinstance(strategies, dict):
                print(f"Grabbing strategies retrieved: {len(strategies)} strategies")
                assert isinstance(strategies, dict)
                assert len(strategies) > 0  # Should have at least some strategies
            else:
                print("Grabbing strategy test returned unexpected format")
                pytest.fail("Grabbing strategy test returned unexpected format")
        except Exception as e:
            print(f"Grabbing strategy test failed: {e}")
            pytest.fail(f"Grabbing strategy test failed: {e}")

    def test_converter_creation(self, proxy):
        """Test image format converter creation."""
        print("Testing converter creation...")
        
        try:
            result = proxy.create_converter()
            if result.get('converter_created'):
                print("Converter creation successful")
                assert result['converter_created'] is True
            else:
                print("Converter creation failed")
                pytest.fail("Converter creation failed")
        except Exception as e:
            print(f"Converter test failed: {e}")
            pytest.fail(f"Converter test failed: {e}")

    def test_exception_handling(self, proxy):
        """Test exception type availability."""
        print("Testing exception handling...")
        
        try:
            exceptions = proxy.test_exceptions()
            if isinstance(exceptions, dict):
                print(f"Exception test successful: {len(exceptions)} exceptions tested")
                assert isinstance(exceptions, dict)
                assert len(exceptions) > 0  # Should have at least some exceptions
            else:
                print("Exception test returned unexpected format")
                pytest.fail("Exception test returned unexpected format")
        except Exception as e:
            print(f"Exception test failed: {e}")
            pytest.fail(f"Exception test failed: {e}") 