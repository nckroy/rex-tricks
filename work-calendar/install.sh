#!/bin/sh
# Install the work calendar pane for Rex.
#
#   ./install.sh            copy the scripts to ~/.config/rex/work-calendar and link
#                           `workcal` and `workcal-pane` into ~/.local/bin
#   ./install.sh uninstall  remove the links and the cached events
set -eu

here=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.config/rex/work-calendar"
bin="$HOME/.local/bin"
cache="$HOME/Library/Caches/rex-work-calendar"

if [ "${1:-}" = uninstall ]; then
  rm -f "$bin/workcal" "$bin/workcal-pane"
  rm -rf "$cache"
  echo "Links and cache removed. Files in $dest were left in place."
  exit 0
fi

command -v claude >/dev/null || echo "warning: claude isn't on PATH; the pane fetches events with it" >&2
mkdir -p "$dest" "$bin"
cp "$here/workcal.py" "$here/workcal-pane.sh" "$dest/"
chmod +x "$dest/workcal.py" "$dest/workcal-pane.sh"
ln -sf "$dest/workcal.py" "$bin/workcal"
ln -sf "$dest/workcal-pane.sh" "$bin/workcal-pane"
echo "Installed to $dest; run 'workcal-pane' in a Rex pane, or 'workcal' in any terminal."
case ":$PATH:" in *":$bin:"*) ;; *) echo "note: $bin isn't on your PATH" >&2 ;; esac
