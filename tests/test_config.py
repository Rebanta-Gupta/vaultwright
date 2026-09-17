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
