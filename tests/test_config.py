from pathlib import Path

import pytest

from vaultwright.core import config as config_module

SAMPLE = """
vault = "{vault}"

[scan]
ignore = ["Cold Emails"]

[kiln]
model = "gemma3:4b"
temperature = 0.1
"""


def write_config(path: Path, vault: str = "/tmp/vault") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SAMPLE.format(vault=vault), encoding="utf-8")
    return path


def test_defaults_when_no_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "HOME_CONFIG", tmp_path / "missing.toml")
    cfg = config_module.load(cwd=tmp_path)
    assert cfg.vault is None
    assert cfg.source is None
    assert cfg.kiln.model == "qwen3:8b"
    assert cfg.scan.ignore == []


def test_local_file_beats_home(tmp_path: Path, monkeypatch) -> None:
    home = write_config(tmp_path / "home" / "config.toml", vault="/home/vault")
    local = write_config(tmp_path / "work" / config_module.LOCAL_FILENAME, vault="/local/vault")
    monkeypatch.setattr(config_module, "HOME_CONFIG", home)

    cfg = config_module.load(cwd=local.parent)
    assert cfg.source == local
    assert cfg.vault == Path("/local/vault")


def test_home_file_used_when_no_local(tmp_path: Path, monkeypatch) -> None:
    home = write_config(tmp_path / "home" / "config.toml", vault="/home/vault")
    monkeypatch.setattr(config_module, "HOME_CONFIG", home)

    cfg = config_module.load(cwd=tmp_path / "elsewhere")
    assert cfg.source == home
    assert cfg.vault == Path("/home/vault")
    assert cfg.kiln.model == "gemma3:4b"
    assert cfg.kiln.temperature == 0.1
    assert cfg.kiln.output == "refined"  # untouched default


def test_explicit_path_wins(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config_module, "HOME_CONFIG", write_config(tmp_path / "h.toml"))
    picked = write_config(tmp_path / "picked.toml", vault="/picked")

    cfg = config_module.load(picked, cwd=tmp_path)
    assert cfg.vault == Path("/picked")


def test_missing_explicit_path_raises(tmp_path: Path) -> None:
    with pytest.raises(config_module.ConfigError):
        config_module.load(tmp_path / "nope.toml")


def test_broken_toml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("vault = [unclosed", encoding="utf-8")
    with pytest.raises(config_module.ConfigError):
        config_module.load(bad)


def test_utf8_bom_is_tolerated(tmp_path: Path) -> None:
    """PowerShell's `Set-Content -Encoding utf8` writes a BOM on Windows."""
    path = tmp_path / "bom.toml"
    path.write_text(SAMPLE.format(vault="/bom/vault"), encoding="utf-8-sig")

    cfg = config_module.load(path)
    assert cfg.vault == Path("/bom/vault")


class TestSetValue:
    """`vw config set` must never disturb the rest of someone's config file."""

    ORIGINAL = """# my settings
vault = "/vaults"

[scan]
ignore = ["Cold Emails"]

[kiln]
model = "qwen3:8b"   # tuned for this laptop
"""

    def config_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "config.toml"
        path.write_text(self.ORIGINAL, encoding="utf-8")
        return path

    def test_replaces_an_existing_top_level_key(self, tmp_path: Path) -> None:
        path = self.config_file(tmp_path)
        config_module.set_value(path, "vault", "/other/vaults")

        text = path.read_text()
        assert 'vault = "/other/vaults"' in text
        assert "# my settings" in text          # comments survive
        assert 'ignore = ["Cold Emails"]' in text
        assert config_module.load(path).vault == Path("/other/vaults")

    def test_adds_a_new_top_level_key_above_the_sections(self, tmp_path: Path) -> None:
        path = self.config_file(tmp_path)
        config_module.set_value(path, "default_vault", "Job_Box")

        lines = path.read_text().splitlines()
        # sits with the other top-level keys, with the blank line still before [scan]
        assert lines.index('default_vault = "Job_Box"') == lines.index('vault = "/vaults"') + 1
        assert lines[lines.index("[scan]") - 1] == ""

        cfg = config_module.load(path)
        assert cfg.default_vault == "Job_Box"
        assert cfg.scan.ignore == ["Cold Emails"]   # sections still parse
        assert cfg.kiln.model == "qwen3:8b"

    def test_replaces_a_key_inside_a_section(self, tmp_path: Path) -> None:
        path = self.config_file(tmp_path)
        config_module.set_value(path, "kiln.model", "gemma3:4b")

        assert config_module.load(path).kiln.model == "gemma3:4b"
        assert "# tuned for this laptop" not in path.read_text()  # that line was replaced
        assert "# my settings" in path.read_text()

    def test_adds_a_key_to_an_existing_section(self, tmp_path: Path) -> None:
        path = self.config_file(tmp_path)
        config_module.set_value(path, "kiln.layout", "mirror")

        cfg = config_module.load(path)
        assert cfg.kiln.layout == "mirror"
        assert cfg.kiln.model == "qwen3:8b"

    def test_creates_a_missing_section(self, tmp_path: Path) -> None:
        path = tmp_path / "bare.toml"
        path.write_text('vault = "/vaults"\n', encoding="utf-8")
        config_module.set_value(path, "kiln.temperature", "0.1")

        assert config_module.load(path).kiln.temperature == 0.1

    def test_creates_the_file_when_there_is_none(self, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "config.toml"
        config_module.set_value(path, "default_vault", "Job_Box")

        assert config_module.load(path).default_vault == "Job_Box"

    def test_windows_paths_are_stored_with_forward_slashes(self, tmp_path: Path) -> None:
        path = self.config_file(tmp_path)
        config_module.set_value(path, "vault", "C:\\Users\\gupta\\Vaults")

        assert config_module.load(path).vault == Path("C:/Users/gupta/Vaults")

    def test_unknown_key_is_refused(self, tmp_path: Path) -> None:
        path = self.config_file(tmp_path)
        with pytest.raises(config_module.ConfigError, match="not settable"):
            config_module.set_value(path, "scan.ignore", "everything")
        assert path.read_text() == self.ORIGINAL   # nothing written

    def test_non_numeric_temperature_is_refused(self, tmp_path: Path) -> None:
        path = self.config_file(tmp_path)
        with pytest.raises(config_module.ConfigError, match="must be a number"):
            config_module.set_value(path, "kiln.temperature", "warm")
