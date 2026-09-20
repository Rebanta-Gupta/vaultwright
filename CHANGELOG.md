# Changelog

All notable changes to this project are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-09-20

First working release. Everything below is new.

### Commands

- **`vw scan`** — folder tree with note counts, by vault path or name
- **`vw check`** — verify every note survives protect/restore byte for byte, writing nothing
- **`vw kiln`** — refine one note with a local Ollama model. Dry run by default
- **`vw vaults`** — list the vaults it can see
- **`vw config`** / **`vw config set`** — show settings, or change one without disturbing the file

### Refining

- Machinery is hidden from the model and restored afterwards: code fences, inline code, display and
  inline maths, wikilinks, embeds, link targets, `%%` comments, `<!-- -->` comments, horizontal rules
- Anything the model adds is rendered inside a `> [!ai]` callout by the tool, not by the model
- Replies are validated against a JSON schema; a dropped or invented placeholder rejects the note
- **Figures are checked.** If a number changes between original and refined, `--write` is refused
  unless `--allow-number-changes` is passed
- Indentation characters are restored, so a three-line fix stays a three-line diff
- Tags are normalised and merged into the note's frontmatter
- Notes under 30 words get typo fixes only — no summary, no flashcards
- Originals are never modified; output goes to a `refined/` folder beside the note

### Configuration

- `--config`, then `./vaultwright.toml`, then `~/.config/vaultwright/config.toml`
- `vault` accepts a single vault or a folder of vaults, detected rather than declared
- `[kiln]` toggles for `summary`, `tags`, `flashcards`, plus `model`, `layout`, `temperature`

### Known limitations

- Single note at a time — no batch mode yet
- No retrieval, so "fill gaps" draws on the model's own knowledge. Review the `> [!ai]` callouts
- Flashcard and addition quality is still being tuned
