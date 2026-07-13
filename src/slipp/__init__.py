"""slipp - fly.io-like operations CLI for self-hosted infrastructure."""

from dotenv import load_dotenv

__version__ = "0.2.0"

load_dotenv()


def main() -> None:
    """Run the slipp CLI application."""
    from slipp import output
    from slipp.cli import app
    from slipp.services.ssh import hint_ssh_log
    from slipp.utils.errors import SlippError

    try:
        app()
    except SlippError as e:
        output.error(str(e))
        # Safety net for commands that let a SlippError (e.g.
        # SudoPasswordError) propagate uncaught rather than checking the
        # SSH result inline.
        hint_ssh_log()
        raise SystemExit(1)
