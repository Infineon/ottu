"""Test initialization and version resolution."""

import importlib
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import ottu


def test_package_version_found():
    """Test standard package version loading."""
    assert isinstance(ottu.__version__, str)


def test_package_version_not_found():
    """Test fallback when package version is not found."""
    with patch("importlib.metadata.version", side_effect=PackageNotFoundError):
        importlib.reload(ottu)
        assert ottu.__version__ == "unknown"
    importlib.reload(ottu)
