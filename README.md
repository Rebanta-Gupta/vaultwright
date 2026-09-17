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

## Configuration

Optional. Settings are read from the first of these that exists:

1. `--config <path>`
2. `vaultwright.toml` in the current folder
3. `~/.config/vaultwright/config.toml`

```toml
vault = "C:/Users/you/Obsidian/Vaults/MyVault"

[scan]
ignore = ["Cold Emails", "Templates"]

[kiln]
model = "qwen3:8b"
output = "refined"
temperature = 0.3
```

With `vault` set, the path argument becomes optional: `vw scan -s Lectures`.
`vw config` prints the settings in use and where they came from.

## Planned

- `kiln` — refine notes with a local [Ollama](https://ollama.com) model into a `refined/` folder.

## License

MIT
