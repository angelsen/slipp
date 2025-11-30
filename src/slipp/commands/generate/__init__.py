"""Generate Ansible project files and scaffolding.

Provides commands to generate Dockerfiles, project scaffolding, and
complete Ansible project structures.
"""

import typer

from .dockerfile import dockerfile_command
from .full import full_command
from .scaffold import scaffold_command

generate_app = typer.Typer(name="generate", help="Generate Ansible project files")
generate_app.command(name="dockerfile")(dockerfile_command)
generate_app.command(name="scaffold")(scaffold_command)
generate_app.command(name="full")(full_command)
