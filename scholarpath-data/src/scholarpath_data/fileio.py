"""Small, safe file-writing helpers (atomic, and no rewrite when content is unchanged)."""

from __future__ import annotations

import os
from pathlib import Path

from scholarpath_data.errors import OutputError


def atomic_write_bytes(path: Path, data: bytes) -> bool:
    """Write ``data`` to ``path`` via a temp file + rename.

    Returns ``True`` if the file was written, ``False`` if it already had identical
    content (so reruns do not touch unchanged outputs).
    """
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file() and path.read_bytes() == data:
            return False
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except PermissionError as exc:
        raise OutputError(
            f"Cannot write {path}: permission denied. Close the file if it is open in Excel, "
            "or choose another --output-dir."
        ) from exc
    except OSError as exc:
        raise OutputError(f"Cannot write {path}: {exc}") from exc
    return True


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8", newline: str = "\n") -> bool:
    return atomic_write_bytes(path, text.replace("\r\n", "\n").replace("\n", newline).encode(encoding))
