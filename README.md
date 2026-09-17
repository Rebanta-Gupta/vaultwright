# vaultwright

Command line tools for working with an [Obsidian](https://obsidian.md) vault.

## Install

```bash
uv sync
```

## Usage

```bash
vw scan path/to/vault            # folder tree with note counts
vw scan path/to/vault -s Lectures  # just one folder
vw scan path/to/vault -d 2         # limit tree depth
```

`vaultwright` and `vw` are the same command.

## Planned

- `kiln` — refine notes with a local [Ollama](https://ollama.com) model into a `refined/` folder.

## License

MIT
