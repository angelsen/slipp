"""Unified CLI I/O primitives for slipp.

Philosophy: Unix/POSIX style (systemctl, git, apt, ps).
All commands MUST use these primitives (no escape hatches).

Stream routing (Unix convention):
    stdout = data (pipeable to jq, grep, etc.)
    stderr = diagnostics (progress, hints, errors)

Usage:
    from slipp import output

    # UI output (stderr - visible but doesn't pollute pipes)
    output.success("Operation completed")
    output.error("Operation failed")
    output.info("FYI message")
    output.warning("Non-critical issue")
    output.task("Major step heading")

    # Data output (stdout - pipeable)
    output.table([
        {"service": "backend", "port": 5000},
        {"service": "frontend", "port": 3000},
    ])
    output.text(json.dumps(data))

    # Long operations (simple)
    with output.status("Building image"):
        build_image()

    # Long operations (with live updates)
    with output.spinner("Installing") as update:
        for line in process.stdout:
            update(line.strip()[:60])

    # User input
    if output.confirm("Continue?", default=True):
        proceed()
    name = output.prompt("Enter name", default="default")

    # File logging (for long commands)
    output.setup_file_logging(Path(".slipp/deploy.log"))
    try:
        # ... command work ...
    finally:
        output.cleanup_file_logging()

    # Output format control (global -o flag)
    if output.get_output_format() == OutputFormat.json:
        output.text(json.dumps(data))
    else:
        output.table(data)

Available Primitives:
    UI (stderr): success, error, info, warning, task, hint, blank, table
    Data (stdout): text
    Display (stderr): list_items, group, suggestions
    Progress: status (context manager), spinner (with live updates)
    Input: confirm, prompt
    Logging: setup_file_logging, cleanup_file_logging, get_log_dir
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
ICON_CROSS = "✗"
ICON_ARROW = "→"

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
_file_console: Console | None = None
_log_file: Path | None = None

_output_format: OutputFormat = OutputFormat.table


def _print_ui(msg: str, style: str | None = None) -> None:
    """Print UI/diagnostic output to stderr (and file if enabled)."""
    _err_console.print(msg, style=style)
    if _file_console:
        _file_console.print(msg, style=None, markup=False)


def _print_data(msg: str) -> None:
    """Print data output to stdout (and file if enabled)."""
    _console.print(msg)
    if _file_console:
        _file_console.print(msg, markup=False)


def success(msg: str) -> None:
    """✓ Success message (green). Outputs to stderr."""
    _print_ui(f"[green]✓[/green] {msg}")


def error(msg: str) -> None:
    """✗ Error message (red). Outputs to stderr."""
    _err_console.print(f"[red]✗[/red] {msg}")
    if _file_console:
        _file_console.print(f"✗ {msg}")


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


def text(msg: str) -> None:
    """Plain text data output (stdout). Pipeable."""
    _print_data(msg)


def table(rows: list[dict[str, Any]]) -> None:
    """Unix-style table (stderr).

    Headers are uppercase. Numbers are right-aligned, text is left-aligned.
    Empty list produces no output.
    """
    if not rows:
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
    if _file_console:
        _file_console.print(tbl)


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
        indent: Number of spaces to indent (0, 2, 4, etc.)

    Examples:
        >>> output.list_items(["file1.yml", "file2.yml"])
        •  file1.yml
        •  file2.yml

        >>> output.list_items(["Review files", "Test locally"], numbered=True)
        1. Review files
        2. Test locally

        >>> output.list_items(["nested item"], indent=4)
            •  nested item
    """
    indent_str = " " * indent
    for i, item in enumerate(items, 1):
        prefix = f"{i}." if numbered else bullet
        line = f"{indent_str}  {prefix} {item}"
        _err_console.print(line)
        if _file_console:
            _file_console.print(line)


def group(name: str) -> None:
    """Display indented group header. Outputs to stderr.

    Used for grouping items by category (e.g., project name).

    Args:
        name: Group name to display

    Example:
        >>> output.group("PoC")
        # Output:
        #   PoC:
    """
    _print_ui(f"\n  [bold]{name}:[/bold]")


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
def status(msg: str) -> Generator[None, None, None]:
    """Animated spinner for long operations. Uses stderr.

    Usage:
        with output.status("Building image"):
            build_image()
    """
    with _err_console.status(f"[bold green]{msg}..."):
        yield


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


def confirm(question: str, default: bool = True) -> bool:
    """Yes/no confirmation.

    Args:
        question: Question to ask user
        default: Default answer (True = yes, False = no)

    Returns:
        User's response as boolean
    """
    import typer

    return typer.confirm(question, default=default)


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


def setup_file_logging(log_path: Path) -> None:
    """Enable file logging for verbose operations.

    Creates .slipp/ directory if needed.
    All subsequent output calls write to both terminal and file.

    Args:
        log_path: Path to log file (e.g., .slipp/launch-2025-11-21.log)
    """
    global _file_console, _log_file

    log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = log_path

    file_handle = log_path.open("w")
    _file_console = Console(
        file=file_handle, color_system=None, width=120, markup=False, emoji=False
    )


def cleanup_file_logging() -> None:
    """Close file handle if open."""
    global _file_console, _log_file

    if _file_console and _file_console.file:
        _file_console.file.close()
        _file_console = None
        _log_file = None


def set_output_format(fmt: OutputFormat) -> None:
    """Set global output format (called by CLI callback)."""
    global _output_format
    _output_format = fmt


def get_output_format() -> OutputFormat:
    """Get current output format."""
    return _output_format
