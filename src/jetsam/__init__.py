"""jetsam — Git workflow accelerator for humans and agents."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the version declared in pyproject.toml, read from
    # the installed package metadata (hatchling writes it at build time). No
    # hardcoded string to drift out of sync with releases.
    __version__ = version("jetsam-mcp")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0.0.0+unknown"
