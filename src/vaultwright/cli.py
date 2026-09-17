"""Command line entry point for vaultwright."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.tree import Tree

from vaultwright.core import config as config_module
from vaultwright.core import vault

app = typer.Typer(help="Tools for working with an Obsidian vault.", no_args_is_help=True)
console = Console()

CONFIG_OPTION = typer.Option(
    None, "--config", "-c", help="Use this config file instead of the usual search."
)


@app.callback()
def main() -> None:
    """Keeps vaultwright a command group even while it has a single command."""


def load_config(path: Optional[Path]) -> config_module.Config:
    """Load settings, turning a bad config file into a clean CLI error."""
    try:
        return config_module.load(path)
    except config_module.ConfigError as err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(1) from err


def resolve_vault(given: Optional[Path], cfg: config_module.Config) -> Path:
    """The vault to work on: the argument if passed, else the configured one."""
    vault_path = given or cfg.vault
    if vault_path is None:
        console.print(
            "[red]No vault given.[/red] Pass one as an argument, or set "
            f'[bold]vault = "..."[/bold] in {config_module.HOME_CONFIG}.'
        )
        raise typer.Exit(1)
    return vault_path


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


@app.command()
def scan(
    vault_path: Optional[Path] = typer.Argument(
        None, help="Path to the Obsidian vault root. Defaults to the configured vault."
    ),
    subdir: Optional[Path] = typer.Option(
        None, "--subdir", "-s", help="Only scan this folder inside the vault."
    ),
    depth: int = typer.Option(
        0, "--depth", "-d", min=0, help="Limit how many folder levels are shown (0 = all)."
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Scan even if the folder has no .obsidian config."
    ),
    all_folders: bool = typer.Option(
        False, "--all", "-a", help="Ignore the config file's scan.ignore list."
    ),
    config_path: Optional[Path] = CONFIG_OPTION,
) -> None:
    """Print the vault's folder tree with note counts."""
    cfg = load_config(config_path)
    vault_path = resolve_vault(vault_path, cfg)

    if not vault_path.is_dir():
        console.print(f"[red]No such folder:[/red] {vault_path}")
        raise typer.Exit(1)

    if not vault.is_vault(vault_path) and not force:
        console.print(
            f"[red]Not an Obsidian vault (no .obsidian folder):[/red] {vault_path}\n"
            "[dim]Pass --force to scan it anyway.[/dim]"
        )
        raise typer.Exit(1)

    ignore = [] if all_folders else cfg.scan.ignore
    try:
        stats = vault.scan(vault_path, subdir, ignore)
    except (NotADirectoryError, ValueError) as err:
        console.print(f"[red]Cannot scan:[/red] {err}")
        raise typer.Exit(1) from err

    root_name = subdir.as_posix() if subdir else vault_path.resolve().name
    tree = Tree(label(stats, root_name=root_name))
    add_children(tree, stats, depth)
    console.print(tree)

    if ignore:
        console.print(f"[dim]Ignored by config: {', '.join(ignore)}[/dim]")
    if stats.note_count == 0:
        console.print("[yellow]No notes found.[/yellow]")


@app.command()
def config(config_path: Optional[Path] = CONFIG_OPTION) -> None:
    """Show the settings in use and which file they came from."""
    cfg = load_config(config_path)

    source = str(cfg.source) if cfg.source else "none (using built-in defaults)"
    console.print(f"[bold]config file[/bold]  {source}")
    console.print(f"[bold]vault[/bold]        {cfg.vault or '(not set)'}")
    console.print(f"[bold]scan.ignore[/bold]  {cfg.scan.ignore or '(none)'}")
    console.print(
        f"[bold]kiln[/bold]         model={cfg.kiln.model} "
        f"output={cfg.kiln.output} temperature={cfg.kiln.temperature}"
    )
    if cfg.source is None:
        console.print(
            f"\n[dim]Searched: ./{config_module.LOCAL_FILENAME}, "
            f"{config_module.HOME_CONFIG}[/dim]"
        )


if __name__ == "__main__":
    app()
