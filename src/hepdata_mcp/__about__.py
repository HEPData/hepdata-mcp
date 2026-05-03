"""Package metadata helpers."""

from importlib.metadata import PackageNotFoundError, version


def package_version() -> str:
    """Return the installed package version, falling back for editable test runs."""
    try:
        return version("hepdata-mcp")
    except PackageNotFoundError:
        return "0.1.0"
