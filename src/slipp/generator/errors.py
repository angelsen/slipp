"""Custom exceptions for template generator."""

from slipp.utils.errors import SlippError


class GeneratorError(SlippError):
    """Base exception for generator module."""

    pass


class TemplateNotFoundError(GeneratorError):
    """Template doesn't exist on GitHub."""

    pass


class TemplateFetchError(GeneratorError):
    """Network/API error fetching template."""

    pass


class TemplateParseError(GeneratorError):
    """Template URL could not be parsed into a repo path."""

    pass


class TemplateGenerationError(GeneratorError):
    """Template generation failed (playbook/compose)."""

    pass
