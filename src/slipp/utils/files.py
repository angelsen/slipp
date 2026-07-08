"""File utilities shared across services."""

from pathlib import Path


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
