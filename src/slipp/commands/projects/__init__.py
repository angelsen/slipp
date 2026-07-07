"""Projects subcommand group - manage registered projects."""

import typer

from slipp.commands.projects.add import add_command
from slipp.commands.projects.list import list_command
from slipp.commands.projects.remove import remove_command

projects_app = typer.Typer(name="projects", help="Manage registered projects")
projects_app.command(name="add")(add_command)
projects_app.command(name="remove")(remove_command)
projects_app.command(name="list")(list_command)
