# Writing a plugin

A plugin is a folder with a `plugin.json` in it. A plugin can be any mix of:

- **a pane** in the Claude column, if it has a `pane` section;
- **commands** linked into `~/.local/bin`, if it has `links`;
- **a service**, set up and torn down by its own scripts, if it has `hooks`.

## Start one

```sh
rex-tricks new clock                     # copies plugins/_template to ~/.config/rex-tricks/plugins.d/clock
$EDITOR ~/.config/rex-tricks/plugins.d/clock/plugin.json
rex-tricks check                         # finds mistakes in the manifest
rex-tricks enable clock --at 1           # put it at the top of the Claude column
```

Start `claude` in a Rex pane to see it. A plugin in `plugins.d/` is yours alone, and install never touches it. To share one, move its folder into `plugins/` in this repo and open a pull request. A plugin in `plugins.d/` with the same name as a built-in replaces it, so you can also override a built-in for yourself. `rex-tricks check` warns when that happens.

## plugin.json

```json
{
  "name": "clock",
  "description": "One line on what this plugin does",
  "requires": { "commands": ["python3"], "python": "3.9" },
  "links": { "clock": "clock.sh" },
  "hooks": { "install": "hooks/install.sh", "uninstall": "hooks/uninstall.sh" },
  "pane": {
    "label": "🕒 clock",
    "command": ["{dir}/clock.sh"],
    "height": 0.2,
    "min_rows": 0,
    "keep_open": false
  },
  "settings": {
    "CLOCK_INTERVAL": { "default": "1", "description": "seconds between redraws" }
  }
}
```

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | Lowercase letters, digits and dashes. It must match the folder's name. |
| `description` | yes | One line, shown by `rex-tricks list`. |
| `requires.commands` | no | Programs that must be on `PATH` (or in `/opt/homebrew/bin`). A pane whose requirements are missing is skipped, and `list` says what's missing. |
| `requires.python` | no | The oldest Python the plugin runs on, such as `"3.9"`. |
| `links` | no | Commands to link into `~/.local/bin`: `{"command-name": "file-in-the-plugin"}`. |
| `hooks.install` | no | A script run by `enable` and `install`. Run it again on every install, so make it safe to repeat. |
| `hooks.uninstall` | no | A script run by `disable` and `uninstall`. |
| `pane.label` | for panes | The pane's label in Rex. |
| `pane.command` | for panes | The program and its arguments, as a list. See the placeholders below. |
| `pane.height` | no | The pane's share of the column, above 0 and at most 1. The default is 0.3. |
| `pane.min_rows` | no | The fewest rows the pane can work with. The column takes rows from other panes to give it this many. The default is 0. |
| `pane.keep_open` | no | Keep the pane open after the command exits. The default is false. |
| `settings` | no | Environment variables the plugin reads, each with a string `default` and a `description`. Users change them with `rex-tricks set NAME VAR VALUE`. An empty value isn't set at all. |

Placeholders in `pane.command`:

| Placeholder | Becomes |
|---|---|
| `{dir}` | the plugin's installed folder |
| `{python}` | the python3 that runs rex-tricks |
| `{claude_session_id}` | the new Claude Code session's ID |
| `{rex_session}` | the Rex session's ID |

A bare program name, such as `btop`, is looked up on `PATH` and in `/opt/homebrew/bin` before the pane opens.

Hooks run with `/bin/sh` from the plugin's folder. They get the plugin's settings and these variables:

| Variable | Value |
|---|---|
| `REX_TRICKS_PLUGIN_DIR` | the plugin's installed folder |
| `REX_TRICKS_HOME` | `~/.config/rex-tricks` |
| `REX_TRICKS_BIN` | where commands are linked |
| `REX_TRICKS_PYTHON` | the python3 running rex-tricks |

A non-zero exit is reported but doesn't stop other plugins from installing.

## Guidelines

- **Write panes that redraw to fit.** A pane can be anything from 8 rows high, and its size is set once. Read the size from the terminal on each redraw, as `usage_report.py` does, rather than once at start.
- **Never block Claude's start-up.** A pane's command runs in its own pane, but a hook that waits on the network slows `rex-tricks install`.
- **Keep private data out of the repo.** Use example host names (`example.net`), and read real ones from local files, as the context panes do with `~/.config/rex/prod-hosts`.
- **Put caches in `~/Library/Caches/<plugin>`,** and remove them in the uninstall hook.
- **Use Python 3.9 or later, and the standard library only,** so plugins run on the python3 that comes with macOS.
- **Document it in `docs/plugins/<name>.md`,** and add a row to the README's table.

## Built-in examples

| Plugin | Shows how to |
|---|---|
| [`btop`](../plugins/btop/plugin.json) | make a pane from an existing program, with only a manifest and a `min_rows` |
| [`claude-usage`](../plugins/claude-usage/plugin.json) | use `{claude_session_id}`, `keep_open` and a setting |
| [`work-calendar`](../plugins/work-calendar/plugin.json) | make a pane that also links commands and clears its cache on uninstall |
| [`vault-pane`](../plugins/vault-pane/plugin.json) | make a command-only plugin |
| [`context-panes`](../plugins/context-panes/plugin.json) | make a service with a LaunchAgent set up and removed by hooks |
