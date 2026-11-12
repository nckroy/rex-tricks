#!/bin/sh
# Install the Claude usage pane for Rex.
#
#   ./install.sh            copy the scripts to ~/.claude/scripts/claude-usage and
#                           add a Claude Code SessionStart hook to ~/.claude/settings.json
#   ./install.sh uninstall  remove the hook (the scripts are left in place)
#
# settings.json is backed up to ~/.claude/backups/ before any change.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.claude/scripts/claude-usage"
settings="$HOME/.claude/settings.json"
backups="$HOME/.claude/backups"
marker="claude-usage/rex_session_start.sh"
cmd='/bin/zsh -c '"'"'"$HOME/.claude/scripts/claude-usage/rex_session_start.sh" 2>/dev/null || true'"'"

# Use the first jq that actually runs (a stale Intel build in /usr/local/bin fails on Apple silicon without Rosetta).
jq=
for j in $(which -a jq 2>/dev/null) /opt/homebrew/bin/jq /usr/bin/jq; do
  "$j" --version >/dev/null 2>&1 && { jq=$j; break; }
done
[ -n "$jq" ] || { echo "no working jq found" >&2; exit 1; }

backup() {
  [ -f "$settings" ] || return 0
  mkdir -p "$backups"
  cp "$settings" "$backups/settings.json.pre-claude-usage-$(date +%Y%m%d-%H%M%S)"
}

if [ "${1:-}" = uninstall ]; then
  if [ -f "$settings" ] && "$jq" -e --arg m "$marker" '[.hooks.SessionStart[]?.hooks[]?.command | select(contains($m))] | length > 0' "$settings" >/dev/null; then
    backup
    tmp=$(mktemp)
    "$jq" --arg m "$marker" '.hooks.SessionStart |= map(select([.hooks[]?.command | contains($m)] | any | not))' "$settings" > "$tmp"
    "$jq" -e . "$tmp" >/dev/null && mv "$tmp" "$settings"
    echo "Hook removed from $settings. Scripts in $dest were left in place."
  else
    echo "No claude-usage hook found in $settings."
  fi
  exit 0
fi

mkdir -p "$dest"
cp "$here/usage_report.py" "$here/usage_loop.sh" "$here/rex_session_start.sh" "$dest/"
chmod +x "$dest/usage_loop.sh" "$dest/rex_session_start.sh"

[ -f "$settings" ] || echo '{}' > "$settings"
if "$jq" -e --arg m "$marker" '[.hooks.SessionStart[]?.hooks[]?.command | select(contains($m))] | length > 0' "$settings" >/dev/null; then
  echo "Scripts updated in $dest; the SessionStart hook is already in $settings."
else
  backup
  tmp=$(mktemp)
  "$jq" --arg c "$cmd" '.hooks.SessionStart = ((.hooks.SessionStart // []) + [{"matcher":"startup","hooks":[{"type":"command","command":$c,"timeout":10}]}])' "$settings" > "$tmp"
  "$jq" -e . "$tmp" >/dev/null && mv "$tmp" "$settings"
  echo "Scripts installed to $dest; SessionStart hook added to $settings."
fi
