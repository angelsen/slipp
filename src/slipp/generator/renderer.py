"""Go template rendering via the shared Jinja2 environment.

Go templates (fetched from flyctl) are converted to Jinja2 syntax and
rendered through the same environment as every other generator (compose,
inventory, playbook, requirements, caddy, roles) so template failures always
surface as one error type.
"""

import re
from typing import Any

from jinja2 import TemplateError

from slipp.generator.env import get_env
from slipp.generator.errors import TemplateGenerationError


def render_go_template(
    template_content: str, variables: dict[str, Any], *, label: str
) -> str:
    """Convert a Go template to Jinja2 syntax and render it.

    Converts Go template syntax to Jinja2:
    - {{ .Variable }} → {{ Variable }}
    - {{ if .Condition }} → {% if Condition %}
    - {{ else if .Other }} → {% elif Other %}
    - {{ else }} → {% else %}
    - {{ end }} → {% endif %}
    - {{- trim whitespace -}}

    Args:
        template_content: Raw template string (Go syntax)
        variables: Template variables (DetectedService fields)
        label: Human-readable name of what's being rendered, used in the
            error message (e.g. the template path)

    Returns:
        Rendered template string

    Raises:
        TemplateGenerationError: If rendering fails

    Example:
        >>> template = "FROM python:{{ .pythonVersion }}"
        >>> render_go_template(template, {"pythonVersion": "3.12"}, label="Dockerfile")
        'FROM python:3.12'
    """
    try:
        jinja_source = _convert_go_syntax(template_content)
        return get_env().from_string(jinja_source).render(**variables)
    except TemplateError as e:
        raise TemplateGenerationError(f"Failed to render {label}: {e}") from e


def _convert_go_syntax(template: str) -> str:
    """Convert Go template syntax to Jinja2.

    Transformations (leading/trailing `-` whitespace-control markers on
    either side of `{{`/`}}` are preserved on the Jinja `{%`/`%}` side):
    - {{ .Variable }} → {{ Variable }}
    - {{ if .Condition }} → {% if Condition %}
    - {{ else if .Other }} → {% elif Other %}
    - {{ else }} → {% else %}
    - {{ end }} → {% endif %}

    Args:
        template: Go template string

    Returns:
        Jinja2 template string
    """
    result = template

    # {{(-) else if .var (-)}} → {%(-) elif var (-)%}
    result = re.sub(
        r"{{(-?)\s*else\s+if\s+\.(\w+)\s*(-?)}}", r"{%\1 elif \2 \3%}", result
    )

    # {{(-) if .var (-)}} → {%(-) if var (-)%}
    result = re.sub(r"{{(-?)\s*if\s+\.(\w+)\s*(-?)}}", r"{%\1 if \2 \3%}", result)

    # {{(-) else (-)}} → {%(-) else (-)%}
    result = re.sub(r"{{(-?)\s*else\s*(-?)}}", r"{%\1 else \2%}", result)

    # {{(-) end (-)}} → {%(-) endif (-)%}
    result = re.sub(r"{{(-?)\s*end\s*(-?)}}", r"{%\1 endif \2%}", result)

    # {{(-) .Variable (-)}} → {{(-) Variable (-)}}
    result = re.sub(r"{{(-?)\s*\.(\w+)\s*(-?)}}", r"{{\1 \2 \3}}", result)

    return result
