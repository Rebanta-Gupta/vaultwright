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
        "Search all notes (6)",
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
    assert labels(browser) == [
        "Search all notes (6)", "../", "NE220/  (2 notes)", "outline.md"
    ]


def test_folder_counts_include_nested_notes(vault: Path) -> None:
    browser = browse.Browser(vault)
    lectures = next(e for e in browser.entries() if "Lectures" in e.label)
    assert lectures.note_count == 3           # outline.md + two in NE220


def test_choosing_a_note_returns_its_vault_relative_path(vault: Path) -> None:
    browser = browse.Browser(vault, start=Path("Lectures/NE220"))
    note = next(e for e in browser.entries() if e.is_note and e.label == "w1.md")

    assert browser.choose(note) == Path("Lectures/NE220/w1.md")


def up_row(browser: browse.Browser) -> browse.Entry:
    return next(e for e in browser.entries() if e.kind == "up")


def test_going_back_up(vault: Path) -> None:
    browser = browse.Browser(vault, start=Path("Lectures/NE220"))

    browser.choose(up_row(browser))
    assert browser.current == Path("Lectures")

    browser.choose(up_row(browser))
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


class TestSearch:
    """Drilling down is fine until you already know the note's name."""

    def search_row(self, browser: browse.Browser) -> browse.Entry:
        return next(e for e in browser.entries() if e.kind == "search")

    def test_search_row_is_offered_first(self, vault: Path) -> None:
        rows = browse.Browser(vault).entries()
        assert rows[0].kind == "search"
        assert rows[0].label == "Search all notes (6)"

    def test_search_lists_every_note_by_full_path(self, vault: Path) -> None:
        browser = browse.Browser(vault)
        browser.choose(self.search_row(browser))

        assert browser.searching
        # one flat alphabetical list, so index.md sorts between the folders
        assert labels(browser) == [
            "../  (back to browsing)",
            "Cold Emails/a.md",
            "index.md",
            "Labs/lab2.md",
            "Lectures/NE220/w1.md",
            "Lectures/NE220/w2.md",
            "Lectures/outline.md",
        ]

    def test_search_respects_ignored_folders(self, vault: Path) -> None:
        browser = browse.Browser(vault, ignore=["Cold Emails"])
        browser.choose(self.search_row(browser))

        assert not any("Cold Emails" in label for label in labels(browser))

    def test_choosing_from_search_returns_the_note(self, vault: Path) -> None:
        browser = browse.Browser(vault)
        browser.choose(self.search_row(browser))
        note = next(e for e in browser.entries() if e.label == "Lectures/NE220/w2.md")

        assert browser.choose(note) == Path("Lectures/NE220/w2.md")

    def test_backing_out_returns_to_the_same_folder(self, vault: Path) -> None:
        browser = browse.Browser(vault, start=Path("Lectures"))
        browser.choose(self.search_row(browser))
        browser.choose(browser.entries()[0])        # "../ (back to browsing)"

        assert not browser.searching
        assert browser.current == Path("Lectures")  # exactly where we left off

    def test_breadcrumb_says_what_mode_it_is_in(self, vault: Path) -> None:
        browser = browse.Browser(vault)
        browser.choose(self.search_row(browser))
        assert browser.breadcrumb == f"{vault.name} — all notes"

    def test_no_search_row_in_an_empty_vault(self, tmp_path: Path) -> None:
        (tmp_path / ".obsidian").mkdir()
        assert browse.Browser(tmp_path).entries() == []
