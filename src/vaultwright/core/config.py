"""Settings loading: flag > local file > home file > built-in defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

LOCAL_FILENAME = "vaultwright.toml"
HOME_CONFIG = Path.home() / ".config" / "vaultwright" / "config.toml"


class ConfigError(Exception):
    """Raised when a config file exists but cannot be used."""


@dataclass
class ScanConfig:
    """Settings for the scan command."""

    ignore: list[str] = field(default_factory=list)


@dataclass
class KilnConfig:
    """Settings for the (not yet built) kiln command."""

    model: str = "qwen3:8b"
    output: str = "refined"
    temperature: float = 0.3


@dataclass
class Config:
    """Everything vaultwright reads from a config file."""

    vault: Path | None = None
    scan: ScanConfig = field(default_factory=ScanConfig)
    kiln: KilnConfig = field(default_factory=KilnConfig)
    source: Path | None = None  # which file this came from, for `vw config`


def find_config(explicit: Path | None = None, cwd: Path | None = None) -> Path | None:
    """First config file that exists, in precedence order."""
    if explicit is not None:
        if not explicit.is_file():
            raise ConfigError(f"No config file at {explicit}")
        return explicit

    local = (cwd or Path.cwd()) / LOCAL_FILENAME
    if local.is_file():
        return local
    if HOME_CONFIG.is_file():
        return HOME_CONFIG
    return None


def load(explicit: Path | None = None, cwd: Path | None = None) -> Config:
    """Read the applicable config file, falling back to defaults."""
    path = find_config(explicit, cwd)
    if path is None:
        return Config()

    try:
        # utf-8-sig tolerates a BOM, which Windows editors and PowerShell add.
        raw = tomllib.loads(path.read_text(encoding="utf-8-sig"))
    except (tomllib.TOMLDecodeError, OSError) as err:
        raise ConfigError(f"Could not read {path}: {err}") from err

    vault = raw.get("vault")
    scan_raw = raw.get("scan", {})
    kiln_raw = raw.get("kiln", {})
    defaults = KilnConfig()

    return Config(
        vault=_expand(vault) if vault else None,
        scan=ScanConfig(ignore=list(scan_raw.get("ignore", []))),
        kiln=KilnConfig(
            model=kiln_raw.get("model", defaults.model),
            output=kiln_raw.get("output", defaults.output),
            temperature=float(kiln_raw.get("temperature", defaults.temperature)),
        ),
        source=path,
    )


def _expand(value: str) -> Path:
    """Allow ~ and environment variables in path settings."""
    import os

    return Path(os.path.expandvars(value)).expanduser()
