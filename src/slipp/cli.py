"""CLI root application with Typer.

slipp provides fly.io-like operations for self-hosted infrastructure
managed with Ansible. Organize commands into singular actions (slipp run)
and plural management subcommands (slipp runs list).
"""

from typing import Annotated

import typer

from slipp import output
from slipp.commands.bootstrap import bootstrap_app
from slipp.commands.config import config_command
from slipp.commands.deploy import deploy_command
from slipp.commands.exec import exec_command
from slipp.commands.generate import generate_app
from slipp.commands.host import host_command
from slipp.commands.image import image_app
from slipp.commands.images import images_app
from slipp.commands.launch import launch_command
from slipp.commands.logo import logo_command
from slipp.commands.logs import logs_command
from slipp.commands.projects import projects_app
from slipp.commands.ps import ps_command
from slipp.commands.run import RUN_CONTEXT_SETTINGS, run_command
from slipp.commands.runs import runs_app
from slipp.commands.secret import secret_command
from slipp.commands.secrets import secrets_app
from slipp.commands.ssh import ssh_command
from slipp.commands.status import status_command
from slipp.commands.tag import tag_command
from slipp.commands.tags import tags_app
from slipp.constants import OutputFormat
from slipp.services.logo import show_logo

app = typer.Typer(
    name="slipp",
    help="fly.io-like operations CLI for self-hosted infrastructure",
    add_completion=True,
)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", "-V", help="Show version and exit")
    ] = False,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable verbose logging")
    ] = False,
    output_format: Annotated[
        OutputFormat,
        typer.Option("--output", "-o", help="Output format: table (default), json"),
    ] = OutputFormat.table,
) -> None:
    """slipp - Operations CLI for Ansible-managed infrastructure."""
    if version:
        show_logo()
        from slipp import __version__

        output.stdout(f"slipp {__version__}")
        raise typer.Exit()

    output.set_output_format(output_format)

    if verbose:
        output.info("Verbose logging enabled")


app.add_typer(bootstrap_app, name="bootstrap")
app.add_typer(generate_app, name="generate")
app.add_typer(image_app, name="image")
app.add_typer(images_app, name="images")
app.add_typer(projects_app, name="projects")
app.add_typer(runs_app, name="runs")
app.add_typer(secrets_app, name="secrets")
app.add_typer(tags_app, name="tags")

app.command(name="config")(config_command)
app.command(name="deploy")(deploy_command)
app.command(name="exec")(exec_command)
app.command(name="host")(host_command)
app.command(name="launch")(launch_command)
app.command(name="logo")(logo_command)
app.command(name="logs")(logs_command)
app.command(name="ps")(ps_command)
app.command(name="run", context_settings=RUN_CONTEXT_SETTINGS)(run_command)
app.command(name="secret")(secret_command)
app.command(name="ssh")(ssh_command)
app.command(name="status")(status_command)
app.command(name="tag")(tag_command)
