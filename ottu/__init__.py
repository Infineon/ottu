"""ottu (on-target testing utility) - CLI tool for embedded board testing."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ottu")
except PackageNotFoundError:
    __version__ = "unknown"

__all__ = ["__version__"]
