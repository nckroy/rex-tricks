# Configuring rex-tricks

rex-tricks keeps its files in `~/.config/rex-tricks`:

| Path | What it is |
|---|---|
| `config.json` | Your settings: which plugins are on, the Claude column, overrides. |
| `plugins/` | The built-in plugins, copied from the repo. `./install.sh` replaces this folder, so don't edit it. |
| `plugins.d/` | Your own plugins. Nothing touches this folder. |
| `bin/`, `core/` | The `rex-tricks` command and its code. |

`rex-tricks` is linked into `~/.local/bin`. Set `REX_TRICKS_HOME` to keep everything somewhere else, and `REX_TRICKS_PLUGIN_PATH` (folders separated by `:`) to load plugins from more places, such as a clone of someone else's plugins.

## Commands

```sh
rex-tricks list                     # every plugin found, whether it's on, and what it needs
rex-tricks info btop                # one plugin, with your settings applied
rex-tricks enable btop --at 2       # turn a plugin on (a pane goes into the column at position 2)
rex-tricks disable btop             # turn it off and remove its links and services
rex-tricks column                   # show the Claude column
rex-tricks column work-calendar claude-usage    # set it, top to bottom
rex-tricks set btop pane.min_rows 30            # override part of a plugin's pane
rex-tricks set work-calendar WORKCAL_MODEL sonnet   # set one of a plugin's settings
rex-tricks unset btop pane.min_rows             # back to the plugin's default
rex-tricks check                    # validate plugins and config.json
rex-tricks install                  # reinstall the enabled plugins
rex-tricks uninstall                # remove every hook, link and service (keeps config.json)
```

Changes to the column and to pane or setting values take effect the next time `claude` starts. The column is built from `config.json` each time, so nothing needs reinstalling. `enable` and `disable` install and remove right away.

## config.json

`rex-tricks` writes this file for you, but you can edit it by hand. Run `rex-tricks check` afterwards.

```json
{
  "enabled": ["context-panes", "claude-usage", "work-calendar", "btop", "vault-pane"],
  "column": {
    "panes": ["work-calendar", "btop", "claude-usage"],
    "width": 83,
    "min_rows": 8
  },
  "plugins": {
    "btop": { "pane": { "min_rows": 30 } },
    "work-calendar": { "settings": { "WORKCAL_REFRESH_MIN": "10" } }
  }
}
```

| Key | Meaning |
|---|---|
| `enabled` | Plugins that are on. Only these are installed and opened. |
| `column.panes` | The Claude column, top to bottom. A plugin listed here also has to be in `enabled`. |
| `column.width` | The column's width in terminal columns, including padding. The default of 83 fits the usage report's 80. |
| `column.min_rows` | The smallest a pane gets when another pane needs its rows. The default is 8. `REX_PANE_MIN_ROWS` overrides it. |
| `plugins.NAME.pane` | Overrides for the plugin's `pane`: `label`, `command`, `height`, `min_rows`, `keep_open`. |
| `plugins.NAME.settings` | Values for the plugin's settings, as strings. They reach the plugin as environment variables. |

## The Claude column

When you start a new `claude` session in a Rex pane, a Claude Code `SessionStart` hook (matcher `startup`) opens the column to its right. rex-tricks adds the hook to `~/.claude/settings.json` while any enabled plugin is in the column, and removes it when none is. It backs the file up to `~/.claude/backups/` before each change. Outside Rex the hook does nothing.

The hook:

1. opens the first pane to the right of Claude's pane, without taking focus;
2. opens each later pane below the previous one;
3. moves the borders so the column is `column.width` wide and each pane gets its `height` share. Shares are relative, so `0.35, 0.30, 0.35` and `7, 6, 7` give the same column. Height must be at most 1, though.

A plugin whose requirements are missing, such as btop when it isn't installed, is skipped. The hook has a 10-second timeout, always exits 0 and returns as soon as the panes are open, so it can't block or break Claude's start-up. Problems are logged to `$TMPDIR/rex-tricks-column.log`.

### Minimum rows

A pane's size in rows isn't known until the Rex app lays it out. After a cold start of Rex that can take several seconds, longer than the hook may run. So a detached process waits up to 30 seconds for the sizes to be set and to settle, and then:

- **Checks the column's width.** If Claude's pane reported a stale width when the hook ran, it moves the border again.
- **Gives each pane its `min_rows`.** Rows don't map exactly to proportions, because each pane loses a row or two to its label bar and border. So it fits the window's height in rows and that overhead from the sizes of every pane in the window. A pane that's too short takes rows from the others, bottom pane first, and each of them keeps at least `column.min_rows` (or its own minimum, if that's larger). It then measures again and corrects, up to four times. If the column is too short for every minimum, each pane is left as big as it can be.

Sizes are set once, when the column opens. After you change the font size or the window, drag the borders, or close the column's panes and restart `claude`.

## Moving from the old installers

Before plugins, each add-on had its own `install.sh`. The first time you run `./install.sh` (which runs `rex-tricks setup`), it:

- finds what those installers set up and enables the matching plugins;
- swaps the old `claude-usage/rex_session_start.sh` hook for the new one;
- repoints the `workcal`, `workcal-pane` and `vault-pane` links;
- restarts the context watcher from its new place.

It lists the old folders it no longer uses, such as `~/.claude/scripts/claude-usage`, so you can delete them. Your `~/.zshrc` line for context-coded panes keeps working unchanged.
