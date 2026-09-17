"""Command line entry point for vaultwright."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.tree import Tree

from vaultwright.core import vault

app = typer.Typer(help="Tools for working with an Obsidian vault.", no_args_is_help=True)
console = Console()


def human_size(num_bytes: int) -> str:
    """Bytes as a short human-readable string."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def label(stats: vault.FolderStats, *, root_name: str | None = None) -> str:
    """Rich markup for one folder row in the tree."""
    name = root_name or stats.name
    counts = f"{stats.note_count} note{'s' if stats.note_count != 1 else ''}"
    return f"[bold]{name}[/bold]  [dim]({counts}, {human_size(stats.total_bytes)})[/dim]"


def add_children(node: Tree, stats: vault.FolderStats, depth: int, level: int = 1) -> None:
    """Recursively attach child folders, stopping once ``depth`` is reached."""
    if depth and level > depth:
        return
    for child in stats.children:
        branch = node.add(label(child))
        add_children(branch, child, depth, level + 1)


@app.callback()
def main() -> None:
    """Keeps vaultwright a command group even while it has a single command."""


@app.command()
def scan(
    vault_path: Path = typer.Argument(..., help="Path to the Obsidian vault root."),
    subdir: Optional[Path] = typer.Option(
        None, "--subdir", "-s", help="Only scan this folder inside the vault."
    ),
    depth: int = typer.Option(
        0, "--depth", "-d", min=0, help="Limit how many folder levels are shown (0 = all)."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Scan even if the folder has no .obsidian config."
    ),
) -> None:
    """Print the vault's folder tree with note counts."""
    if not vault_path.is_dir():
        console.print(f"[red]No such folder:[/red] {vault_path}")
        raise typer.Exit(1)

    if not vault.is_vault(vault_path) and not force:
        console.print(
            f"[red]Not an Obsidian vault (no .obsidian folder):[/red] {vault_path}\n"
            "[dim]Pass --force to scan it anyway.[/dim]"
        )
        raise typer.Exit(1)

    try:
        stats = vault.scan(vault_path, subdir)
    except (NotADirectoryError, ValueError) as err:
        console.print(f"[red]Cannot scan:[/red] {err}")
        raise typer.Exit(1) from err

    root_name = subdir.as_posix() if subdir else vault_path.resolve().name
    tree = Tree(label(stats, root_name=root_name))
    add_children(tree, stats, depth)
    console.print(tree)

    if stats.note_count == 0:
        console.print("[yellow]No notes found.[/yellow]")


if __name__ == "__main__":
    app()
