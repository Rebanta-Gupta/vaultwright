"""Lossless note parsing.

The model only ever sees prose. Anything Obsidian or Markdown treats as
machinery — frontmatter, code fences, math, wikilinks, embeds, link targets,
comments — is swapped for an opaque placeholder first and put back afterwards.

The guarantee this module exists to provide: for any note,
``restore(protect(text)) == text``, byte for byte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PLACEHOLDER_TEMPLATE = "\u27e6VW{index:04d}\u27e7"  # ⟦VW0001⟧
PLACEHOLDER_RE = re.compile(r"\u27e6VW\d{4}\u27e7")

# Order matters: the first pattern that matches at a position wins, so
# block-level constructs must come before the inline ones they can contain.
PATTERNS: list[tuple[str, str]] = [
    # A note that already contains placeholder-shaped text: protect it first so
    # restore() can never mistake the note's own content for one of ours.
    ("literal", r"\u27e6VW\d{4}\u27e7"),
    # ```lang … ``` or ~~~ … ~~~
    ("fence", r"(?ms:^[ \t]*(?P<marker>```|~~~).*?^[ \t]*(?P=marker)[ \t]*$)"),
    # %% Obsidian comment %%
    ("comment", r"(?s:%%.*?%%)"),
    # <!-- HTML comment --> — deliberately hidden content. A model will happily
    # "restore" it, which silently un-hides something the author chose to hide.
    ("html_comment", r"(?s:<!--.*?-->)"),
    # --- *** ___ horizontal rules: structure the author put there on purpose
    ("rule", r"(?m:^[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*$)"),
    # $$ display math $$
    ("math_block", r"(?s:\$\$.*?\$\$)"),
    # ![[embedded note.png]]
    ("embed", r"!\[\[[^\]\n]*\]\]"),
    # [[wikilink|alias]]
    ("wikilink", r"\[\[[^\]\n]*\]\]"),
    # `inline code`
    ("code", r"`[^`\n]+`"),
    # $inline math$ — no leading/trailing space, so "$5 and $10" is left alone
    ("math_inline", r"\$(?!\s)[^$\n]*?(?<!\s)\$"),
    # the (target) half of [text](target), leaving the text editable
    ("link_target", r"\]\([^)\s]*(?:\s+\"[^\"]*\")?\)"),
]

MASTER_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in PATTERNS)
)

FRONTMATTER_RE = re.compile(r"(?s)\A(\ufeff?)(---\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z))")


@dataclass
class Protected:
    """Text with its machinery swapped out, plus the pieces needed to undo it."""

    text: str
    fragments: dict[str, str] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.fragments)


@dataclass
class ParsedNote:
    """A note split into the parts kiln treats differently.

    ``frontmatter`` keeps its own ``---`` fences and trailing newline, so
    ``bom + frontmatter + body`` reassembles the original exactly.
    """

    bom: str
    frontmatter: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.bom}{self.frontmatter}{self.body}"


def split_frontmatter(text: str) -> ParsedNote:
    """Separate a leading YAML frontmatter block from the body."""
    match = FRONTMATTER_RE.match(text)
    if match is None:
        bom = "\ufeff" if text.startswith("\ufeff") else ""
        return ParsedNote(bom=bom, frontmatter="", body=text[len(bom):])
    return ParsedNote(
        bom=match.group(1),
        frontmatter=match.group(2),
        body=text[match.end():],
    )


def protect(text: str) -> Protected:
    """Replace every machinery fragment with a numbered placeholder."""
    fragments: dict[str, str] = {}
    counter = 0

    def swap(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        key = PLACEHOLDER_TEMPLATE.format(index=counter)
        fragments[key] = match.group(0)
        return key

    return Protected(text=MASTER_RE.sub(swap, text), fragments=fragments)


def restore(text: str, fragments: dict[str, str]) -> str:
    """Put the original fragments back where their placeholders are.

    A placeholder the model invented (one not in ``fragments``) is left alone
    rather than guessed at; ``missing`` reports the opposite problem.
    """
    if not fragments:
        return text
    return PLACEHOLDER_RE.sub(lambda m: fragments.get(m.group(0), m.group(0)), text)


def missing(text: str, fragments: dict[str, str]) -> list[str]:
    """Placeholders that went into the model but did not come back."""
    present = set(PLACEHOLDER_RE.findall(text))
    return [key for key in fragments if key not in present]


def invented(text: str, fragments: dict[str, str]) -> list[str]:
    """Placeholders in the text that were never handed to the model."""
    return sorted(set(PLACEHOLDER_RE.findall(text)) - set(fragments))


def round_trip(text: str) -> str:
    """protect() then restore(); should return ``text`` unchanged."""
    shielded = protect(text)
    return restore(shielded.text, shielded.fragments)


def read_note(path: Path) -> str:
    """Read a note without touching its line endings or BOM."""
    return path.read_bytes().decode("utf-8")


def write_note(path: Path, text: str) -> None:
    """Write a note back exactly as given, creating parent folders as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
