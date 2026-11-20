# rex-tricks

Plugins for the [Rex](https://www.superlogical.com/rex/docs) terminal on macOS, and `rex-tricks`, a small tool that installs them and arranges the column of panes that opens beside Claude Code.

![A Rex window in three columns. On the left, two context-coded panes: one labeled PROD · kube eks-prod-east, aws acme-prod, dir prod, with red text and the red ⚠ PROD prompt segment, and one labeled SUDO · port selfupdate. In the middle, the Obsidian vault pane shows a sample daily note in emeraldian. On the right, the work calendar shows a day of sample meetings above btop and the Claude usage report.](docs/demo.png)

*Left: two [context-coded panes](docs/plugins/context-panes.md), a production kube/AWS/directory context with red text and the `⚠ PROD` prompt segment, and a `sudo` command. Middle: the [Obsidian vault pane](docs/plugins/vault-pane.md) on a sample vault. Right: the [Claude column](docs/configuration.md#the-claude-column) that opens beside Claude, with the [work calendar](docs/plugins/work-calendar.md) showing made-up meetings from its `--demo` mode, btop sized to its 24-row minimum, and the [Claude usage pane](docs/plugins/claude-usage.md). Host names are examples.*

## Plugins

| Plugin | What it does | Docs |
|---|---|---|
| `context-panes` | Labels and colors each pane by what it's working against: 🔴 PROD, 🟡 SUDO, 🌐 remote or 💻 local | [context-panes.md](docs/plugins/context-panes.md) |
| `claude-usage` | A live report of your Claude Code usage, in the Claude column | [claude-usage.md](docs/plugins/claude-usage.md) |
| `work-calendar` | A text-mode view of your Outlook calendar, fed by Claude's Microsoft 365 connector, in the Claude column or any pane | [work-calendar.md](docs/plugins/work-calendar.md) |
| `btop` | The btop system monitor in the Claude column, given the 24 rows it needs | [btop.md](docs/plugins/btop.md) |
| `vault-pane` | Opens an Obsidian vault or note in emeraldian, a terminal UI for Obsidian, beside the current pane | [vault-pane.md](docs/plugins/vault-pane.md) |

The **Claude column** is the stack of panes that opens to the right of Claude Code whenever you start `claude` in Rex. You choose which plugins go in it and in what order, and rex-tricks gives each pane its share of the height and at least the rows it needs. See [configuration](docs/configuration.md).

### Context-coded panes

- Labels panes `🔴 PROD`, `🟡 SUDO`, `🌐` remote or `💻 local`, with the reason, such as `🔴 PROD · kube eks-prod-east`.
- Recolors the text red in production and yellow as root, and adds a `⚠ PROD` segment to a Powerlevel10k prompt.
- Detects production from SSH targets, the kube context, AWS profiles, OpenTofu workspaces, directories, and your own list of hosts.
- Catches remote sessions however they start: `ssh`, `mosh`, `kubectl exec`, `docker exec`, `aws ssm`, `tailscale ssh` and aliases or scripts that run them.
- Follows a second SSH hop through a bastion when the far shells report their host (OSC 7).

### Claude usage

- Opens in the Claude column whenever you start `claude` in Rex, and refreshes every 30 seconds.
- Shows this session's tokens, cache hit rate, models, subagents and output by hour.
- Shows context size and growth, with likely compactions.
- Shows the current 5-hour window, with time left and per-session totals.

### Work calendar

- Day view with a `now` line and a countdown to your next meeting. Conflicts are marked, and you can join a meeting's Zoom link with one key.
- Week strip, week view, and navigation by day and by week.
- Fetches through a locked-down headless `claude -p`. The model never reads your events, and several panes share one cache.
- Opens at the top of the Claude column each time you start `claude`, or anywhere with `workcal-pane`.

### Obsidian vault pane

- Opens a vault, a note, today's daily note or the graph view in [emeraldian](https://github.com/iamrohithrnair/emeraldian), in a pane beside this one.
- Keeps one vault pane per Rex session, so running it again replaces the last one.
- Prints the new pane's block ID, so scripts and Claude can open a note they just wrote and close it later.

## Install

You need Rex on macOS with the `rex` CLI on `PATH`, and `python3` 3.9 or later (the one that comes with macOS will do). From your clone of this repo:

```sh
./install.sh
```

This copies rex-tricks to `~/.config/rex-tricks` and links the `rex-tricks` command into `~/.local/bin`. If you used the older per-add-on installers, it enables the same add-ons as plugins and takes over their hooks. Then turn on the plugins you want:

```sh
rex-tricks list                       # what there is, and what each one needs
rex-tricks enable claude-usage        # panes join the Claude column...
rex-tricks enable work-calendar --at 1    # ...at the position you give
rex-tricks enable btop --at 2
rex-tricks enable vault-pane
rex-tricks enable context-panes
```

Each plugin's doc lists what it needs: `jq`, emeraldian, Claude Code with the Microsoft 365 connector, and so on. Context-coded panes also need one line at the **end** of `~/.zshrc`, after Powerlevel10k is loaded:

```zsh
# Rex: context-coded panes (PROD / SUDO / local). Keep after p10k is loaded.
[[ -r ~/.config/rex/prod-highlight.zsh ]] && source ~/.config/rex/prod-highlight.zsh
```

Run `./install.sh` again after you pull updates. `./install.sh uninstall` removes every hook, link and LaunchAgent, and keeps your settings. [Configuration](docs/configuration.md) covers the column, per-plugin settings and `config.json`.

## Contributing

Issues and pull requests are welcome, and new plugins especially.

- **A plugin is a folder under `plugins/` with a `plugin.json`.** [Writing a plugin](docs/writing-plugins.md) covers the manifest, hooks and settings. `rex-tricks new NAME` starts one in `~/.config/rex-tricks/plugins.d/`, where you can try it before moving it into the repo.
- **Run the checks:** `bin/rex-tricks check` and `python3 -m unittest discover tests`. Run them on `/usr/bin/python3` too, which is 3.9.
- **Document a plugin in `docs/plugins/<name>.md`:** what it does, requirements, install, settings, how it works and limitations. Add a row to the table above and a few bullets about what it does. Keep the details out of this README.
- **Test in Rex,** in a real pane, at narrow and wide sizes. `rex capture -b <block>` prints a pane's screen.
- **Keep private data out of the repo.** Use example host names (`example.net`), and read real ones from local files such as `~/.config/rex/prod-hosts`.
- **Write in American English,** in short, plain sentences.
