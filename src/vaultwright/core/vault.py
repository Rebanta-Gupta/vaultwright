"""Vault scanning: find notes, count them, describe the tree."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Folders never worth walking into.
IGNORED_DIRS = {".obsidian", ".trash", ".git", "node_modules", "refined"}

ROOT = Path(".")


@dataclass
class Note:
    """One markdown file in the vault."""

    path: Path          # absolute path on disk
    rel_path: Path      # path relative to the vault root
    size: int           # bytes

    @property
    def title(self) -> str:
        """Obsidian uses the filename without its extension as the title."""
        return self.path.stem


@dataclass
class FolderStats:
    """Aggregated counts for one folder in the vault.

    ``note_count`` / ``total_bytes`` include everything nested underneath;
    ``own_note_count`` / ``own_bytes`` count only notes directly in this folder.
    """

    rel_path: Path
    note_count: int = 0
    total_bytes: int = 0
    own_note_count: int = 0
    own_bytes: int = 0
    children: list["FolderStats"] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.rel_path.name or "."


def is_vault(path: Path) -> bool:
    """A real Obsidian vault has a .obsidian config folder at its root."""
    return (path / ".obsidian").is_dir()


def is_ignored(rel_path: Path) -> bool:
    """True if any part of the relative path is a folder we skip."""
    return any(part in IGNORED_DIRS for part in rel_path.parts)


def iter_notes(root: Path, base: Path | None = None) -> list[Note]:
    """Every .md file under ``base`` (default: ``root``), skipping IGNORED_DIRS.

    ``rel_path`` on each note stays relative to ``root``, so callers always
    speak in vault-relative paths even when scanning a single subfolder.
    """
    root = root.resolve()
    base = root if base is None else base.resolve()

    notes: list[Note] = []
    for path in base.rglob("*.md"):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root)
        if is_ignored(rel_path.parent):
            continue
        notes.append(Note(path=path, rel_path=rel_path, size=path.stat().st_size))

    notes.sort(key=lambda n: n.rel_path.as_posix().lower())
    return notes


def scan(root: Path, subdir: Path | None = None) -> FolderStats:
    """Build a FolderStats tree for ``root``, or for one folder inside it."""
    root = root.resolve()
    base = root if subdir is None else (root / subdir).resolve()

    if not base.is_dir():
        raise NotADirectoryError(base)
    if root not in (base, *base.parents):
        raise ValueError(f"{base} is outside the vault {root}")

    base_rel = ROOT if base == root else base.relative_to(root)
    nodes: dict[Path, FolderStats] = {}
    tree = _node_for(base_rel, base_rel, nodes)

    for note in iter_notes(root, base):
        folder_rel = note.rel_path.parent
        if folder_rel == Path(""):
            folder_rel = ROOT
        node = _node_for(folder_rel, base_rel, nodes)
        node.own_note_count += 1
        node.own_bytes += note.size

    _roll_up(tree)
    return tree


def _node_for(
    rel_path: Path, base_rel: Path, nodes: dict[Path, FolderStats]
) -> FolderStats:
    """Fetch or create the node for ``rel_path``, wiring it to its parent."""
    existing = nodes.get(rel_path)
    if existing is not None:
        return existing

    node = FolderStats(rel_path=rel_path)
    nodes[rel_path] = node
    if rel_path != base_rel:
        parent = _node_for(rel_path.parent, base_rel, nodes)
        parent.children.append(node)
    return node


def _roll_up(node: FolderStats) -> FolderStats:
    """Sum each folder's own counts with those of everything below it."""
    node.children.sort(key=lambda c: c.name.lower())
    node.note_count = node.own_note_count
    node.total_bytes = node.own_bytes
    for child in node.children:
        _roll_up(child)
        node.note_count += child.note_count
        node.total_bytes += child.total_bytes
    return node
