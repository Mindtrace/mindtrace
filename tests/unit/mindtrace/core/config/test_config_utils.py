import os
import tempfile
from pathlib import Path

from mindtrace.core.utils import load_ini_as_dict


class TestLoadIniAsDict:
    """Test cases for load_ini_as_dict function."""

    def test_load_ini_as_dict_existing_file(self):
        """Test loading from an existing INI file."""
        ini_content = """
[section1]
key1 = value1
key2 = value2

[section2]
key3 = value3
nested_key = nested_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["KEY1"] == "value1"
            assert result["SECTION1"]["KEY2"] == "value2"
            assert result["SECTION2"]["KEY3"] == "value3"
            assert result["SECTION2"]["NESTED_KEY"] == "nested_value"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_missing_file(self):
        """Test that missing file returns empty dict."""
        temp_path = Path("nonexistent_file.ini")
        result = load_ini_as_dict(temp_path)
        assert result == {}

    def test_load_ini_as_dict_empty_file(self):
        """Test loading from an empty INI file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result == {}
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_comments(self):
        """Test loading INI file with comments."""
        ini_content = """
# This is a comment
[section1]
key1 = value1
key2 = value2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["KEY1"] == "value1"
            assert result["SECTION1"]["KEY2"] == "value2"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_whitespace(self):
        """Test loading INI file with whitespace handling."""
        ini_content = """
[ section1 ]
  key1   =   value1   
  key2 = value2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["KEY1"] == "value1"
            assert result["SECTION1"]["KEY2"] == "value2"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_unicode(self):
        """Test loading INI file with unicode characters."""
        ini_content = """
[section1]
unicode_key = 测试
emoji_key = 🚀
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["UNICODE_KEY"] == "测试"
            assert result["SECTION1"]["EMOJI_KEY"] == "🚀"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_boolean_values(self):
        """Test loading INI file with boolean-like values."""
        ini_content = """
[section1]
true_value = true
false_value = false
numeric_true = 1
numeric_false = 0
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["TRUE_VALUE"] == "true"
            assert result["SECTION1"]["FALSE_VALUE"] == "false"
            assert result["SECTION1"]["NUMERIC_TRUE"] == "1"
            assert result["SECTION1"]["NUMERIC_FALSE"] == "0"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_numeric_values(self):
        """Test loading INI file with numeric values."""
        ini_content = """
[section1]
integer_value = 42
float_value = 3.14
negative_value = -10
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["INTEGER_VALUE"] == "42"
            assert result["SECTION1"]["FLOAT_VALUE"] == "3.14"
            assert result["SECTION1"]["NEGATIVE_VALUE"] == "-10"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_quoted_values(self):
        """Test loading INI file with quoted values."""
        ini_content = """
[section1]
quoted_value = "quoted string"
single_quoted = 'single quoted'
mixed_quotes = "mixed 'quotes'"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["QUOTED_VALUE"] == "quoted string"
            assert result["SECTION1"]["SINGLE_QUOTED"] == "single quoted"
            assert result["SECTION1"]["MIXED_QUOTES"] == "mixed 'quotes'"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_multiline_values(self):
        """Test loading INI file with multiline values."""
        ini_content = """
[section1]
multiline_value = This is a \
multiline \
value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            # The exact behavior depends on the INI parser implementation
            # This test verifies that multiline values are handled
            assert "MULTILINE_VALUE" in result["SECTION1"]
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_special_characters(self):
        """Test loading INI file with special characters."""
        ini_content = """
[section1]
special_chars = !@#%^&*()_+-=[]{}|;':",./<>?
url_value = https://example.com/path?param=value&other=123
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["SPECIAL_CHARS"] == "!@#%^&*()_+-=[]{}|;':\",./<>?"
            assert result["SECTION1"]["URL_VALUE"] == "https://example.com/path?param=value&other=123"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_path_object(self):
        """Test loading INI file using Path object."""
        ini_content = """
[section1]
key1 = value1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["KEY1"] == "value1"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_with_tilde_expansion(self):
        """Test that tilde expansion works in INI values."""
        ini_content = """
[section1]
home_path = ~/test/path
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            expected_path = os.path.expanduser("~/test/path")
            assert result["SECTION1"]["HOME_PATH"] == expected_path
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_case_insensitive_sections(self):
        """Test that section names are uppercased."""
        ini_content = """
[Section1]
key1 = value1
[section2]
key2 = value2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert "SECTION1" in result
            assert "SECTION2" in result
            assert result["SECTION1"]["KEY1"] == "value1"
            assert result["SECTION2"]["KEY2"] == "value2"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_case_insensitive_keys(self):
        """Test that keys are uppercased."""
        ini_content = """
[section1]
Key1 = value1
KEY2 = value2
key3 = value3
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(ini_content)
            temp_path = Path(f.name)

        try:
            result = load_ini_as_dict(temp_path)
            assert result["SECTION1"]["KEY1"] == "value1"
            assert result["SECTION1"]["KEY2"] == "value2"
            assert result["SECTION1"]["KEY3"] == "value3"
        finally:
            os.unlink(temp_path)

    def test_load_ini_as_dict_permission_error(self):
        """Test handling of permission errors."""
        # Create a file and then make it unreadable
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write("[section1]\nkey1 = value1\n")
            temp_path = Path(f.name)

        try:
            # Make file unreadable
            os.chmod(temp_path, 0o000)
            # Should return empty dict for permission errors
            result = load_ini_as_dict(temp_path)
            assert result == {}
        finally:
            # Restore permissions and clean up
            os.chmod(temp_path, 0o644)
            os.unlink(temp_path)
