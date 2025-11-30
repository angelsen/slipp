"""Custom exceptions for template generator."""


class GeneratorError(Exception):
    """Base exception for generator module."""

    pass


class TemplateNotFoundError(GeneratorError):
    """Template doesn't exist on GitHub."""

    pass


class TemplateFetchError(GeneratorError):
    """Network/API error fetching template."""

    pass


class TemplateRenderError(GeneratorError):
    """Template rendering failed."""

    pass


class TemplateGenerationError(GeneratorError):
    """Template generation failed (playbook/compose)."""

    pass
