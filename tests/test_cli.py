"""CLI-level tests, mostly around picking the right vault."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vaultwright.cli import app
from vaultwright.core import config as config_module

runner = CliRunner()


def flat(text: str) -> str:
    """Output with wrapping collapsed, so assertions don't depend on width."""
    return " ".join(text.split())


@pytest.fixture
def vaults_folder(tmp_path: Path) -> Path:
    for name in ("Job_Box", "Second_Brain"):
        (tmp_path / name / ".obsidian").mkdir(parents=True)
        (tmp_path / name / "note.md").write_text("a note\n")
    return tmp_path


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_vault_name_resolves_against_the_vaults_folder(vaults_folder: Path, tmp_path: Path) -> None:
    cfg = write_config(tmp_path, f'vault = "{vaults_folder.as_posix()}"\n')
    result = runner.invoke(app, ["scan", "Job_Box", "-c", str(cfg)])

    assert result.exit_code == 0
    assert "Job_Box" in result.stdout


def test_default_vault_is_used_when_no_name_given(vaults_folder: Path, tmp_path: Path) -> None:
    cfg = write_config(
        tmp_path,
        f'vault = "{vaults_folder.as_posix()}"\ndefault_vault = "Second_Brain"\n',
    )
    result = runner.invoke(app, ["scan", "-c", str(cfg)])

    assert result.exit_code == 0
    assert "Second_Brain" in result.stdout


def test_vaults_folder_without_a_default_asks_which(vaults_folder: Path, tmp_path: Path) -> None:
    cfg = write_config(tmp_path, f'vault = "{vaults_folder.as_posix()}"\n')
    result = runner.invoke(app, ["scan", "-c", str(cfg)])

    assert result.exit_code == 1
    assert "holds several vaults" in flat(result.stdout)
    assert "Job_Box" in result.stdout and "Second_Brain" in result.stdout


def test_unknown_vault_name_lists_the_real_ones(vaults_folder: Path, tmp_path: Path) -> None:
    cfg = write_config(tmp_path, f'vault = "{vaults_folder.as_posix()}"\n')
    result = runner.invoke(app, ["scan", "Nope", "-c", str(cfg)])

    assert result.exit_code == 1
    assert "No vault named" in flat(result.stdout)
    assert "Job_Box" in result.stdout


def test_a_single_vault_config_still_works(vaults_folder: Path, tmp_path: Path) -> None:
    cfg = write_config(tmp_path, f'vault = "{(vaults_folder / "Job_Box").as_posix()}"\n')
    result = runner.invoke(app, ["scan", "-c", str(cfg)])

    assert result.exit_code == 0
    assert "Job_Box" in result.stdout


def test_vaults_command_lists_them(vaults_folder: Path, tmp_path: Path) -> None:
    cfg = write_config(
        tmp_path,
        f'vault = "{vaults_folder.as_posix()}"\ndefault_vault = "Job_Box"\n',
    )
    result = runner.invoke(app, ["vaults", "-c", str(cfg)])

    assert result.exit_code == 0
    assert "Job_Box" in result.stdout and "Second_Brain" in result.stdout
    assert "default" in result.stdout


def test_no_vault_configured_at_all(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "HOME_CONFIG", tmp_path / "missing.toml")
    cfg = write_config(tmp_path, "# empty\n")
    result = runner.invoke(app, ["scan", "-c", str(cfg)])

    assert result.exit_code == 1
    assert "No vault given" in flat(result.stdout)


def test_check_runs_on_a_named_vault(vaults_folder: Path, tmp_path: Path) -> None:
    cfg = write_config(tmp_path, f'vault = "{vaults_folder.as_posix()}"\n')
    result = runner.invoke(app, ["check", "Job_Box", "-c", str(cfg)])

    assert result.exit_code == 0
    assert "round trip cleanly" in flat(result.stdout)


def test_config_set_default_vault(vaults_folder: Path, tmp_path: Path) -> None:
    cfg = write_config(tmp_path, f'vault = "{vaults_folder.as_posix()}"\n')
    result = runner.invoke(app, ["config", "set", "default_vault", "Job_Box", "-c", str(cfg)])

    assert result.exit_code == 0
    assert config_module.load(cfg).default_vault == "Job_Box"

    # and it takes effect immediately
    assert runner.invoke(app, ["scan", "-c", str(cfg)]).exit_code == 0


def test_config_set_rejects_a_vault_that_does_not_exist(
    vaults_folder: Path, tmp_path: Path
) -> None:
    cfg = write_config(tmp_path, f'vault = "{vaults_folder.as_posix()}"\n')
    result = runner.invoke(app, ["config", "set", "default_vault", "Nope", "-c", str(cfg)])

    assert result.exit_code == 1
    assert "No vault named" in flat(result.stdout)
    assert config_module.load(cfg).default_vault is None


def test_config_set_rejects_an_unknown_key(tmp_path: Path) -> None:
    cfg = write_config(tmp_path, "# empty\n")
    result = runner.invoke(app, ["config", "set", "nonsense", "1", "-c", str(cfg)])

    assert result.exit_code == 1
    assert "not settable" in flat(result.stdout)


def test_config_show_still_works(tmp_path: Path) -> None:
    cfg = write_config(tmp_path, 'vault = "/vaults"\n')
    result = runner.invoke(app, ["config", "-c", str(cfg)])

    assert result.exit_code == 0
    assert "config file" in flat(result.stdout)
    assert "layout=sibling" in result.stdout


def test_diff_does_not_eat_wikilinks(capsys) -> None:
    """Rich markup would swallow [[links]] and [tags] in the diff."""
    from vaultwright.cli import show_diff

    show_diff("see [[NE 220L/Lab 1]]\n", "see [[NE 220L/Lab 1]] and [tag]\n", "note.md")
    out = capsys.readouterr().out

    assert "[[NE 220L/Lab 1]]" in out
    assert "[tag]" in out


def test_write_is_refused_when_numbers_changed(tmp_path: Path, monkeypatch) -> None:
    """A model that rewrites 50% as 5,0% must not reach the vault silently."""
    from vaultwright.core import refine

    vault = tmp_path / "V"
    (vault / ".obsidian").mkdir(parents=True)
    note = vault / "stats.md"
    note.write_text("Quartiles\n\n" + "word " * 40 + "\n- 50% of values are below Q2\n")

    def fake_refine(client, title, text, **kwargs):
        return refine.RefineResult(
            original=text,
            refined=text.replace("50%", "5,0%"),
            number_warnings=["numbers no longer present: 50"],
        )

    monkeypatch.setattr(refine, "refine_text", fake_refine)
    monkeypatch.setattr(
        "vaultwright.cli.llm.OllamaClient", lambda **kw: type("C", (), {"model": "fake"})()
    )

    cfg = write_config(tmp_path, f'vault = "{vault.as_posix()}"\n')
    result = runner.invoke(app, ["kiln", "stats.md", "-c", str(cfg), "--write"])

    assert result.exit_code == 1
    assert "changed a figure" in flat(result.stdout)
    assert not (vault / "refined").exists()

    ok = runner.invoke(
        app, ["kiln", "stats.md", "-c", str(cfg), "--write", "--allow-number-changes"]
    )
    assert ok.exit_code == 0
    assert (vault / "refined" / "stats.md").exists()


def test_kiln_without_a_note_outside_a_terminal(vaults_folder: Path, tmp_path: Path) -> None:
    """The picker needs a terminal; in a pipe it must say so, not hang."""
    cfg = write_config(
        tmp_path,
        f'vault = "{vaults_folder.as_posix()}"\ndefault_vault = "Job_Box"\n',
    )
    result = runner.invoke(app, ["kiln", "-c", str(cfg)])

    assert result.exit_code == 1
    assert "No note given" in flat(result.stdout)


def test_missing_questionary_gives_a_message_not_a_traceback(
    vaults_folder: Path, monkeypatch, capsys
) -> None:
    """The picker's dependency is imported lazily, so it can be missing at runtime."""
    import builtins

    import typer

    from vaultwright.cli import pick_note

    real_import = builtins.__import__

    def no_questionary(name, *args, **kwargs):
        if name == "questionary":
            raise ImportError("No module named 'questionary'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_questionary)

    with pytest.raises(typer.Exit) as exit_info:
        pick_note(vaults_folder / "Job_Box", [])

    assert exit_info.value.exit_code == 1
    out = flat(capsys.readouterr().out)
    assert "isn't installed" in out
    assert "uv sync" in out
