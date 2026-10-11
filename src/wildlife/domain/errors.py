"""Errors the app expects and knows how to explain.

Every WildlifeError carries a `user_message`: plain words that the UI can show
as-is. Anything that is NOT a WildlifeError is treated as a bug: it is logged
in full and the user sees a generic "Something went wrong" message.
"""

from __future__ import annotations


class WildlifeError(Exception):
    """Base class for problems we can explain to the user."""

    def __init__(self, user_message: str, *, detail: str | None = None) -> None:
        super().__init__(detail or user_message)
        self.user_message = user_message


class ValidationError(WildlifeError):
    """One or more fields are invalid. `fields` maps field name -> message."""

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("Please check the highlighted fields.", detail=repr(fields))
        self.fields = fields


class NotFoundError(WildlifeError):
    """The thing asked for no longer exists (e.g. deleted in another window)."""


class ConflictError(WildlifeError):
    """The action isn't allowed in the current state (e.g. a place is in use)."""


class DatabaseError(WildlifeError):
    """The database can't be opened, upgraded or trusted."""


class PhotoError(WildlifeError):
    """A photo file is missing, unreadable or unsupported."""


class ImportFileError(WildlifeError):
    """An import file is malformed. `problems` lists row-level issues."""

    def __init__(self, user_message: str, problems: list[str] | None = None) -> None:
        super().__init__(user_message)
        self.problems = problems or []


class BackupError(WildlifeError):
    """A backup or restore failed. Says what was attempted and what is safe."""


class OnlineServiceError(WildlifeError):
    """An optional online service is unavailable."""
