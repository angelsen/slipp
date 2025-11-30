"""Template generator for slipp.

Fetches Dockerfile templates from Flyctl's GitHub and renders them
with variables from scanner-detected services.
"""

from slipp.generator.errors import (
    GeneratorError,
    TemplateFetchError,
    TemplateNotFoundError,
    TemplateRenderError,
)
from slipp.generator.generator import GeneratedFile, TemplateGenerator

__all__ = [
    "GeneratorError",
    "TemplateFetchError",
    "TemplateNotFoundError",
    "TemplateRenderError",
    "GeneratedFile",
    "TemplateGenerator",
]
