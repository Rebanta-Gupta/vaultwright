"""Command line entry point for vaultwright."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.tree import Tree

from vaultwright.core import config as config_module
from vaultwright.core import llm, parse, refine, vault

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
    """Work out which vault to act on.

    Accepts a vault path, a bare vault name (resolved against a configured
    folder of vaults), or nothing at all — in which case the configured vault
    is used, or the configured default inside a folder of vaults.
    """
    configured = cfg.vault

    # A bare name like "Job_Box", resolved against the configured vaults folder.
    if given is not None and not given.exists() and configured is not None:
        candidate = configured / given
        if vault.is_vault(candidate):
            return candidate
        if configured.is_dir() and not vault.is_vault(configured):
            _no_such_vault(given, configured)

    chosen = given or configured
    if chosen is None:
        console.print(
            "[red]No vault given.[/red] Pass one as an argument, or set "
            f'[bold]vault = "..."[/bold] in {config_module.HOME_CONFIG}.'
        )
        raise typer.Exit(1)

    # The configured path holds several vaults rather than being one.
    if vault.is_vault_root(chosen):
        if cfg.default_vault:
            candidate = chosen / cfg.default_vault
            if vault.is_vault(candidate):
                return candidate
            _no_such_vault(Path(cfg.default_vault), chosen)
        names = ", ".join(v.name for v in vault.find_vaults(chosen))
        console.print(
            f"[red]{chosen} holds several vaults, so it isn't one itself.[/red]\n"
            f"[dim]Available: {names}[/dim]\n"
            '[dim]Name one (vw scan <name>), or set default_vault = "..." '
            "in your config.[/dim]"
        )
        raise typer.Exit(1)

    return chosen


def _no_such_vault(name: Path, root: Path) -> None:
    """Complain about an unknown vault name, listing the real ones."""
    names = ", ".join(v.name for v in vault.find_vaults(root)) or "none found"
    console.print(f"[red]No vault named[/red] {name} [red]in[/red] {root}")
    console.print(f"[dim]Available: {names}[/dim]")
    raise typer.Exit(1)


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
        None, help="Vault path or name. Defaults to the configured vault."
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
def vaults(config_path: Optional[Path] = CONFIG_OPTION) -> None:
    """List the vaults vaultwright can see."""
    cfg = load_config(config_path)
    if cfg.vault is None:
        console.print(f"[red]No vault configured in[/red] {config_module.HOME_CONFIG}")
        raise typer.Exit(1)

    if vault.is_vault(cfg.vault):
        console.print(f"[bold]{cfg.vault.name}[/bold]  [dim]{cfg.vault}[/dim]")
        return

    found = vault.find_vaults(cfg.vault)
    if not found:
        console.print(f"[yellow]No vaults found in[/yellow] {cfg.vault}")
        raise typer.Exit(1)

    console.print(f"[dim]In {cfg.vault}:[/dim]")
    for item in found:
        count = len(vault.iter_notes(item, ignore=cfg.scan.ignore))
        marker = "[green]*[/green]" if item.name == cfg.default_vault else " "
        plural = "" if count == 1 else "s"
        console.print(f" {marker} [bold]{item.name}[/bold]  [dim]({count} note{plural})[/dim]")
    if cfg.default_vault:
        console.print("\n[dim]* default[/dim]")


config_app = typer.Typer(help="Show or change settings.", invoke_without_command=True)
app.add_typer(config_app, name="config")


@config_app.callback(invoke_without_command=True)
def config(
    ctx: typer.Context, config_path: Optional[Path] = CONFIG_OPTION
) -> None:
    """Show the settings in use and which file they came from."""
    if ctx.invoked_subcommand is not None:
        return
    cfg = load_config(config_path)

    source = str(cfg.source) if cfg.source else "none (using built-in defaults)"
    console.print(f"[bold]config file[/bold]  {source}")
    console.print(f"[bold]vault[/bold]        {cfg.vault or '(not set)'}")
    console.print(f"[bold]scan.ignore[/bold]  {cfg.scan.ignore or '(none)'}")
    console.print(
        f"[bold]kiln[/bold]         model={cfg.kiln.model} "
        f"output={cfg.kiln.output} layout={cfg.kiln.layout} "
        f"temperature={cfg.kiln.temperature}"
    )
    if cfg.source is None:
        console.print(
            f"\n[dim]Searched: ./{config_module.LOCAL_FILENAME}, "
            f"{config_module.HOME_CONFIG}[/dim]"
        )


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Setting to change, e.g. default_vault or kiln.model."),
    value: str = typer.Argument(..., help="The new value."),
    config_path: Optional[Path] = CONFIG_OPTION,
) -> None:
    """Change one setting, leaving the rest of the file untouched.

    Writes to the config file already in use, or creates the one in your home
    folder if there isn't one yet.
    """
    cfg = load_config(config_path)
    target = config_path or cfg.source or config_module.HOME_CONFIG

    # A wrong vault name here would only show up later, so check it now.
    if key == "default_vault" and cfg.vault is not None:
        if not vault.is_vault(cfg.vault / value):
            _no_such_vault(Path(value), cfg.vault)

    try:
        written = config_module.set_value(target, key, value)
    except (config_module.ConfigError, OSError) as err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(1) from err

    console.print(f"[green]{key}[/green] = {value}   [dim]({written})[/dim]")


@app.command()
def check(
    vault_path: Optional[Path] = typer.Argument(
        None, help="Vault path or name. Defaults to the configured vault."
    ),
    subdir: Optional[Path] = typer.Option(
        None, "--subdir", "-s", help="Only check this folder inside the vault."
    ),
    all_folders: bool = typer.Option(
        False, "--all", "-a", help="Ignore the config file's scan.ignore list."
    ),
    show: int = typer.Option(5, "--show", min=0, help="How many failing notes to list."),
    config_path: Optional[Path] = CONFIG_OPTION,
) -> None:
    """Verify every note survives protect/restore unchanged.

    Nothing is written. This is the safety check kiln depends on: if a note
    fails here, refining it could silently mangle links, math or code.
    """
    cfg = load_config(config_path)
    vault_path = resolve_vault(vault_path, cfg)

    if not vault_path.is_dir():
        console.print(f"[red]No such folder:[/red] {vault_path}")
        raise typer.Exit(1)

    ignore = [] if all_folders else cfg.scan.ignore
    base = vault_path / subdir if subdir else None
    notes = vault.iter_notes(vault_path, base, ignore)

    failures: list[tuple[Path, str]] = []
    unreadable: list[tuple[Path, str]] = []

    for note in notes:
        try:
            text = parse.read_note(note.path)
        except (OSError, UnicodeDecodeError) as err:
            unreadable.append((note.rel_path, str(err)))
            continue
        if parse.round_trip(text) != text:
            failures.append((note.rel_path, "round trip changed the note"))

    console.print(f"Checked [bold]{len(notes)}[/bold] notes in {vault_path}")

    for label_text, rows, colour in (
        ("could not read", unreadable, "yellow"),
        ("round trip failed", failures, "red"),
    ):
        if not rows:
            continue
        console.print(f"[{colour}]{len(rows)} {label_text}[/{colour}]")
        for rel_path, reason in rows[:show]:
            console.print(f"  [dim]{rel_path.as_posix()}[/dim] — {reason}")
        if len(rows) > show:
            console.print(f"  [dim]… and {len(rows) - show} more[/dim]")

    if failures or unreadable:
        raise typer.Exit(1)
    console.print("[green]All notes round trip cleanly.[/green]")


def show_diff(before: str, after: str, name: str) -> None:
    """Print a unified diff, coloured."""
    import difflib

    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(),
        fromfile=f"{name} (original)", tofile=f"{name} (refined)", lineterm="",
    )
    # markup=False matters: note text is full of [[wikilinks]] and [tags], which
    # rich would otherwise eat as markup.
    for line in lines:
        if line.startswith("+") and not line.startswith("+++"):
            style = "green"
        elif line.startswith("-") and not line.startswith("---"):
            style = "red"
        elif line.startswith("@@"):
            style = "cyan"
        else:
            style = "dim"
        console.print(line, style=style, highlight=False, markup=False)


@app.command()
def kiln(
    note: Path = typer.Argument(..., help="The note to refine, inside the vault."),
    vault_path: Optional[Path] = typer.Option(
        None, "--vault", "-v", help="Vault path or name. Defaults to the configured vault."
    ),
    write: bool = typer.Option(
        False, "--write", "-w", help="Write the result. Without this, nothing is saved."
    ),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Override the model."),
    allow_number_changes: bool = typer.Option(
        False,
        "--allow-number-changes",
        help="Write even if the model altered a figure. Check the diff first.",
    ),
    temperature: Optional[float] = typer.Option(None, "--temperature", "-t"),
    config_path: Optional[Path] = CONFIG_OPTION,
) -> None:
    """Refine one note with a local Ollama model.

    Dry run by default: it prints a diff and writes nothing. With --write the
    result goes to <vault>/<output>/<same path>. The original is never touched.
    """
    cfg = load_config(config_path)
    vault_path = resolve_vault(vault_path, cfg)

    source = note if note.is_absolute() else vault_path / note
    if not source.is_file():
        console.print(f"[red]No such note:[/red] {source}")
        raise typer.Exit(1)

    try:
        rel_path = source.resolve().relative_to(vault_path.resolve())
    except ValueError as err:
        console.print(f"[red]{source} is outside the vault {vault_path}[/red]")
        raise typer.Exit(1) from err

    text = parse.read_note(source)
    try:
        client = llm.OllamaClient(
            model=model or cfg.kiln.model,
            temperature=cfg.kiln.temperature if temperature is None else temperature,
        )
    except llm.LLMError as err:
        console.print(f"[red]{err}[/red]")
        raise typer.Exit(1) from err

    console.print(f"[dim]Refining {rel_path.as_posix()} with {client.model}…[/dim]")
    try:
        result = refine.refine_text(
            client,
            source.stem,
            text,
            summary=cfg.kiln.summary,
            tags=cfg.kiln.tags,
            flashcards=cfg.kiln.flashcards,
        )
    except (llm.LLMError, refine.RefineRejected) as err:
        console.print(f"[red]Not refined:[/red] {err}")
        raise typer.Exit(1) from err

    if not result.changed:
        console.print("[yellow]The model returned the note unchanged.[/yellow]")

    show_diff(result.original, result.refined, rel_path.as_posix())

    if result.shortened:
        console.print(
            "[dim]Short note — typo fixes only, no summary or flashcards.[/dim]"
        )

    for problem in result.number_warnings:
        console.print(f"[red]Numbers changed:[/red] {problem}", markup=True, highlight=False)

    summary = (
        f"{result.protected_count} protected fragment(s) preserved · "
        f"{len(result.added)} addition(s) · {result.flashcard_count} flashcard(s) · "
        f"tags: {', '.join(result.tags) or 'none'}"
    )
    console.print("")
    console.print(summary, style="dim", highlight=False, markup=False)
    if result.added:
        console.print("[dim]Additions are wrapped in a > [!ai] callout.[/dim]")

    if not write:
        console.print("[dim]Dry run — nothing written. Pass --write to save.[/dim]")
        return

    if result.number_warnings and not allow_number_changes:
        console.print(
            "[red]Not written:[/red] the model changed a figure. Study notes are "
            "mostly numbers, so this is refused by default.\n"
            "[dim]Re-run to get a different answer, or pass "
            "--allow-number-changes if the change is right.[/dim]"
        )
        raise typer.Exit(1)

    try:
        target = refine.refined_path(
            vault_path, rel_path, cfg.kiln.output, cfg.kiln.layout
        )
    except ValueError as err:
        console.print(f"[red]Refusing to write:[/red] {err}")
        raise typer.Exit(1) from err

    parse.write_note(target, result.refined)
    console.print(f"[green]Written:[/green] {target}")


if __name__ == "__main__":
    app()
