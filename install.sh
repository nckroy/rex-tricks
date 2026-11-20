#!/bin/sh
# Install rex-tricks: copy it to ~/.config/rex-tricks, link `rex-tricks` into ~/.local/bin,
# and install the plugins you've enabled. The first time, it enables whatever the older
# per-add-on installers set up. Run it again after you pull updates.
#
#   ./install.sh             install or update
#   ./install.sh uninstall   remove hooks, links and the LaunchAgent (keeps your config)
set -eu
here=$(cd "$(dirname "$0")" && pwd)
py=$(command -v python3) || { echo "python3 not found" >&2; exit 1; }
command -v rex >/dev/null || echo "warning: the rex CLI isn't on PATH" >&2
if [ "${1:-}" = uninstall ]; then
  exec "$py" -I "$here/bin/rex-tricks" uninstall
fi
exec "$py" -I "$here/bin/rex-tricks" setup
