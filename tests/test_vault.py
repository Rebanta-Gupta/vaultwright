from pathlib import Path

import pytest

from vaultwright.core import vault


@pytest.fixture
def fake_vault(tmp_path: Path) -> Path:
    """A miniature vault: 4 notes, one ignored folder, one non-markdown file."""
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "root.md").write_text("root note")

    lectures = tmp_path / "Lectures" / "NE220"
    lectures.mkdir(parents=True)
    (lectures / "week1.md").write_text("week one")
    (lectures / "week2.md").write_text("week two")
    (tmp_path / "Lectures" / "outline.md").write_text("outline")
    (tmp_path / "Lectures" / "slides.pdf").write_bytes(b"not markdown")

    refined = tmp_path / "refined" / "Lectures"
    refined.mkdir(parents=True)
    (refined / "week1.md").write_text("already refined")
    return tmp_path


def test_is_vault(fake_vault: Path, tmp_path: Path) -> None:
    assert vault.is_vault(fake_vault)
    assert not vault.is_vault(tmp_path / "nope")


def test_iter_notes_skips_ignored_and_non_markdown(fake_vault: Path) -> None:
    rel = [n.rel_path.as_posix() for n in vault.iter_notes(fake_vault)]
    assert rel == ["Lectures/NE220/week1.md", "Lectures/NE220/week2.md",
                   "Lectures/outline.md", "root.md"]


def test_note_title(fake_vault: Path) -> None:
    notes = {n.title for n in vault.iter_notes(fake_vault)}
    assert notes == {"week1", "week2", "outline", "root"}


def test_scan_rolls_counts_up(fake_vault: Path) -> None:
    stats = vault.scan(fake_vault)
    assert stats.note_count == 4
    assert stats.own_note_count == 1

    lectures = next(c for c in stats.children if c.name == "Lectures")
    assert lectures.note_count == 3
    assert lectures.own_note_count == 1
    assert [c.name for c in lectures.children] == ["NE220"]
    assert lectures.total_bytes == sum(c.total_bytes for c in lectures.children) + lectures.own_bytes


def test_scan_subdir(fake_vault: Path) -> None:
    stats = vault.scan(fake_vault, Path("Lectures/NE220"))
    assert stats.note_count == 2
    assert stats.children == []


def test_scan_rejects_path_outside_vault(fake_vault: Path) -> None:
    with pytest.raises(ValueError):
        vault.scan(fake_vault, Path(".."))
