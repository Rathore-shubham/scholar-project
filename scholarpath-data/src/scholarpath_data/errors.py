"""User-facing error types.

``SourceError`` is raised for problems the user can fix (missing file, unsupported
format, unreadable spreadsheet). The CLI prints its message without a traceback.
"""

from __future__ import annotations


class ScholarPathError(Exception):
    """Base class for expected, user-actionable errors."""


class SourceError(ScholarPathError):
    """The input file is missing, unsupported, unreadable or empty."""


class OutputError(ScholarPathError):
    """The requested output location is unsafe or cannot be written."""
