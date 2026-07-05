"""Template generator for slipp.

Fetches Dockerfile templates from Flyctl's GitHub and renders them
with variables from scanner-detected services.
"""

from slipp.generator.generator import TemplateGenerator

__all__ = [
    "TemplateGenerator",
]
