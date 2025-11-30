"""Common stages and base classes for launch workflow.

Provides reusable base classes for implementing launch pipeline stages,
including file generation with dry-run support and configuration validation.
"""

from pathlib import Path
from typing import Any

import typer

from slipp import output
from slipp.constants import VALID_PROXIES


class FileGenerationStage:
    """Base class for stages that generate files."""

    def __init__(self, description: str):
        self.description = description

    def generate_content(self, context: Any) -> dict[Path, str]:
        """Generate file content for this stage.

        Args:
            context: Stage execution context containing configuration.

        Returns:
            Dictionary mapping file paths to their content strings.

        Raises:
            NotImplementedError: Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement generate_content()")

    def execute(self, context: Any) -> None:
        """Execute file generation stage.

        Generates files from context, creates parent directories,
        and logs output. Supports dry-run mode for preview.

        Args:
            context: Stage execution context with output_dir, dry_run flags.
        """
        output.info(f"{self.description}...")

        try:
            files = self.generate_content(context)

            for file_path, content in files.items():
                display_path = (
                    str(file_path.relative_to(context.output_dir))
                    if hasattr(context, "output_dir")
                    else str(file_path)
                )

                if context.dry_run:
                    output.hint(f"  Would create: {display_path}")
                else:
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    is_new_file = not file_path.exists()
                    file_path.write_text(content)
                    icon = output.ICON_CHECK if is_new_file else output.ICON_REFRESH
                    output.list_items([display_path], bullet=icon)
                    context.generated_files.append(file_path)

        except Exception as e:
            output.error(f"Failed to {self.description.lower()}: {e}")
            raise typer.Exit(1)


class ValidationStage:
    """Validate proxy choice and set skip_caddy flag."""

    def execute(self, context: Any) -> None:
        """Validate proxy configuration and set caddy skip flag.

        Checks that proxy choice is in VALID_PROXIES list and sets
        skip_caddy flag to True when proxy is "none".

        Args:
            context: Stage execution context with proxy setting.

        Raises:
            typer.Exit: If proxy choice is invalid.
        """
        if context.proxy not in VALID_PROXIES:
            output.error(f"Invalid proxy: {context.proxy}")
            output.info(f"Valid options: {', '.join(VALID_PROXIES)}")
            raise typer.Exit(1)

        context.skip_caddy = context.proxy == "none"
