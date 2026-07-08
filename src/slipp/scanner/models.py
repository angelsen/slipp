"""Scanner data models.

Provides Pydantic models for scanner configuration and results.
Mirrors flyctl's scanner types but using Pydantic instead of Go structs.
"""

from pydantic import BaseModel, Field

# Framework identifiers slipp.scanner can actually emit, grouped by language
# family. Single source of truth for anything that needs to branch on
# framework -> family (Caddy site routing, template variable extraction) -
# fastapi/django/nextjs/nuxtjs/etc. have no scanner detector and never match.
PYTHON_FRAMEWORKS = frozenset({"flask", "python"})
NODE_FRAMEWORKS = frozenset({"sveltekit", "node"})


class SourceInfo(BaseModel):
    """Source code information detected by scanner.

    This is the internal model used during scanning, converted to
    DetectedService for the public API.

    Mirrors flyctl's SourceInfo struct but using Pydantic.

    Attributes:
        family: Framework name (e.g., "Flask", "SvelteKit")
        port: Default port number (e.g., 8080, 3000)
        template_url: Dockerfile template URL from Fly.io
        dependencies: List of detected dependencies
    """

    family: str
    port: int
    template_url: str
    dependencies: list[str] = Field(default_factory=list)
