"""VPS bootstrap operations command group.

Provides commands for bootstrapping and configuring VPS infrastructure,
including account setup and development proxy installation.
"""

import typer

from slipp.commands.bootstrap.account import account_command
from slipp.commands.bootstrap.proxy import proxy_command
from slipp.commands.bootstrap.registry import registry_app

bootstrap_app = typer.Typer(name="bootstrap", help="VPS bootstrap operations")
bootstrap_app.command(name="account")(account_command)
bootstrap_app.command(name="proxy")(proxy_command)
bootstrap_app.add_typer(registry_app, name="registry")
