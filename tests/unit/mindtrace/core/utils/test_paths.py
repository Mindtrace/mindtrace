"""Tests for mindtrace.core.utils.paths module."""



from mindtrace.core.utils.paths import expand_tilde, expand_tilde_str


class TestExpandTildeStr:
    """Tests for expand_tilde_str function."""

    def test_expand_tilde_str_with_tilde(self):
        """Test expand_tilde_str expands ~ to home directory."""
        result = expand_tilde_str("~/test/path")
        assert result.startswith("/")
        assert result.endswith("/test/path")
        assert "~" not in result

    def test_expand_tilde_str_without_tilde(self):
        """Test expand_tilde_str returns unchanged string when no ~."""
        result = expand_tilde_str("/absolute/path")
        assert result == "/absolute/path"

    def test_expand_tilde_str_with_non_string(self):
        """Test expand_tilde_str returns non-string values unchanged."""
        assert expand_tilde_str(123) == 123
        assert expand_tilde_str(None) is None
        assert expand_tilde_str(["list"]) == ["list"]


class TestExpandTilde:
    """Tests for expand_tilde function."""

    def test_expand_tilde_with_string(self):
        """Test expand_tilde with string value."""
        result = expand_tilde("~/test/path")
        assert result.startswith("/")
        assert result.endswith("/test/path")
        assert "~" not in result

    def test_expand_tilde_with_string_no_tilde(self):
        """Test expand_tilde with string without ~."""
        result = expand_tilde("/absolute/path")
        assert result == "/absolute/path"

    def test_expand_tilde_with_dict(self):
        """Test expand_tilde with dictionary."""
        data = {
            "path1": "~/test1",
            "path2": "/absolute/path",
            "nested": {"path3": "~/test2"},
        }
        result = expand_tilde(data)
        assert result["path1"].startswith("/")
        assert result["path1"].endswith("/test1")
        assert result["path2"] == "/absolute/path"
        assert result["nested"]["path3"].startswith("/")
        assert result["nested"]["path3"].endswith("/test2")

    def test_expand_tilde_with_list(self):
        """Test expand_tilde with list."""
        data = ["~/test1", "/absolute/path", "~/test2"]
        result = expand_tilde(data)
        assert isinstance(result, list)
        assert result[0].startswith("/")
        assert result[0].endswith("/test1")
        assert result[1] == "/absolute/path"
        assert result[2].startswith("/")
        assert result[2].endswith("/test2")

    def test_expand_tilde_with_tuple(self):
        """Test expand_tilde with tuple."""
        data = ("~/test1", "/absolute/path", "~/test2")
        result = expand_tilde(data)
        assert isinstance(result, tuple)
        assert result[0].startswith("/")
        assert result[0].endswith("/test1")
        assert result[1] == "/absolute/path"
        assert result[2].startswith("/")
        assert result[2].endswith("/test2")

    def test_expand_tilde_with_set(self):
        """Test expand_tilde with set."""
        data = {"~/test1", "/absolute/path", "~/test2"}
        result = expand_tilde(data)
        assert isinstance(result, set)
        # Check that all paths are expanded
        expanded_paths = list(result)
        for path in expanded_paths:
            if path.endswith("/test1") or path.endswith("/test2"):
                assert path.startswith("/")
                assert "~" not in path
            elif path == "/absolute/path":
                assert path == "/absolute/path"

    def test_expand_tilde_with_nested_structures(self):
        """Test expand_tilde with nested structures."""
        data = {
            "paths": ["~/test1", "~/test2"],
            "config": {
                "dirs": ("~/dir1", "~/dir2"),
                "files": {"/absolute/file1", "~/file2"},
            },
        }
        result = expand_tilde(data)
        assert result["paths"][0].startswith("/")
        assert result["paths"][1].startswith("/")
        assert result["config"]["dirs"][0].startswith("/")
        assert result["config"]["dirs"][1].startswith("/")
        # Check set elements
        files = list(result["config"]["files"])
        for file_path in files:
            if file_path.endswith("/file2"):
                assert file_path.startswith("/")
                assert "~" not in file_path
            elif file_path == "/absolute/file1":
                assert file_path == "/absolute/file1"

    def test_expand_tilde_with_non_string_types(self):
        """Test expand_tilde with non-string types returns unchanged."""
        assert expand_tilde(123) == 123
        assert expand_tilde(None) is None
        assert expand_tilde(True) is True
        assert expand_tilde(3.14) == 3.14

    def test_expand_tilde_with_mixed_types(self):
        """Test expand_tilde with mixed types in structure."""
        data = {
            "string": "~/test",
            "number": 42,
            "list": ["~/path1", 100, "~/path2"],
            "nested": {"key": "~/value", "num": 0},
        }
        result = expand_tilde(data)
        assert result["string"].startswith("/")
        assert result["number"] == 42
        assert result["list"][0].startswith("/")
        assert result["list"][1] == 100
        assert result["list"][2].startswith("/")
        assert result["nested"]["key"].startswith("/")
        assert result["nested"]["num"] == 0
