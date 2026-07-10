"""File utilities shared across services."""

from datetime import datetime
from pathlib import Path
from typing import IO


def get_log_dir(base: Path | None = None) -> Path:
    """Return .slipp/logs/ path (does not create the directory)."""
    base = base or Path.cwd()
    return base / ".slipp" / "logs"


def open_log(log_dir: Path | None, prefix: str) -> tuple[Path | None, IO[str] | None]:
    """Open a timestamped log file under log_dir, if log_dir is given."""
    if not log_dir:
        return None, None
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    log_path = log_dir / f"{prefix}-{timestamp}.log"
    return log_path, log_path.open("w")


def atomic_write_text(path: Path, content: str, *, mode: int | None = None) -> None:
    """Write text to path atomically via a temp file in the same directory.

    Args:
        path: Destination file path
        content: Text content to write
        mode: Optional file permission bits to set after write (e.g. 0o600)

    Raises:
        Exception: If write fails (temp file is cleaned up)
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(path)
        if mode is not None:
            path.chmod(mode)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
