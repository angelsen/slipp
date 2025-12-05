"""VPS bootstrap operations command group.

Provides commands for bootstrapping and configuring VPS infrastructure,
including account setup and development proxy installation.
"""

import typer

from .account import account_command
from .proxy import proxy_command
from .registry import registry_app

bootstrap_app = typer.Typer(name="bootstrap", help="VPS bootstrap operations")
bootstrap_app.command(name="account")(account_command)
bootstrap_app.command(name="proxy")(proxy_command)
bootstrap_app.add_typer(registry_app, name="registry")
