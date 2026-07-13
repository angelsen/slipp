"""Generate Ansible project files and scaffolding.

Provides commands to generate Dockerfiles, project scaffolding, and
complete Ansible project structures.
"""

import typer

from slipp.commands.generate.dockerfile import dockerfile_command
from slipp.commands.generate.scaffold import scaffold_command
from slipp.commands.launch import launch_command

generate_app = typer.Typer(name="generate", help="Generate Ansible project files")
generate_app.command(name="dockerfile")(dockerfile_command)
generate_app.command(name="scaffold")(scaffold_command)
# Intentional alias: `generate full` is `launch` under the `generate`
# namespace, for discoverability alongside dockerfile/scaffold.
generate_app.command(name="full")(launch_command)
