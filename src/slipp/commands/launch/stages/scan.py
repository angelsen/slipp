"""Project scanning stage for launch workflow.

Scans project directories to detect supported frameworks and
services. Reports detected services or exits if none found.
"""

from typing import Any

import typer

from slipp import output
from slipp.scanner import scan


class ProjectScanStage:
    """Scan project directories to detect services and frameworks.

    Iterates through project directories, scans for supported
    frameworks (Python: Flask/FastAPI/Django, Node.js: SvelteKit/
    Express/Next.js), and collects detected services.

    Raises:
        typer.Exit: If no services are detected or scanning fails.
    """

    def execute(self, context: Any) -> None:
        """Scan project directories and populate context.services.

        Args:
            context: Launch context containing project_dirs, output_dir,
                and services list to populate.
        """
        output.task(f"Launching {context.output_dir.name}")

        for project_dir in context.project_dirs:
            output.info(f"Scanning {project_dir}...")

            try:
                service = scan(project_dir)
                if service:
                    context.services.append(service)
            except Exception as e:
                output.error(f"Failed to scan {project_dir}: {e}")
                raise typer.Exit(1)

        if not context.services:
            output.warning("No services detected")
            output.text("Supported frameworks:")
            output.list_items(
                [
                    "Python: Flask, FastAPI, Django",
                    "Node.js: SvelteKit, Express, Next.js",
                ],
                indent=2,
            )
            output.hint("Ensure your project has package.json or pyproject.toml")
            raise typer.Exit(1)

        output.success(f"Detected {len(context.services)} service(s):")
        output.list_items(
            [f"{s.name} ({s.framework})" for s in context.services], indent=2
        )
