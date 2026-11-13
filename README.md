# rex-tricks

Small add-ons for the [Rex](https://www.superlogical.com/rex/docs) terminal on macOS.

![A Rex window with six context-coded panes and the Claude usage pane. Pane labels read: PROD · kube eks-prod-east, aws acme-prod, dir prod (with the red PROD prompt segment); PROD · ssh db1.prod.example.net; SUDO · port selfupdate; web1.staging.example.net (remote); local · rex-tricks; and PROD · SUDO · dir prod. The right-hand pane shows the Claude usage report.](docs/demo.png)

*Left to right, top to bottom: a production kube/AWS/directory context with red text and the `⚠ PROD` prompt segment, SSH to a production host, a `sudo` command, SSH to a non-production host, an ordinary local pane, and `sudo` inside a production directory. On the right is the [Claude usage pane](docs/claude-usage-pane.md). Host names are examples.*

## Add-ons

| Add-on | What it does | Docs |
|---|---|---|
| **Context-coded panes** | Labels and colors each pane by what it's working against: 🔴 PROD, 🟡 SUDO, 🌐 remote or 💻 local | [docs/context-coded-panes.md](docs/context-coded-panes.md) |
| **Claude usage pane** | Opens a live report of your Claude Code usage beside Claude when it starts | [docs/claude-usage-pane.md](docs/claude-usage-pane.md) |
| **Work calendar pane** | A text-mode view of your Outlook calendar, fed by Claude's Microsoft 365 connector | [docs/work-calendar.md](docs/work-calendar.md) |

### Context-coded panes

- Labels panes `🔴 PROD`, `🟡 SUDO`, `🌐` remote or `💻 local`, with the reason, such as `🔴 PROD · kube eks-prod-east`.
- Recolors the text red in production and yellow as root, and adds a `⚠ PROD` segment to a Powerlevel10k prompt.
- Detects production from SSH targets, the kube context, AWS profiles, OpenTofu workspaces, directories, and your own list of hosts.
- Catches remote sessions however they start: `ssh`, `mosh`, `kubectl exec`, `docker exec`, `aws ssm`, `tailscale ssh` and aliases or scripts that run them.
- Follows a second SSH hop through a bastion when the far shells report their host (OSC 7).

### Claude usage pane

- Opens to the right of Claude Code whenever you start `claude` in Rex, and refreshes every 30 seconds.
- Shows this session's tokens, cache hit rate, models, subagents and output by hour.
- Shows context size and growth, with likely compactions.
- Shows the current 5-hour window, with time left and per-session totals.

### Work calendar pane

- Day view with a `now` line and a countdown to your next meeting. Conflicts are marked, and you can join a meeting's Zoom link with one key.
- Week strip, week view, and navigation by day and by week.
- Fetches through a locked-down headless `claude -p`. The model never reads your events, and several panes share one cache.
- When the Claude usage pane is installed, it opens above that pane each time you start `claude`.

## Install

You need Rex on macOS with the `rex` CLI on `PATH`. Each add-on installs on its own. Run its installer from your clone of this repo, and run it again after you pull updates.

**Context-coded panes** (needs `jq`; Powerlevel10k is optional):

```sh
./install.sh
```

Then add this line to the **end** of `~/.zshrc`, after Powerlevel10k is loaded, and open a new pane:

```zsh
# Rex: context-coded panes (PROD / SUDO / local). Keep after p10k is loaded.
[[ -r ~/.config/rex/prod-highlight.zsh ]] && source ~/.config/rex/prod-highlight.zsh
```

**Claude usage pane** (needs Claude Code, `python3` and `jq`):

```sh
claude-usage/install.sh
```

**Work calendar pane** (needs Claude Code signed in to claude.ai with the Microsoft 365 connector connected, and `python3`):

```sh
work-calendar/install.sh
workcal-pane          # open it now, to the right of this pane
```

Each installer takes `uninstall`. The docs for each add-on cover requirements, settings, checks and troubleshooting.

## Contributing

Issues and pull requests are welcome.

- **One folder or file set per add-on,** each with its own `install.sh` that copies files into place (a LaunchAgent can't read `~/Documents` without privacy prompts) and supports `uninstall`.
- **Document an add-on in `docs/<add-on>.md`:** what it does, requirements, install, settings, how it works and limitations. Add a row to the table above and a few bullets about what it does. Keep the details out of this README.
- **Test in Rex,** in a real pane, at narrow and wide sizes. `rex block capture -b <block>` prints a pane's screen.
- **Keep private data out of the repo.** Use example host names (`example.net`), and read real ones from local files such as `~/.config/rex/prod-hosts`.
- **Write in American English,** in short, plain sentences.
