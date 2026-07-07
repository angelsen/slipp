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

        Transformations:
        - {{ .Variable }} → {{ Variable }}
        - {{ if .Condition }} → {% if Condition %}
        - {{ else if .Other }} → {% elif Other %}
        - {{ else }} → {% else %}
        - {{ end }} → {% endif %}
        - {{- whitespace -}} → {%- whitespace -%}

        Args:
            template: Go template string

        Returns:
            Jinja2 template string
        """
        result = template

        # Convert control structures (with whitespace control support)
        result = re.sub(
            r"{{\s*if\s+\.(\w+)\s*-}}", r"{% if \1 -%}", result, flags=re.MULTILINE
        )

        # {{ if .var }} → {% if var %}
        result = re.sub(
            r"{{\s*if\s+\.(\w+)\s*}}", r"{% if \1 %}", result, flags=re.MULTILINE
        )

        # {{ else if .var -}} → {% elif var -%}
        result = re.sub(
            r"{{\s*else\s+if\s+\.(\w+)\s*-}}",
            r"{% elif \1 -%}",
            result,
            flags=re.MULTILINE,
        )

        # {{ else if .var }} → {% elif var %}
        result = re.sub(
            r"{{\s*else\s+if\s+\.(\w+)\s*}}",
            r"{% elif \1 %}",
            result,
            flags=re.MULTILINE,
        )

        # {{ else -}} → {% else -%}
        result = re.sub(r"{{\s*else\s*-}}", r"{% else -%}", result, flags=re.MULTILINE)

        # {{ else }} → {% else %}
        result = re.sub(r"{{\s*else\s*}}", r"{% else %}", result, flags=re.MULTILINE)

        # {{ end -}} → {% endif -%}
        result = re.sub(r"{{\s*end\s*-}}", r"{% endif -%}", result, flags=re.MULTILINE)

        # {{ end }} → {% endif %}
        result = re.sub(r"{{\s*end\s*}}", r"{% endif %}", result, flags=re.MULTILINE)

        # Convert variables (with whitespace control)
        result = re.sub(r"{{\s*\.(\w+)\s*-}}", r"{{ \1 -}}", result, flags=re.MULTILINE)

        # {{ .Variable }} → {{ Variable }}
        result = re.sub(r"{{\s*\.(\w+)\s*}}", r"{{ \1 }}", result, flags=re.MULTILINE)

        # Handle left whitespace control (trim left)
        result = re.sub(r"{{-\s*if\s+", r"{%- if ", result)
        result = re.sub(r"{{-\s*else", r"{%- else", result)
        result = re.sub(r"{{-\s*end", r"{%- endif", result)

        return result
