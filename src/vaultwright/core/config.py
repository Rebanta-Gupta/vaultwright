"""Settings loading: flag > local file > home file > built-in defaults."""

from __future__ import annotations

import re
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
    """Settings for the kiln command."""

    model: str = "qwen3:8b"
    output: str = "refined"
    temperature: float = 0.3
    layout: str = "sibling"   # "sibling": <note folder>/refined/  |  "mirror": <vault>/refined/<path>
    summary: bool = True
    tags: bool = True
    flashcards: bool = True


@dataclass
class Config:
    """Everything vaultwright reads from a config file."""

    vault: Path | None = None          # a vault, or a folder containing vaults
    default_vault: str | None = None   # which one, when `vault` holds several
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
    default_vault = raw.get("default_vault")
    scan_raw = raw.get("scan", {})
    kiln_raw = raw.get("kiln", {})
    defaults = KilnConfig()

    return Config(
        vault=_expand(vault) if vault else None,
        default_vault=default_vault,
        scan=ScanConfig(ignore=list(scan_raw.get("ignore", []))),
        kiln=KilnConfig(
            model=kiln_raw.get("model", defaults.model),
            output=kiln_raw.get("output", defaults.output),
            temperature=float(kiln_raw.get("temperature", defaults.temperature)),
            layout=str(kiln_raw.get("layout", defaults.layout)),
            summary=bool(kiln_raw.get("summary", defaults.summary)),
            tags=bool(kiln_raw.get("tags", defaults.tags)),
            flashcards=bool(kiln_raw.get("flashcards", defaults.flashcards)),
        ),
        source=path,
    )


def _expand(value: str) -> Path:
    """Allow ~ and environment variables in path settings."""
    import os

    return Path(os.path.expandvars(value)).expanduser()


# Settings `vw config set` is allowed to write. Anything else must be hand-edited.
SETTABLE: dict[str, str] = {
    "vault": "str",
    "default_vault": "str",
    "kiln.model": "str",
    "kiln.output": "str",
    "kiln.layout": "str",
    "kiln.temperature": "float",
    "kiln.summary": "bool",
    "kiln.tags": "bool",
    "kiln.flashcards": "bool",
}


def format_value(dotted_key: str, value: str) -> str:
    """Render a value as TOML, validating it against SETTABLE."""
    kind = SETTABLE.get(dotted_key)
    if kind is None:
        known = ", ".join(sorted(SETTABLE))
        raise ConfigError(f"{dotted_key} is not settable from the command line. Try: {known}")
    if kind == "bool":
        if value.lower() not in ("true", "false"):
            raise ConfigError(f"{dotted_key} must be true or false, not {value!r}")
        return value.lower()
    if kind == "float":
        try:
            return repr(float(value))
        except ValueError as err:
            raise ConfigError(f"{dotted_key} must be a number, not {value!r}") from err
    # Backslashes are escapes in TOML, so Windows paths are stored with forward slashes.
    return '"' + value.replace("\\", "/").replace('"', '\\"') + '"'


def set_value(path: Path, dotted_key: str, value: str) -> Path:
    """Write one setting into a config file, leaving everything else alone.

    Edits the existing line if the key is already there, otherwise inserts it in
    the right section. Comments, ordering and unrelated settings are preserved —
    the file is the user's, and rewriting it wholesale would lose their edits.
    """
    rendered = format_value(dotted_key, value)
    section, _, key = dotted_key.rpartition(".")
    line = f"{key} = {rendered}"

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        body = f"{line}\n" if not section else f"[{section}]\n{line}\n"
        path.write_text(body, encoding="utf-8")
        return path

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    current = ""
    key_pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    section_header = re.compile(r"^\s*\[([^\]]+)\]\s*$")

    for index, existing in enumerate(lines):
        header = section_header.match(existing)
        if header:
            current = header.group(1).strip()
            continue
        if current == section and key_pattern.match(existing):
            lines[index] = line
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return path

    # Not present yet: put it at the end of its section, or start the section.
    if not section:
        insert_at = next(
            (i for i, existing in enumerate(lines) if section_header.match(existing)),
            len(lines),
        )
        # Sit with the other top-level keys, above the blank line before a section.
        while insert_at > 0 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, line)
    else:
        start = next(
            (
                i
                for i, existing in enumerate(lines)
                if (header := section_header.match(existing)) and header.group(1).strip() == section
            ),
            None,
        )
        if start is None:
            if lines and lines[-1].strip():
                lines.append("")
            lines.extend([f"[{section}]", line])
        else:
            end = next(
                (i for i in range(start + 1, len(lines)) if section_header.match(lines[i])),
                len(lines),
            )
            while end > start + 1 and not lines[end - 1].strip():
                end -= 1
            lines.insert(end, line)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
