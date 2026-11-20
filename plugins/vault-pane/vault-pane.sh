#!/bin/sh
# Open an Obsidian vault in emeraldian, in a Rex pane beside this one.
#
#   vault-pane [options] [PATH] [emeraldian options]
#
#   PATH                a vault, or a note inside one. Defaults to $REX_VAULT,
#                       then to emeraldian's own default (the vault Obsidian
#                       last had open).
#   --split DIR         right (default), left, above or below
#   --anchor BLOCK      split beside BLOCK instead of this pane ($REX_BLOCK)
#   --label TEXT        pane label (default: "📓 " and the vault's or note's name)
#   --no-focus          leave the keyboard focus where it is
#   --keep              don't close the pane vault-pane opened earlier
#   -h, --help          show this help
#
# Anything else, such as --note NAME, --daily, --graph or --search QUERY, goes
# to emeraldian. The new pane's block ID is printed on stdout.
set -eu

usage() { sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; }
die() { echo "vault-pane: $*" >&2; exit 1; }

split=right anchor=${REX_BLOCK:-} label= focus=true keep= vault=
while [ $# -gt 0 ]; do
  case $1 in
    --split) split=${2:?--split needs a direction}; shift 2 ;;
    --anchor) anchor=${2:?--anchor needs a block}; shift 2 ;;
    --label) label=${2:?--label needs text}; shift 2 ;;
    --no-focus) focus=false; shift ;;
    --keep) keep=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; break ;;
    -*) break ;;
    *) [ -z "$vault" ] || break; vault=$1; shift ;;
  esac
done
vault=${vault:-${REX_VAULT:-}}

[ -n "${REX_SESSION:-}" ] || die "not inside Rex (REX_SESSION isn't set)"
[ -n "$anchor" ] || die "no pane to split beside (REX_BLOCK isn't set; use --anchor)"
command -v rex >/dev/null || die "the rex CLI isn't on PATH"
command -v jq >/dev/null || die "jq isn't installed (brew install jq)"
bin=$(command -v emeraldian) || die "emeraldian isn't installed (brew install emeraldian)"
if [ -n "$vault" ]; then
  [ -e "$vault" ] || die "no such vault or note: $vault"
  vault=$(cd "$(dirname "$vault")" && pwd)/$(basename "$vault")
fi

if [ -z "$label" ]; then
  name=${vault:+$(basename "$vault")}
  [ -f "${vault:-}" ] && name=$(basename "$vault" .md)
  label="📓 ${name:-vault}"
fi

# One vault pane per session: close the one opened last time, if it's still there.
state_dir="$HOME/Library/Caches/rex-vault-pane"
state="$state_dir/$(printf %s "$REX_SESSION" | tr -c 'A-Za-z0-9-' _)"
if [ -z "$keep" ] && [ -r "$state" ]; then
  old=$(cat "$state")
  if rex block ls -s "$REX_SESSION" --json |
      jq -e --arg id "$old" 'any(.blocks[]; .block_id == $id)' >/dev/null; then
    rex block close "$old" >/dev/null
  fi
fi

block=$(rex split -s "$REX_SESSION" -b "$anchor" --split="$split" --label "$label" \
  --focus="$focus" --json -- "$bin" ${vault:+"$vault"} "$@" | jq -r '.block_ids[0]')
[ -n "$block" ] && [ "$block" != null ] || die "rex didn't open a pane"

mkdir -p "$state_dir"
printf '%s\n' "$block" >"$state"
printf '%s\n' "$block"
