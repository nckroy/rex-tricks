#!/bin/sh
# Install the Obsidian vault pane for Rex.
#
#   ./install.sh            copy vault-pane.sh to ~/.config/rex/vault-pane and link
#                           `vault-pane` into ~/.local/bin
#   ./install.sh uninstall  remove the link and the remembered pane IDs
set -eu

here=$(cd "$(dirname "$0")" && pwd)
dest="$HOME/.config/rex/vault-pane"
bin="$HOME/.local/bin"
cache="$HOME/Library/Caches/rex-vault-pane"

if [ "${1:-}" = uninstall ]; then
  rm -f "$bin/vault-pane"
  rm -rf "$cache"
  echo "Link and cache removed. Files in $dest were left in place."
  exit 0
fi

command -v emeraldian >/dev/null || echo "warning: emeraldian isn't installed; run 'brew install emeraldian'" >&2
command -v jq >/dev/null || echo "warning: jq isn't installed; run 'brew install jq'" >&2
mkdir -p "$dest" "$bin"
cp "$here/vault-pane.sh" "$dest/"
chmod +x "$dest/vault-pane.sh"
ln -sf "$dest/vault-pane.sh" "$bin/vault-pane"
echo "Installed to $dest; run 'vault-pane ~/path/to/vault' in a Rex pane."
case ":$PATH:" in *":$bin:"*) ;; *) echo "note: $bin isn't on your PATH" >&2 ;; esac
