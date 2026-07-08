"""Unified CLI I/O primitives for slipp.

Philosophy: Unix/POSIX style (systemctl, git, apt, ps).
All commands MUST use these primitives (no escape hatches).

Stream routing (Unix convention):
    stdout = data (pipeable to jq, grep, ssh, etc.)
    stderr = diagnostics (progress, hints, errors)

Commands explicitly choose what goes where - no abstraction magic.

Usage:
    from slipp import output

    # Data output (stdout - pipeable)
    output.stdout(f"{user}@{host}")           # Raw pipeable data

    # UI output (stderr - visible but doesn't pollute pipes)
    output.success("Operation completed")
    output.error("Operation failed")
    output.info("FYI message")
    output.warning("Non-critical issue")
    output.task("Major step heading")
    output.hint("Dimmed suggestion")

    # Structured display (stderr)
    output.kv("name", "value")                # key: value pair
    output.kv("name", "value", indent=1)      # indented
    output.bullet("Item text")                # • bullet point
    output.table([{"col": "val"}])            # formatted table

    # Long operations
    with output.spinner("Installing") as update:
        for line in process.stdout:
            update(line.strip()[:60])

    # User input
    name = output.prompt("Enter name", default="default")

Available Primitives:
    Data (stdout): stdout
    UI (stderr): success, error, info, warning, task, hint, blank
    Display (stderr): kv, bullet, table, list_items, suggestions
    Progress (stderr): spinner
    Input: prompt, prompt_password
    Logging: get_log_dir
    Format: set_output_format, get_output_format
    Path: format_path
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator

from rich import box
from rich.console import Console
from rich.table import Table

from slipp.constants import OutputFormat

ICON_BULLET = "•"
ICON_CHECK = "✓"
ICON_REFRESH = "↻"

LAUNCH_FRAMES = [
    "🌍",
    "🌎",
    "🌏",
    "💥",
    "🌍🚀        ",
    "🌎 🚀       ",
    "🌏  🚀      ",
    "    🚀     🌑",
    "     🚀   🌒",
    "      🚀 🌓",
    "       🚀🌔",
    "      🌕🚀",
    "     🌔 🚀",
    "    🌓  🚀",
    "   🌒   🚀",
    "  🌑    🚀",
    "       🚀",
    "      🚀",
    "     🚀",
    "    🚀",
    "   🚀",
    "  🚀",
    " 🚀",
    "🚀",
    "",
    "",
]

_console = Console()
_err_console = Console(stderr=True)

_output_format: OutputFormat = OutputFormat.table


def _print_ui(msg: str, style: str | None = None) -> None:
    """Print UI/diagnostic output to stderr.

    Args:
        msg: Message to print.
        style: Rich style markup (e.g., "bold red"). Defaults to None.
    """
    _err_console.print(msg, style=style)


def _print_data(msg: str) -> None:
    """Print data output to stdout.

    Args:
        msg: Data to print (pipeable).
    """
    _console.print(msg)


def success(msg: str) -> None:
    """✓ Success message (green). Outputs to stderr."""
    _print_ui(f"[green]✓[/green] {msg}")


def error(msg: str) -> None:
    """✗ Error message (red). Outputs to stderr."""
    _err_console.print(f"[red]✗[/red] {msg}")


def info(msg: str) -> None:
    """ℹ Info message (blue). Outputs to stderr."""
    _print_ui(f"[blue]ℹ[/blue] {msg}")


def warning(msg: str) -> None:
    """⚠ Warning message (yellow). Outputs to stderr."""
    _print_ui(f"[yellow]⚠[/yellow] {msg}")


def task(msg: str) -> None:
    """TASK [msg] - Section header (bold). Outputs to stderr."""
    _print_ui(f"\n[bold]TASK[/bold] [{msg}]")


def hint(msg: str) -> None:
    """Hint/tip message (dimmed). Outputs to stderr."""
    _print_ui(f"[dim]{msg}[/dim]")


def blank() -> None:
    """Empty line. Outputs to stderr."""
    _print_ui("")


def stdout(data: str) -> None:
    """Write raw data to stdout. No formatting, pipeable."""
    _print_data(data)


def kv(key: str, value: Any, indent: int = 0) -> None:
    """Write key: value pair to stderr with alignment."""
    prefix = "  " * indent
    _err_console.print(f"{prefix}[dim]{key}:[/dim] {value}")


def bullet(msg: str, indent: int = 0) -> None:
    """Write single bullet item to stderr."""
    prefix = "  " * indent
    _print_ui(f"{prefix}• {msg}")


def table(rows: list[dict[str, Any]]) -> None:
    """Display rows as a table, or as JSON when output format is json.

    Headers are uppercase. Numbers are right-aligned, text is left-aligned.
    Empty list produces no output.

    Args:
        rows: List of dicts where each dict is a row.
    """
    if not rows:
        return

    if _output_format == OutputFormat.json:
        import json

        stdout(json.dumps(rows, indent=2))
        return

    tbl = Table(
        box=box.SIMPLE_HEAD,
        show_header=True,
        show_edge=False,
        padding=(0, 2),
    )

    for key in rows[0].keys():
        value = rows[0][key]
        justify = (
            "right"
            if isinstance(value, (int, float)) or str(value).isdigit()
            else "left"
        )
        tbl.add_column(key.upper(), justify=justify)

    for row in rows:
        tbl.add_row(*[str(v) for v in row.values()])

    _err_console.print(tbl)


def list_items(
    items: list[str],
    numbered: bool = False,
    bullet: str = "•",
    indent: int = 0,
) -> None:
    """Display bulleted or numbered list. Outputs to stderr.

    Args:
        items: List of items to display
        numbered: If True, use 1. 2. 3., else use bullet
        bullet: Bullet character (default: •, ignored if numbered=True)
        indent: Indent level (0, 1, 2, ...), same meaning as kv()/bullet() -
            each level adds 2 spaces, on top of this function's own 2-space
            base indent before the bullet/number.

    Examples:
        >>> output.list_items(["file1.yml", "file2.yml"])
        •  file1.yml
        •  file2.yml

        >>> output.list_items(["Review files", "Test locally"], numbered=True)
        1. Review files
        2. Test locally

        >>> output.list_items(["nested item"], indent=2)
            •  nested item
    """
    indent_str = "  " * indent
    for i, item in enumerate(items, 1):
        prefix = f"{i}." if numbered else bullet
        line = f"{indent_str}  {prefix} {item}"
        _err_console.print(line)


def suggestions(header: str, items: list[str]) -> None:
    """Display actionable command suggestions. Outputs to stderr.

    Used to show users what commands they can run to resolve an issue.

    Args:
        header: Header text (e.g., "Specify target:")
        items: List of suggested commands

    Example:
        >>> output.suggestions("Specify target:", [
        ...     'slipp exec PoC:postgres@production "psql"',
        ...     'slipp exec matrix:postgres "psql"',
        ... ])
        # Output:
        # Specify target:
        #   slipp exec PoC:postgres@production "psql"
        #   slipp exec matrix:postgres "psql"
    """
    _print_ui(f"\n{header}")
    for item in items:
        _print_ui(f"  [dim]{item}[/dim]")


@contextmanager
def spinner(
    message: str, spinner_type: str = "dots"
) -> Generator[Callable[[str], None], None, None]:
    """Spinner with live status updates. Uses stderr.

    Yields an update function to change the status text while spinner runs.
    Caller is responsible for formatting the text passed to update().

    Args:
        message: Base spinner message (e.g., "Installing requirements")
        spinner_type: Rich spinner type (default: "dots", also: "earth", "moon", etc.)

    Yields:
        update: Function to call with status text updates

    Example:
        with output.spinner("Installing") as update:
            for line in process.stdout:
                update(line.strip()[:60])  # Caller formats
    """
    with _err_console.status(f"[bold]{message}[/bold]", spinner=spinner_type) as status:

        def update(text: str) -> None:
            status.update(f"[bold]{message}[/bold] [dim]{text}[/dim]")

        yield update


def success_animation(message: str = "Deploy completed") -> None:
    """Play launch animation then show success message. Uses stderr.

    Animation sequence: Earth spins → rocket launches → travels through space →
    moon passes → rocket returns → exits frame → success message.

    Args:
        message: Success message to show after animation
    """
    import time

    from rich.live import Live
    from rich.text import Text

    with Live(console=_err_console, refresh_per_second=10, transient=True) as live:
        for frame in LAUNCH_FRAMES:
            live.update(Text(frame))
            time.sleep(0.18)

    success(message)


def get_log_dir(base: Path | None = None) -> Path:
    """Get log directory path.

    Centralizes log directory logic for consistency.
    Directory is NOT created - caller should create if needed.

    Args:
        base: Base directory (default: cwd)

    Returns:
        Path to .slipp/logs/ directory
    """
    base = base or Path.cwd()
    return base / ".slipp" / "logs"


def format_path(path: Path | str, project_root: Path | None = None) -> str:
    """Format path for display, relative to project root when possible.

    Shows relative paths for cleaner output that matches config files.
    Falls back to absolute path if not under project root.

    Args:
        path: Absolute or relative path to format
        project_root: Base directory for relative display (default: None)

    Returns:
        Relative path string if within project, absolute otherwise

    Examples:
        >>> format_path(Path("/home/user/project/inventory.yml"), Path("/home/user/project"))
        'inventory.yml'
        >>> format_path(Path("/etc/hosts"), Path("/home/user/project"))
        '/etc/hosts'
    """
    path_obj = Path(path) if isinstance(path, str) else path
    if project_root:
        try:
            return str(path_obj.relative_to(project_root))
        except ValueError:
            pass  # Path not under project_root
    return str(path_obj)


def prompt(question: str, default: str | None = None) -> str:
    """Text input prompt.

    Args:
        question: Question/prompt text
        default: Default value if user presses enter

    Returns:
        User's input string
    """
    import typer

    return typer.prompt(question, default=default)


def prompt_password(question: str = "Password", confirm: bool = False) -> str:
    """Password input with optional confirmation.

    Args:
        question: Password prompt text
        confirm: If True, prompt twice and verify match

    Returns:
        Password string

    Raises:
        PasswordMismatchError: If confirm=True and passwords don't match
    """
    import typer

    from slipp.utils.errors import PasswordMismatchError

    password = typer.prompt(question, hide_input=True)

    if confirm:
        password2 = typer.prompt("Confirm password", hide_input=True)
        if password != password2:
            raise PasswordMismatchError("Passwords do not match")

    return password


def set_output_format(fmt: OutputFormat) -> None:
    """Set global output format (called by CLI callback)."""
    global _output_format
    _output_format = fmt


def get_output_format() -> OutputFormat:
    """Get current output format."""
    return _output_format
