"""Generate Ansible project files and scaffolding.

Provides commands to generate Dockerfiles, project scaffolding, and
complete Ansible project structures.
"""

import typer

from slipp.commands.generate.dockerfile import dockerfile_command
from slipp.commands.generate.scaffold import scaffold_command

generate_app = typer.Typer(name="generate", help="Generate Ansible project files")
generate_app.command(name="dockerfile")(dockerfile_command)
generate_app.command(name="scaffold")(scaffold_command)
