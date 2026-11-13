# Obsidian vault pane

`vault-pane` opens an Obsidian vault in [emeraldian](https://github.com/iamrohithrnair/emeraldian), a terminal UI for Obsidian, in a Rex pane beside the one you're in. It keeps one vault pane per Rex session: running it again closes the pane it opened last time and opens a new one.

It's handy for reading a note that a script or Claude just wrote, such as a daily brief, without leaving the terminal.

## Requirements

- Rex on macOS, with the `rex` CLI on `PATH`
- [emeraldian](https://github.com/iamrohithrnair/emeraldian): `brew install emeraldian`
- `jq`

## Install

```sh
vault-pane/install.sh
```

This copies `vault-pane.sh` to `~/.config/rex/vault-pane` and links `vault-pane` into `~/.local/bin`. Run `vault-pane/install.sh uninstall` to remove the link.

## Use

```sh
vault-pane ~/Notes                          # a vault
vault-pane ~/Notes/Daily/2026-11-13.md      # a note, opened in its vault
vault-pane ~/Notes --note "Project Ideas"   # a note by name
vault-pane ~/Notes --daily                  # today's daily note
vault-pane ~/Notes --graph                  # the graph view
vault-pane --no-focus --split below ~/Notes
```

| Option | What it does |
|---|---|
| `PATH` | A vault, or a note inside one. Defaults to `$REX_VAULT`, then to the vault Obsidian last had open. |
| `--split DIR` | Where the pane goes: `right` (the default), `left`, `above` or `below`. |
| `--anchor BLOCK` | Split beside another pane instead of this one. |
| `--label TEXT` | The pane label. The default is `📓` and the vault's or note's name. |
| `--no-focus` | Leave the keyboard focus in the current pane. |
| `--keep` | Don't close the vault pane opened earlier. |

Any other option, such as `--note`, `--daily`, `--graph`, `--search` or `--theme`, goes to emeraldian. The new pane's block ID is printed on stdout, so a script can capture it, close it or move it later.

## Settings

- **Default vault:** set `REX_VAULT` in `~/.zshrc`, for example `export REX_VAULT=~/Notes`.
- **emeraldian's settings** are in `~/Library/Application Support/emeraldian/config.toml`. It opens notes in reading mode by default (`reading_mode = true` under `[ui]`). `Ctrl+E` switches to editing.
- **Assistant:** emeraldian's assistant (`Ctrl+L`) is off until you choose a provider. It can edit, rename and delete notes and sends note contents to that provider. Set `allow_writes = false` under `[agent]` to keep it read-only.

## How it works

The script checks that it's running inside Rex, then runs `rex split` with emeraldian as the pane's command. It saves the new block ID in `~/Library/Caches/rex-vault-pane/`, one file per Rex session. Next time, it closes that block first if it's still open.

## Limitations

- Pictures in notes use the kitty graphics protocol. Rex supports it, but large images can draw slowly.
- Shortcuts with both `Ctrl` and `Shift`, such as `Ctrl+Shift+F`, need the kitty keyboard protocol. Rex supports it. If one doesn't work, `Ctrl+F` pressed twice also searches every note.
- emeraldian redraws when the pane is resized, so the pane can be any width.
