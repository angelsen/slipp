"""Template fetcher for Flyctl GitHub templates."""

import hashlib
import json
from pathlib import Path

import httpx
from pydantic import BaseModel

from slipp.generator.errors import TemplateFetchError, TemplateNotFoundError


class TemplateFile(BaseModel):
    """Single template file from GitHub."""

    path: str
    content: str
    url: str


class TemplateFetcher:
    """Fetches Dockerfile templates from flyctl GitHub repository.

    Templates are cached locally to avoid repeated downloads.
    """

    GITHUB_REPO = "superfly/flyctl"
    BRANCH = "master"
    BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{BRANCH}"

    def __init__(self, cache_dir: Path | None = None):
        """Initialize fetcher with optional cache directory.

        Args:
            cache_dir: Directory to cache templates (default: ~/.cache/slipp/templates)
        """
        self.cache_dir = cache_dir or Path.home() / ".cache" / "slipp" / "templates"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
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
                )
            raise TemplateFetchError(
                f"HTTP {e.response.status_code} fetching template: {e}"
            )
        except httpx.RequestError as e:
            raise TemplateFetchError(f"Network error fetching template: {e}")

        template = TemplateFile(
            path=Path(template_path).name,
            content=response.text,
            url=url,
        )
        self._save_to_cache(template_path, template)

        return template

    def _get_from_cache(self, template_path: str) -> TemplateFile | None:
        """Load template from cache if available.

        Args:
            template_path: Template path (used for cache key)

        Returns:
            Cached template or None if not found
        """
        cache_key = self._cache_key(template_path)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text())
            return TemplateFile(**data)
        except (json.JSONDecodeError, IOError, ValueError):
            # Cache corrupted, ignore
            return None

    def _save_to_cache(self, template_path: str, template: TemplateFile) -> None:
        """Save template to cache directory.

        Args:
            template_path: Template path (used for cache key)
            template: Template to save
        """
        cache_key = self._cache_key(template_path)
        cache_file = self.cache_dir / f"{cache_key}.json"

        try:
            cache_file.write_text(template.model_dump_json(indent=2))
        except IOError:
            # Cache write failed, not critical
            pass

    def _cache_key(self, template_path: str) -> str:
        """Generate cache key from template path.

        Args:
            template_path: Template path

        Returns:
            Hash-based cache key (safe for filesystem)
        """
        # Use MD5 hash for short, filesystem-safe key
        return hashlib.md5(template_path.encode()).hexdigest()
