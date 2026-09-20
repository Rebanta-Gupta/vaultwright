"""Walking a vault's folder structure, one level at a time.

All the navigation logic lives here as plain data so it can be tested without a
terminal. The prompt library only draws what ``Browser.entries()`` returns.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from vaultwright.core import vault

UP = ".."


@dataclass(frozen=True)
class Entry:
    """One row in the picker."""

    kind: str          # "up" | "folder" | "note"
    rel_path: Path     # vault-relative; for "up", the folder it leads to
    label: str         # what the user sees
    note_count: int = 0

    @property
    def is_note(self) -> bool:
        return self.kind == "note"


class Browser:
    """Folder-by-folder navigation over the notes in a vault."""

    def __init__(self, root: Path, ignore: Iterable[str] = (), start: Path | None = None):
        self.root = root.resolve()
        self.notes = vault.iter_notes(self.root, ignore=ignore)
        self.current = Path(start) if start else vault.ROOT

    @property
    def at_root(self) -> bool:
        return self.current == vault.ROOT

    @property
    def breadcrumb(self) -> str:
        """Where we are, for the prompt's question line."""
        if self.at_root:
            return self.root.name
        return f"{self.root.name}/{self.current.as_posix()}"

    def entries(self) -> list[Entry]:
        """Rows for the current folder: up, then subfolders, then notes."""
        rows: list[Entry] = []
        if not self.at_root:
            parent = self.current.parent if self.current.parent != Path("") else vault.ROOT
            rows.append(Entry("up", parent, f"{UP}/"))

        rows.extend(self._folders())
        rows.extend(self._notes_here())
        return rows

    def _folders(self) -> list[Entry]:
        """Immediate subfolders that contain at least one note, with totals."""
        counts: dict[str, int] = {}
        for note in self.notes:
            rel = self._relative(note.rel_path)
            if rel is None or len(rel.parts) < 2:
                continue
            counts[rel.parts[0]] = counts.get(rel.parts[0], 0) + 1

        return [
            Entry(
                kind="folder",
                rel_path=self._child(name),
                label=f"{name}/  ({count} note{'s' if count != 1 else ''})",
                note_count=count,
            )
            for name, count in sorted(counts.items(), key=lambda kv: kv[0].lower())
        ]

    def _notes_here(self) -> list[Entry]:
        """Notes sitting directly in the current folder."""
        rows = []
        for note in self.notes:
            rel = self._relative(note.rel_path)
            if rel is None or len(rel.parts) != 1:
                continue
            rows.append(Entry("note", note.rel_path, note.path.name))
        return rows

    def _relative(self, rel_path: Path) -> Path | None:
        """A note's path relative to the current folder, or None if elsewhere."""
        if self.at_root:
            return rel_path
        try:
            return rel_path.relative_to(self.current)
        except ValueError:
            return None

    def _child(self, name: str) -> Path:
        return Path(name) if self.at_root else self.current / name

    def choose(self, entry: Entry) -> Path | None:
        """Act on a row. Returns a note's path if one was picked, else None."""
        if entry.is_note:
            return entry.rel_path
        self.current = entry.rel_path
        return None
