from pathlib import Path

import pytest

from vaultwright.core import parse

GNARLY = """---
title: Tensile Testing
tags: [ne220l, lab]
---

# Lab 2 — $\\sigma$ vs $\\varepsilon$

See [[NE 220L/Lab 1|the first lab]] and ![[stress-strain.png]].

Young's modulus is $E = \\sigma / \\varepsilon$, and the full form is

$$
\\sigma(t) = \\frac{F(t)}{A_0}
$$

```python
# a [[wikilink]] and $math$ in here must survive untouched
x = f"{a}$b$"
```

Run `uv run pytest` before pushing. Costs were $5 and $10.

%% private note to self %%

More in [the docs](https://example.com/a_b "Title") and [local](Notes/Other.md).
"""


def test_round_trip_is_identical() -> None:
    assert parse.round_trip(GNARLY) == GNARLY


@pytest.mark.parametrize(
    "text",
    [
        "",
        "plain prose only\n",
        "﻿---\ntitle: BOM\n---\n\nbody\n",                 # BOM
        "---\r\ntitle: CRLF\r\n---\r\n\r\ntext with [[link]]\r\n",  # Windows line endings
        "no trailing newline",
        "```\nunclosed fence\n",
        "$$\nunclosed math\n",
        "[[link]] at the very start",
        "nested ![[embed]] inside [[link]] text",
    ],
)
def test_round_trip_edge_cases(text: str) -> None:
    assert parse.round_trip(text) == text


def test_machinery_is_hidden_from_the_model() -> None:
    shielded = parse.protect(GNARLY)
    visible = shielded.text

    assert "[[" not in visible
    assert "```" not in visible
    assert "$$" not in visible
    assert "%%" not in visible
    assert "https://example.com" not in visible
    # prose survives untouched
    assert "Young's modulus is" in visible
    assert "Lab 2" in visible


def test_currency_is_not_treated_as_math() -> None:
    shielded = parse.protect("Costs were $5 and $10 total.\n")
    assert shielded.text == "Costs were $5 and $10 total.\n"
    assert shielded.count == 0


def test_split_frontmatter() -> None:
    parsed = parse.split_frontmatter(GNARLY)
    assert parsed.frontmatter.startswith("---\n")
    assert "tags: [ne220l, lab]" in parsed.frontmatter
    assert parsed.body.startswith("\n# Lab 2")
    assert parsed.text == GNARLY


def test_split_frontmatter_without_any() -> None:
    parsed = parse.split_frontmatter("# Just a heading\n")
    assert parsed.frontmatter == ""
    assert parsed.body == "# Just a heading\n"


def test_three_dashes_mid_note_is_not_frontmatter() -> None:
    text = "# Heading\n\n---\n\nA horizontal rule.\n"
    assert parse.split_frontmatter(text).frontmatter == ""


def test_missing_reports_dropped_placeholders() -> None:
    shielded = parse.protect("See [[A]] and [[B]].\n")
    mangled = shielded.text.replace(next(iter(shielded.fragments)), "")

    dropped = parse.missing(mangled, shielded.fragments)
    assert len(dropped) == 1
    assert parse.missing(shielded.text, shielded.fragments) == []


def test_invented_reports_made_up_placeholders() -> None:
    shielded = parse.protect("See [[A]].\n")
    assert parse.invented(shielded.text + "⟦VW9999⟧", shielded.fragments) == [
        "⟦VW9999⟧"
    ]


def test_restore_leaves_unknown_placeholders_alone() -> None:
    assert parse.restore("text ⟦VW0007⟧", {}) == "text ⟦VW0007⟧"


def test_read_and_write_are_byte_identical(tmp_path: Path) -> None:
    raw = "﻿---\r\ntitle: Round trip\r\n---\r\n\r\n[[link]] and `code`\r\n"
    path = tmp_path / "note.md"
    path.write_bytes(raw.encode("utf-8"))

    text = parse.read_note(path)
    out = tmp_path / "nested" / "out.md"
    parse.write_note(out, parse.round_trip(text))

    assert out.read_bytes() == path.read_bytes()


def test_note_containing_placeholder_shaped_text() -> None:
    """A note that already looks like it holds placeholders must still round trip."""
    text = "literal \u27e6VW0005\u27e7 next to a real [[link]]\n"
    assert parse.round_trip(text) == text
