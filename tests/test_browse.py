"""Navigation logic for the note picker. No terminal involved."""

from pathlib import Path

import pytest

from vaultwright.core import browse


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A vault with nesting, an ignored folder, and notes at several levels."""
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "index.md").write_text("root note")

    (tmp_path / "Lectures" / "NE220").mkdir(parents=True)
    (tmp_path / "Lectures" / "outline.md").write_text("outline")
    (tmp_path / "Lectures" / "NE220" / "w1.md").write_text("week one")
    (tmp_path / "Lectures" / "NE220" / "w2.md").write_text("week two")

    (tmp_path / "Labs").mkdir()
    (tmp_path / "Labs" / "lab2.md").write_text("lab")

    (tmp_path / "Cold Emails").mkdir()
    (tmp_path / "Cold Emails" / "a.md").write_text("email")

    (tmp_path / "Empty").mkdir()          # no notes — should not be offered
    return tmp_path


def labels(browser: browse.Browser) -> list[str]:
    return [e.label for e in browser.entries()]


def test_root_lists_folders_then_notes(vault: Path) -> None:
    browser = browse.Browser(vault)
    assert labels(browser) == [
        "Cold Emails/  (1 note)",
        "Labs/  (1 note)",
        "Lectures/  (3 notes)",
        "index.md",
    ]


def test_no_up_entry_at_the_root(vault: Path) -> None:
    assert all(e.kind != "up" for e in browse.Browser(vault).entries())


def test_empty_folders_are_not_offered(vault: Path) -> None:
    assert not any("Empty" in label for label in labels(browse.Browser(vault)))


def test_ignored_folders_are_not_offered(vault: Path) -> None:
    browser = browse.Browser(vault, ignore=["Cold Emails"])
    assert not any("Cold Emails" in label for label in labels(browser))


def test_entering_a_folder(vault: Path) -> None:
    browser = browse.Browser(vault)
    lectures = next(e for e in browser.entries() if e.kind == "folder" and "Lectures" in e.label)

    assert browser.choose(lectures) is None      # a folder is navigation, not a pick
    assert browser.current == Path("Lectures")
    assert labels(browser) == ["../", "NE220/  (2 notes)", "outline.md"]


def test_folder_counts_include_nested_notes(vault: Path) -> None:
    browser = browse.Browser(vault)
    lectures = next(e for e in browser.entries() if "Lectures" in e.label)
    assert lectures.note_count == 3           # outline.md + two in NE220


def test_choosing_a_note_returns_its_vault_relative_path(vault: Path) -> None:
    browser = browse.Browser(vault, start=Path("Lectures/NE220"))
    note = next(e for e in browser.entries() if e.is_note and e.label == "w1.md")

    assert browser.choose(note) == Path("Lectures/NE220/w1.md")


def test_going_back_up(vault: Path) -> None:
    browser = browse.Browser(vault, start=Path("Lectures/NE220"))
    up = browser.entries()[0]
    assert up.kind == "up"

    browser.choose(up)
    assert browser.current == Path("Lectures")

    browser.choose(browser.entries()[0])
    assert browser.at_root                      # and no further up entry exists
    assert all(e.kind != "up" for e in browser.entries())


def test_breadcrumb(vault: Path) -> None:
    browser = browse.Browser(vault)
    assert browser.breadcrumb == vault.name

    browser.current = Path("Lectures/NE220")
    assert browser.breadcrumb == f"{vault.name}/Lectures/NE220"


def test_vault_with_no_notes(tmp_path: Path) -> None:
    (tmp_path / ".obsidian").mkdir()
    browser = browse.Browser(tmp_path)

    assert browser.notes == []
    assert browser.entries() == []
