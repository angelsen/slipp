"""Projects subcommand group - manage registered projects."""

import typer

from .add import add_command
from .list import list_command
from .remove import remove_command

projects_app = typer.Typer(name="projects", help="Manage registered projects")
projects_app.command(name="add")(add_command)
projects_app.command(name="remove")(remove_command)
projects_app.command(name="list")(list_command)
