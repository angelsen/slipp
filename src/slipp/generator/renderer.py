"""Go template renderer using Jinja2."""

import re
from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateError

from slipp.generator.errors import TemplateRenderError


class GoTemplateRenderer:
    """Renders Go templates using Jinja2 adapter.

    Converts Go template syntax to Jinja2:
    - {{ .Variable }} → {{ Variable }}
    - {{ if .Condition }} → {% if Condition %}
    - {{ else if .Other }} → {% elif Other %}
    - {{ else }} → {% else %}
    - {{ end }} → {% endif %}
    - {{- trim whitespace -}}

    Example:
        >>> renderer = GoTemplateRenderer()
        >>> template = "FROM python:{{ .pythonVersion }}"
        >>> renderer.render(template, {"pythonVersion": "3.12"})
        'FROM python:3.12'
    """

    def __init__(self):
        """Initialize Jinja2 environment."""
        self.env = Environment(
            variable_start_string="{{",
            variable_end_string="}}",
            block_start_string="{%",
            block_end_string="%}",
            comment_start_string="{#",
            comment_end_string="#}",
            trim_blocks=True,  # Remove newline after block
            lstrip_blocks=True,  # Remove leading whitespace before block
            undefined=StrictUndefined,
        )

    def render(self, template_content: str, variables: dict[str, Any]) -> str:
        """Render template with variables.

        Args:
            template_content: Raw template string (Go syntax)
            variables: Template variables (DetectedService fields)

        Returns:
            Rendered template string

        Raises:
            TemplateRenderError: If rendering fails

        Example:
            >>> renderer = GoTemplateRenderer()
            >>> template = '''
            ... {% if flask %}
            ... RUN pip install flask
            ... {% endif %}
            ... '''
            >>> result = renderer.render(template, {"flask": True})
            >>> "pip install flask" in result
            True
        """
        try:
            jinja_template = self._convert_go_syntax(template_content)
            template = self.env.from_string(jinja_template)
            return template.render(**variables)

        except TemplateError as e:
            raise TemplateRenderError(f"Template rendering failed: {e}")
        except Exception as e:
            raise TemplateRenderError(f"Unexpected error during rendering: {e}")

    def _convert_go_syntax(self, template: str) -> str:
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
