#!/bin/zsh
# Open the work calendar in a Rex pane to the right of this one (or of BLOCK).
#   workcal-pane.sh [--below] [BLOCK]
D=${0:A:h}
dir=right
[[ $1 == --below ]] && { dir=below; shift; }
anchor=${1:-$REX_BLOCK}
[[ -n $anchor ]] || { echo "Run this inside a Rex pane, or pass a block ID." >&2; exit 1; }
py=$(command -v python3) || { echo "python3 not found" >&2; exit 1; }
args=(-b "$anchor" --split=$dir --label "📅 Work calendar" --focus=false)
[[ -n $REX_SESSION ]] && args+=(-s "$REX_SESSION")
exec rex split "${args[@]}" -- "$py" -I "$D/workcal.py"
