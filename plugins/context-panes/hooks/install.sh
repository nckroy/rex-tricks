#!/bin/sh
# Start the context watcher as a LaunchAgent, and point ~/.config/rex/prod-highlight.zsh
# (the file your ~/.zshrc sources) at this plugin's copy.
# Run by rex-tricks with REX_TRICKS_PLUGIN_DIR set. Safe to run again.
set -eu
dir=${REX_TRICKS_PLUGIN_DIR:?run this with rex-tricks}
label="io.github.nckroy.rex-context-watch"
plist="$HOME/Library/LaunchAgents/$label.plist"
log="$HOME/Library/Logs/rex-context-watch.log"
shim="$HOME/.config/rex/prod-highlight.zsh"
uid=$(id -u)
rex=$(command -v rex) || { echo "rex not found on PATH" >&2; exit 1; }

# The ~/.zshrc line from the README sources this path. Replace an old copy with a shim,
# but leave a file the user wrote alone.
mkdir -p "$(dirname "$shim")"
if [ ! -e "$shim" ] || grep -q 'Installed by rex-tricks\|Rex production-context highlighting' "$shim"; then
  cat > "$shim" <<SHIM
# Installed by rex-tricks (context-panes plugin). The real file is in the plugin's folder.
source "$dir/prod-highlight.zsh"
SHIM
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$plist" <<PLIST
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
    <string>$dir/context-watch.lua</string>
  </array>
  <key>RunAtLoad</key><true/>
  <!-- Restart if it exits, e.g. when the Rex server restarts or isn't up yet. -->
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$log</string>
  <key>StandardErrorPath</key><string>$log</string>
</dict>
</plist>
PLIST
# bootout returns before the job is gone, and bootstrapping too soon fails with error 5.
launchctl bootout "gui/$uid/$label" 2>/dev/null || true
i=0
while launchctl print "gui/$uid/$label" >/dev/null 2>&1 && [ $i -lt 50 ]; do sleep 0.1; i=$((i + 1)); done
i=0
until launchctl bootstrap "gui/$uid" "$plist" 2>/dev/null; do
  i=$((i + 1))
  [ $i -lt 5 ] || { launchctl bootstrap "gui/$uid" "$plist"; exit 1; }
  sleep 1
done
echo "  context-panes: watcher running as $label (log: $log)"
