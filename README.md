# rex-tricks

Small add-ons for the [Rex](https://www.superlogical.com/rex/docs) terminal.

## Context-coded panes: PROD, SUDO, remote and local

Files: [`prod-highlight.zsh`](prod-highlight.zsh) (zsh hook), [`context-watch.lua`](context-watch.lua) (process watcher), [`install.sh`](install.sh)

This add-on makes it obvious which Rex panes are working against production, which are running as root, which are on another machine, and which are just local. It changes each pane's label and, in zsh, the colours of the text. Two parts work together:

- **The zsh hook** runs inside your shell. Before each prompt, and just before `ssh`, `mosh`, `sudo`, `su` and `doas`, it labels the pane and recolours its text.
- **The process watcher** runs in the background. It watches what is actually running in *every* pane, so it also catches what the hook can't see:
  - remote sessions started through an alias, function or script
  - other remote tools: `kubectl exec`, `docker exec`, `aws ssm`, `tailscale ssh`, `et`, `autossh`
  - root shells in bash, or in panes launched directly into a program

| Context | Pane label | Text colours (hook) | Prompt (hook) |
|---|---|---|---|
| Production | `🔴 PROD · kube eks-prod-east`, `🔴 PROD · ssh db1.prod.example` | red-shifted | white-on-red `⚠ PROD …` segment (Powerlevel10k) |
| Production + sudo | `🔴 PROD · SUDO · dir prod` | red-shifted (prod wins) | as above |
| Running as root (`sudo` / `su` / `doas`) | `🟡 SUDO · root shell`, `🟡 SUDO · port selfupdate` | yellow-shifted | — |
| Remote session started from this pane | `🌐 dev-box`, `🌐 ssh web1.staging`, `🌐 kubectl exec` | theme | — |
| This shell itself runs on a remote machine | `🌐 devbox · ~/src` | theme | — |
| Everything else | `💻 local · <dir>` | theme | — |

Everything goes back to normal once you leave the context, for example when you exit the SSH or `sudo -i` session, change directory, or switch kube context.

### Remote vs local

A pane counts as **remote** in any of these cases:

| How | Detected by |
|---|---|
| You type `ssh` / `mosh` in a hooked zsh | hook, from the command line, just before it runs |
| The pane is running `ssh`, `mosh-client`, `et`, `autossh`, `kubectl exec/attach/debug`, `docker`/`podman exec/attach/run`, `aws ssm` (`session-manager-plugin`) or `tailscale ssh`, however it was started | watcher, from the pane's process tree |
| The hooked shell itself runs remotely: `SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY` is set, or the host isn't one of `REX_LOCAL_HOSTS` | hook, once when the shell starts |

If `REX_LOCAL_HOSTS` isn't set, macOS counts as local and any other OS (for example a Linux or FreeBSD machine you reach as a Rex host) counts as remote. The hook only does this check on a machine where it's installed.

Anything else is **local**.

### What counts as production

A name counts as production if it contains `prod`, `prd` or `production` as a separate word, matched case-insensitively. So `db1.prod.example.net`, `acme-prod` and `eks-prod-east` match, but `product` doesn't.

A host also counts as production if it's listed in `~/.config/rex/prod-hosts`, whatever its name. Put one host or glob per line, and start comments with `#`. Matching ignores case, and SSH aliases from `~/.ssh/config` resolve to their real `HostName` with `ssh -G`. Both the hook and the watcher read this file. It stays on your machine, so your internal host names don't end up in this repo:

```
# ~/.config/rex/prod-hosts
bastion.example.org
*.live.example.org
```

Open a new pane after editing the file (the hook reads it at shell start-up), and run `./install.sh` again to restart the watcher.

| Signal | Where it looks | Hook | Watcher |
|---|---|---|---|
| ssh | Target host of an `ssh` / `mosh` command (option arguments such as `-p 22 -i key` are skipped) | ✓ | ✓ (`ssh`, `autossh`) |
| host | The machine the hooked shell runs on, when that's remote | ✓ | |
| kube | `current-context` in `$KUBECONFIG` or `~/.kube/config`. It reads the file directly rather than running `kubectl`, which keeps it fast. | ✓ | |
| aws | `AWS_PROFILE`, `AWS_VAULT`, `AWS_DEFAULT_PROFILE` | ✓ | |
| tofu | `TF_WORKSPACE`, or `.terraform/environment` in the current directory | ✓ | |
| dir | A path component named `prod`, `prd` or `production`, or any glob in `REX_PROD_DIRS` | ✓ | |

The hook lists all matching reasons in the label, e.g. `🔴 PROD · kube eks-prod-east, aws acme-prod`.

### Requirements

- [Rex](https://www.superlogical.com/rex/docs) on macOS, with the `rex` CLI on `PATH`, running zsh in Rex panes. The hook does nothing outside Rex, because it needs `$REX_SESSION` and `$REX_BLOCK`.
- `jq`.
- Optional: [Powerlevel10k](https://github.com/romkatv/powerlevel10k) for the red `PROD` prompt segment. Without it, the labels and text colours still work.

### Install

1. From your clone of this repo, run:

   ```sh
   ./install.sh
   ```

   This copies `prod-highlight.zsh` and `context-watch.lua` to `~/.config/rex/`. It then installs and starts a LaunchAgent (`io.github.nckroy.rex-context-watch`) that keeps the watcher running and restarts it if it stops (for example when Rex restarts). The log goes to `~/Library/Logs/rex-context-watch.log`.

   The files are copied rather than linked because a LaunchAgent reading `~/Documents` or iCloud folders triggers macOS privacy prompts. **Run `./install.sh` again after pulling updates.**

2. Add the `source` line to the **end** of `~/.zshrc`, after Powerlevel10k is loaded. `install.sh` doesn't touch your dotfiles, and without this line the hook never loads. One way to append it:

   ```zsh
   cp ~/.zshrc ~/.zshrc.bak
   cat >> ~/.zshrc <<'EOF'

   # Rex: context-coded panes (PROD / SUDO / local). Keep after p10k is loaded.
   [[ -r ~/.config/rex/prod-highlight.zsh ]] && source ~/.config/rex/prod-highlight.zsh
   EOF
   ```

3. Open a new pane, or run `exec zsh` in panes that are already open. A new pane should be labelled `💻 local · <dir>`.

   - **Check the hook:** run `print -l $precmd_functions` in a pane. It should list `_rex_prod_precmd` before `_p9k_precmd`.
   - **Check the watcher:** run `launchctl print gui/$(id -u)/io.github.nckroy.rex-context-watch | grep state`. It should say `state = running`.

The watcher works on its own too. Without step 2 you get labels from the watcher, but no colours, no prompt segment, and no kube/AWS/tofu/directory checks.

To try the watcher without installing it, run `rex do --all context-watch.lua` in a spare pane and press Ctrl-C to stop it. To remove the LaunchAgent, run `./install.sh uninstall`.

### Customise

**Hook:** set any of these in `~/.zshrc` **before** the `source` line:

```zsh
REX_PROD_HOST_RE='(^|\.)(prod|prd)[0-9]*\.|^bastion-'   # your real prod host naming
REX_PROD_NAME_RE='(^|[^[:alnum:]])(prod|prd|production|live)([^[:alnum:]]|$)'
REX_PROD_DIRS=(~/src/infra/live/* ~/src/deploy/production)
REX_PROD_HOSTS=(bastion.example.org '*.live.example.org')    # added to ~/.config/rex/prod-hosts
REX_PROD_HOSTS_FILE=~/somewhere/else/prod-hosts             # default ~/.config/rex/prod-hosts
REX_LOCAL_HOSTS=(my-mac devbox)                         # short hostnames that count as local
REX_PROD_FG='#ffd7d7';  REX_PROD_PALETTE=(...16 colours...)   # red text palette
REX_SUDO_FG='#fff3c4';  REX_SUDO_PALETTE=(...16 colours...)   # yellow text palette
```

`REX_PROD_HOST_RE` defaults to `REX_PROD_NAME_RE`. Set it if your production hosts are named differently from your other production resources.

**Watcher:** edit the tables at the top of `context-watch.lua`, then run `./install.sh` again:
- `PROD_WORDS`: words that mark a host as production. Keep these in step with `REX_PROD_NAME_RE`.
- Specific production hosts go in `~/.config/rex/prod-hosts` (see [What counts as production](#what-counts-as-production)), not in the script.
- `REMOTE_ALWAYS` and `REMOTE_SUBCOMMANDS`: which programs count as a remote session.

### How it works

- **Labels:** both parts call the Rex server API `session.set_block_label`.
  - The hook runs the call only when the label changes, which takes about 30 ms. It runs synchronously so that a quick `sudo` can't leave a stale label behind.
  - The watcher reacts to Rex's `terminal.process_changed` event. It reads the foreground process and its parents, with each one's name and user ID, and uses `ps` for an `ssh` command line.
- **No fighting between the two:** the watcher only replaces a label that signals less than its own (🔴 > 🟡 > 🌐 > anything else). When the context ends, it restores the label it replaced, but only if nothing else changed the label in the meantime. So in a hooked zsh, the hook's own labels win.
- **Text colours (hook only):** the hook prints standard terminal escape sequences. OSC 10 sets the foreground and OSC 4 sets palette entries 0–15. OSC 104 / OSC 110 restore your theme. Only the 16 ANSI colours and the default foreground change, so 256-colour and true-colour output is untouched.
- **Timing (hook):** a zsh `precmd` hook handles prompt-time state such as directory, kube, AWS and tofu. A `preexec` hook marks `ssh`/`mosh`/`sudo`/`su`/`doas` just before they start, so the label and colours are in place for the password prompt and the whole session. The `precmd` hook is placed before Powerlevel10k's, so the prompt segment always shows the current state.

### Limitations

- **The background can't be tinted.** Rex currently draws every pane's background from the app theme. It ignores a background set from inside the terminal (OSC 11), and the server's `com.superlogical.terminal.set_theme` method has no visible effect in the Mac app. So the highlight is the label plus the text colours. Per-pane tinting is an open feature request in the Rex Beta Discord ("Support tinting or theming of individual panes").
- **Switching the app theme is all-or-nothing.** The Mac app's `client.theme.change` action recolours every pane, so it isn't used here.
- **Only the hook can recolour text.** Panes the watcher catches on its own (bash, aliases, panes launched directly into a program) get the label but keep the theme's colours.
- **The watcher only checks hosts for `ssh` and `autossh`.** `mosh-client`, `kubectl exec` and the rest are labelled remote but never PROD, because their command lines don't carry a reliable host name.
- **sudo is only marked while something runs as root.** There's no SUDO marker for the time afterwards when sudo can run again without a password. Checking that with `sudo -n` would write an entry to the system log each time.
- **Remote work is identified by host name or program, not content.** What you do on the remote machine isn't inspected. A Rex host only gets the hook's checks if the hook is installed there too, and the watcher only sees panes on the server it runs against (your Mac).
- **Manual labels get overwritten.** A label you set by hand is replaced the next time the context changes.

### Troubleshooting

**A pane isn't labelled or coloured at all.** The hook isn't loaded in that shell. Check that the `source` line is in `~/.zshrc` with `grep prod-highlight ~/.zshrc`. Then run `exec zsh` in that pane, or open a new one. A shell that was already running when you added the line doesn't pick it up on its own.

**A root shell (`sudo su -`, `sudo -i`) is labelled SUDO but its text isn't yellow.** The watcher labelled it, but the colours only come from the hook. Make sure the root shell was started from a zsh that has the hook loaded (see above). Exit the root shell, run `exec zsh`, then start it again.

**Do I need to make root's shell zsh (`chsh`)?** No. The hook runs in *your* zsh, just before `sudo` starts, and the watcher reads the pane's processes from outside. The label and text colours belong to the Rex pane, so they stay in place whatever shell root uses (bash, sh, zsh). Changing root's shell wouldn't help anyway. Root's zsh reads root's config, not yours, and `sudo su -` clears `REX_SESSION` and `REX_BLOCK`, which the hook needs to find its pane.

**Remote sessions from aliases or scripts aren't labelled.** The watcher isn't running. Check it with `launchctl print gui/$(id -u)/io.github.nckroy.rex-context-watch | grep state`, look in `~/Library/Logs/rex-context-watch.log`, or run `./install.sh` again.

**My Mac shows up as `🌐` remote.** You've set `REX_LOCAL_HOSTS` but left this Mac out. Add its short hostname (`hostname -s`).
