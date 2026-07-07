"""Shared Jinja2 environment for template generators."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATE_DIR = Path(__file__).parent / "templates"


def relative_to(path: str, base: str) -> str:
    """Jinja2 filter to make path relative to base.

    Args:
        path: Absolute path to make relative
        base: Base path to relativize against

    Returns:
        Relative path string, or the original path if not relative
    """
    try:
        return str(Path(path).relative_to(Path(base)))
    except (ValueError, TypeError):
        return path


def make_env() -> Environment:
    """Create the standard Jinja2 environment for generator templates."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
    env.filters["relative_to"] = relative_to
    return env
