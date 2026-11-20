#!/bin/sh
# Stop the context watcher and remove its LaunchAgent and the ~/.zshrc shim.
label="io.github.nckroy.rex-context-watch"
launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$label.plist"
shim="$HOME/.config/rex/prod-highlight.zsh"
grep -q 'Installed by rex-tricks' "$shim" 2>/dev/null && rm -f "$shim"
echo "  context-panes: watcher stopped. Remove the prod-highlight line from ~/.zshrc too."
