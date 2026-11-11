# rex-tricks

Small add-ons for the [Rex](https://www.superlogical.com/rex/docs) terminal.

## Context-coded panes: PROD, SUDO and local

Script: [`prod-highlight.zsh`](prod-highlight.zsh)

A small zsh hook makes it obvious which Rex panes are working against production, which are running `sudo`, and which are just local. It changes each pane's label and the colours of the text in it. You don't run anything by hand; it updates itself before each prompt and just before `ssh`, `mosh`, `sudo`, `su` and `doas` commands.

| Context | Pane label | Text colours | Prompt |
|---|---|---|---|
| Production | `🔴 PROD · kube eks-prod-east` | red-shifted | white-on-red `⚠ PROD …` segment (Powerlevel10k) |
| Production + sudo | `🔴 PROD · SUDO · dir prod` | red-shifted (prod wins) | as above |
| `sudo` / `su` / `doas` running | `🟡 SUDO · root shell`, `🟡 SUDO · port selfupdate` | yellow-shifted | — |
| SSH to a non-prod host | `🟢 dev-box` | theme | — |
| Everything else | `💻 local · <dir>` | theme | — |

Everything goes back to normal at the next prompt once you leave the context, for example when you exit the SSH or `sudo -i` session, change directory, or switch kube context.

### What counts as production

A name counts as production if it contains `prod`, `prd` or `production` as a separate word, matched case-insensitively. So `db1.prod.example.net`, `acme-prod` and `eks-prod-east` match, but `product` doesn't. The hook checks:

| Signal | Where it looks |
|---|---|
| ssh | Target host of an `ssh` / `mosh` command, checked when it starts (option arguments such as `-p 22 -i key` are skipped) |
| kube | `current-context` in `$KUBECONFIG` or `~/.kube/config`. It reads the file directly rather than running `kubectl`, which keeps it fast. |
| aws | `AWS_PROFILE`, `AWS_VAULT`, `AWS_DEFAULT_PROFILE` |
| tofu | `TF_WORKSPACE`, or `.terraform/environment` in the current directory |
| dir | A path component named `prod`, `prd` or `production`, or any glob in `REX_PROD_DIRS` |

All matching reasons appear in the label, e.g. `🔴 PROD · kube eks-prod-east, aws acme-prod`.

### Requirements

- [Rex](https://www.superlogical.com/rex/docs) with the `rex` CLI on `PATH`, running zsh in Rex panes. The hook does nothing outside Rex, because it needs `$REX_SESSION` and `$REX_BLOCK`.
- `jq`.
- Optional: [Powerlevel10k](https://github.com/romkatv/powerlevel10k) for the red `PROD` prompt segment. Without it, the labels and text colours still work.

### Install

1. Copy [`prod-highlight.zsh`](prod-highlight.zsh) to `~/.config/rex/prod-highlight.zsh`, or point the `source` line below at your clone of this repo.
2. Add this line to the **end** of `~/.zshrc`, after Powerlevel10k is loaded:

   ```zsh
   [[ -r ~/.config/rex/prod-highlight.zsh ]] && source ~/.config/rex/prod-highlight.zsh
   ```

3. Open a new pane. In panes that are already open, run the `source` line once.

### Customise

Set any of these in `~/.zshrc` **before** the `source` line:

```zsh
REX_PROD_HOST_RE='(^|\.)(prod|prd)[0-9]*\.|^bastion-'   # your real prod host naming
REX_PROD_NAME_RE='(^|[^[:alnum:]])(prod|prd|production|live)([^[:alnum:]]|$)'
REX_PROD_DIRS=(~/src/infra/live/* ~/src/deploy/production)
REX_PROD_FG='#ffd7d7';  REX_PROD_PALETTE=(...16 colours...)   # red text palette
REX_SUDO_FG='#fff3c4';  REX_SUDO_PALETTE=(...16 colours...)   # yellow text palette
```

`REX_PROD_HOST_RE` defaults to `REX_PROD_NAME_RE`. Set it if your production hosts are named differently from your other production resources.

### How it works

- **Labels:** each change calls the Rex server API `session.set_block_label` for the pane (`$REX_BLOCK`). The call runs only when the label actually changes and takes about 30 ms. It runs synchronously so that a quick `sudo` can't leave a stale label behind.
- **Text colours:** the hook prints standard terminal escape sequences. OSC 10 sets the foreground and OSC 4 sets palette entries 0–15. OSC 104 / OSC 110 restore your theme. Only the 16 ANSI colours and the default foreground change, so 256-colour and true-colour output is untouched.
- **Timing:** a zsh `precmd` hook handles prompt-time state such as directory, kube, AWS and tofu. A `preexec` hook marks `ssh`/`mosh`/`sudo`/`su`/`doas` just before they start, so the label and colours are in place for the password prompt and the whole session. The `precmd` hook is placed before Powerlevel10k's, so the prompt segment always shows the current state.

### Limitations

- **The background can't be tinted.** Rex currently draws every pane's background from the app theme. It ignores a background set from inside the terminal (OSC 11), and the server's `com.superlogical.terminal.set_theme` method has no visible effect in the Mac app. So the highlight is the label plus the text colours. Per-pane tinting is an open feature request in the Rex Beta Discord ("Support tinting or theming of individual panes").
- **Switching the app theme is all-or-nothing.** The Mac app's `client.theme.change` action recolours every pane, so it isn't used here.
- **sudo is only marked while a command runs.** There's no SUDO marker for the time afterwards when sudo can run again without a password. Checking that with `sudo -n` before every prompt would write an entry to the system log each time.
- **SSH detection is by host name only.** What you do on the remote machine isn't inspected, and the remote shell doesn't run this hook.
- **Only zsh shell panes are covered.** Panes started directly with a program, such as `rex run -- top`, aren't labelled.
- **Manual labels get overwritten.** A label you set by hand is replaced the next time the context changes.
