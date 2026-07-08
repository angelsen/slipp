"""Shared Jinja2 environment for template generators."""

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError

from slipp.generator.errors import TemplateGenerationError

TEMPLATE_DIR = Path(__file__).parent / "templates"


def make_env() -> Environment:
    """Create the standard Jinja2 environment for generator templates."""
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )


@lru_cache(maxsize=1)
def get_env() -> Environment:
    """Shared, lazily-built Jinja2 environment for generator templates."""
    return make_env()


def render_template(template_name: str, context: dict[str, Any], *, label: str) -> str:
    """Render a generator template, wrapping Jinja2 errors uniformly.

    Single render path for all generators (compose, inventory, playbook,
    requirements, caddy, roles) so template failures always surface the same
    error type with a consistent message.

    Args:
        template_name: Template filename relative to the templates directory
        context: Template render context
        label: Human-readable name of what's being generated, used in the
            error message (e.g. "docker-compose.yml")

    Returns:
        Rendered template content

    Raises:
        TemplateGenerationError: If rendering fails
    """
    try:
        return get_env().get_template(template_name).render(**context)
    except TemplateError as e:
        raise TemplateGenerationError(f"Failed to render {label}: {e}") from e
