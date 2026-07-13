"""Template fetcher for Flyctl GitHub templates."""

import hashlib
from pathlib import Path

import httpx
from pydantic import BaseModel

from slipp.generator.errors import TemplateFetchError, TemplateNotFoundError
from slipp.utils.cache import Cache


class TemplateFile(BaseModel):
    """Single template file from GitHub."""

    path: str
    content: str


class TemplateFetcher:
    """Fetches Dockerfile templates from flyctl GitHub repository.

    Templates are cached locally to avoid repeated downloads.
    """

    GITHUB_REPO = "superfly/flyctl"
    BRANCH = "master"
    BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}"
    CACHE_TTL_SECONDS = 7 * 24 * 3600

    def __init__(self):
        """Initialize fetcher, sharing the ~/.cache/slipp/cache.json store."""
        self.cache = Cache()
        self.client = httpx.Client(timeout=30.0)

    def fetch_template(self, template_path: str) -> TemplateFile:
        """Fetch single template file from GitHub.

        Args:
            template_path: Relative path from repo root
                          (e.g., "scanner/templates/python-docker/Dockerfile")

        Returns:
            Template file with content

        Raises:
            TemplateNotFoundError: If template doesn't exist on GitHub
            TemplateFetchError: If network/API error

        Example:
            >>> fetcher = TemplateFetcher()
            >>> template = fetcher.fetch_template("scanner/templates/flask/Dockerfile")
            >>> "FROM python:" in template.content
            True
        """
        cached = self._get_from_cache(template_path)
        if cached:
            return cached

        url = f"{self.BASE_URL}/{template_path}"

        try:
            response = self.client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise TemplateNotFoundError(
                    f"Template not found on GitHub: {template_path}"
                ) from e
            raise TemplateFetchError(
                f"HTTP {e.response.status_code} fetching template: {e}"
            ) from e
        except httpx.RequestError as e:
            raise TemplateFetchError(f"Network error fetching template: {e}") from e

        template = TemplateFile(
            path=Path(template_path).name,
            content=response.text,
        )
        self._save_to_cache(template_path, template)

        return template

    def _get_from_cache(self, template_path: str) -> TemplateFile | None:
        """Load template from cache if available and not expired.

        Args:
            template_path: Template path (used for cache key)

        Returns:
            Cached template or None if not found/expired
        """
        data = self.cache.get(self._cache_key(template_path))
        if data is None:
            return None

        try:
            return TemplateFile(**data)
        except ValueError:
            # Cache corrupted, ignore
            return None

    def _save_to_cache(self, template_path: str, template: TemplateFile) -> None:
        """Save template to cache.

        Args:
            template_path: Template path (used for cache key)
            template: Template to save
        """
        self.cache.set(
            self._cache_key(template_path),
            template.model_dump(),
            ttl_seconds=self.CACHE_TTL_SECONDS,
        )

    def _cache_key(self, template_path: str) -> str:
        """Generate cache key from template path.

        Args:
            template_path: Template path

        Returns:
            Hash-based cache key, namespaced to avoid colliding with other
            entries in the shared ~/.cache/slipp/cache.json store.
        """
        return f"template:{hashlib.md5(template_path.encode()).hexdigest()}"
