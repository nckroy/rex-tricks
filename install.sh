#!/bin/sh
# Install the context-coded panes add-on for Rex on macOS.
#
#   ./install.sh            copy files to ~/.config/rex and start the watcher
#   ./install.sh uninstall  stop the watcher and remove its LaunchAgent
#
# The zsh hook still needs one line in ~/.zshrc (see README.md); this script
# doesn't edit your dotfiles.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.config/rex"
label="io.github.nckroy.rex-context-watch"
plist="$HOME/Library/LaunchAgents/$label.plist"
log="$HOME/Library/Logs/rex-context-watch.log"
uid=$(id -u)

if [ "${1:-}" = uninstall ]; then
  launchctl bootout "gui/$uid/$label" 2>/dev/null || true
  rm -f "$plist"
  echo "Watcher stopped and LaunchAgent removed. Files in $dest were left in place."
  exit 0
fi

rex=$(command -v rex) || { echo "rex not found on PATH" >&2; exit 1; }

mkdir -p "$dest" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
# Copy rather than link: a LaunchAgent reading ~/Documents or iCloud folders
# triggers macOS privacy prompts.
cp "$here/prod-highlight.zsh" "$here/context-watch.lua" "$dest/"

cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$rex</string>
    <string>--autostart=false</string>
    <string>do</string>
    <string>--all</string>
    <string>$dest/context-watch.lua</string>
  </array>
  <key>RunAtLoad</key><true/>
  <!-- Restart if it exits, e.g. when the Rex server restarts or isn't up yet. -->
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$log</string>
  <key>StandardErrorPath</key><string>$log</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$uid/$label" 2>/dev/null || true
launchctl bootstrap "gui/$uid" "$plist"
echo "Installed to $dest; watcher running as $label (log: $log)."
