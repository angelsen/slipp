"""Unified CLI I/O primitives for slipp.

stdout = data (pipeable), stderr = diagnostics (progress, hints, errors).
All commands MUST use these primitives.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Generator, TypeVar

from rich import box
from rich.console import Console
from rich.table import Table

from slipp.constants import OutputFormat

T = TypeVar("T")

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
    """Print to stderr."""
    _err_console.print(msg, style=style)


def _print_data(msg: str) -> None:
    """Print to stdout."""
    _console.print(msg)


def success(msg: str) -> None:
    """✓ green on stderr."""
    _print_ui(f"[green]✓[/green] {msg}")


def error(msg: str) -> None:
    """✗ red on stderr."""
    _err_console.print(f"[red]✗[/red] {msg}")


def info(msg: str) -> None:
    """ℹ blue on stderr."""
    _print_ui(f"[blue]ℹ[/blue] {msg}")


def warning(msg: str) -> None:
    """⚠ yellow on stderr."""
    _print_ui(f"[yellow]⚠[/yellow] {msg}")


def task(msg: str) -> None:
    """TASK [msg] section header on stderr."""
    _print_ui(f"\n[bold]TASK[/bold] [{msg}]")


def hint(msg: str) -> None:
    """Dimmed hint on stderr."""
    _print_ui(f"[dim]{msg}[/dim]")


def blank() -> None:
    """Empty line on stderr."""
    _print_ui("")


def stdout(data: str) -> None:
    """Raw data to stdout (pipeable)."""
    _print_data(data)


def kv(key: str, value: Any, indent: int = 0) -> None:
    """key: value pair on stderr."""
    prefix = "  " * indent
    _err_console.print(f"{prefix}[dim]{key}:[/dim] {value}")


def bullet(msg: str, indent: int = 0) -> None:
    """Single bullet item on stderr."""
    prefix = "  " * indent
    _print_ui(f"{prefix}{ICON_BULLET} {msg}")


def table(rows: list[dict[str, Any]]) -> None:
    """Display rows as a table, or as JSON when output format is json.

    Headers are uppercase. Numbers are right-aligned, text is left-aligned.
    Empty list produces no output.
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
    bullet: str = ICON_BULLET,
    indent: int = 0,
) -> None:
    """Display bulleted or numbered list on stderr.

    Each indent level adds 2 spaces, on top of the 2-space base indent
    before the bullet/number.
    """
    indent_str = "  " * indent
    for i, item in enumerate(items, 1):
        prefix = f"{i}." if numbered else bullet
        line = f"{indent_str}  {prefix} {item}"
        _err_console.print(line)


def suggestions(header: str, items: list[str]) -> None:
    """Display actionable command suggestions on stderr."""
    _print_ui(f"\n{header}")
    for item in items:
        _print_ui(f"  [dim]{item}[/dim]")


@contextmanager
def spinner(
    message: str, spinner_type: str = "dots"
) -> Generator[Callable[[str], None], None, None]:
    """Spinner with live status updates on stderr.

    Yields an update function to change the status text while spinner runs.
    """
    with _err_console.status(f"[bold]{message}[/bold]", spinner=spinner_type) as status:

        def update(text: str) -> None:
            status.update(f"[bold]{message}[/bold] [dim]{text}[/dim]")

        yield update


def success_animation(message: str = "Deploy completed") -> None:
    """Play launch animation then show success message on stderr."""
    import time

    from rich.live import Live
    from rich.text import Text

    with Live(console=_err_console, refresh_per_second=10, transient=True) as live:
        for frame in LAUNCH_FRAMES:
            live.update(Text(frame))
            time.sleep(0.18)

    success(message)


def format_path(path: Path | str, project_root: Path | None = None) -> str:
    """Format path relative to project root when possible, absolute otherwise."""
    path_obj = Path(path) if isinstance(path, str) else path
    if project_root:
        try:
            return str(path_obj.relative_to(project_root))
        except ValueError:
            pass
    return str(path_obj)


def prompt(question: str, default: Any = None, *, type: type | None = None) -> Any:
    """Input prompt via typer (prompt text on stderr, stdout stays data).

    The value type is `type` if given, else inferred from `default`
    (typer's behavior) -- so int prompts work with either.
    """
    import typer

    return typer.prompt(question, default=default, type=type, err=True)


def pick(
    items: list[T], rows: list[dict[str, Any]], label: str, *, default: int = 1
) -> T:
    """Show a numbered table and prompt for a 1-based selection.

    Out-of-range choices clamp to the nearest valid index rather than erroring.
    """
    task(label)
    table(rows)
    choice = prompt("Select", type=int, default=default)
    return items[max(1, min(choice, len(items))) - 1]


def confirm(question: str, *, default: bool = False) -> bool:
    """Yes/no prompt via typer (prompt text on stderr, stdout stays data)."""
    import typer

    return typer.confirm(question, default=default, err=True)


def prompt_password(question: str = "Password", confirm: bool = False) -> str:
    """Password input with optional confirmation.

    Prompt text goes to stderr so a prompt mid-command never corrupts
    piped stdout. Raises PasswordMismatchError if confirm=True and
    passwords don't match.
    """
    import typer

    from slipp.utils.errors import PasswordMismatchError

    password = typer.prompt(question, hide_input=True, err=True)

    if confirm:
        password2 = typer.prompt("Confirm password", hide_input=True, err=True)
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
