#!/bin/zsh
# Claude Code SessionStart hook: inside Rex, open the usage pane to the right of Claude's pane,
# with the work calendar above it when that is installed.
# Reads the hook JSON on stdin for session_id. Does nothing outside Rex. Never blocks startup.
[[ -n "$REX_SESSION" && -n "$REX_BLOCK" ]] || exit 0
command -v rex >/dev/null || exit 0
D=${0:A:h}
sid=$(python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("session_id",""))' 2>/dev/null)
[[ -n "$sid" ]] || exit 0
B=$(rex split -b "$REX_BLOCK" -s "$REX_SESSION" --split=right --label "Claude usage" --focus=false --keep-open -- "$D/usage_loop.sh" "$sid" 2>/dev/null) || exit 0
sleep 1
# Size the usage pane to the report's 80 columns (split --ratio doesn't take effect; move the border instead).
total=$(rex block call size '{}' -b "$REX_BLOCK" 2>/dev/null | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["columns"])' 2>/dev/null)
other=$(rex block call size '{}' -b "$B" 2>/dev/null | python3 -I -c 'import json,sys; print(json.load(sys.stdin)["columns"])' 2>/dev/null)
if [[ -n "$total" && -n "$other" ]]; then
  ratio=$(python3 -I -c "t=$total+$other+1; r=1-83/t; print(round(min(max(r,0.3),0.9),3))")
  rex api call -s "$REX_SESSION" session.resize_pane "{\"direction\":\"horizontal\",\"before_block_id\":\"$REX_BLOCK\",\"after_block_id\":\"$B\",\"ratio\":$ratio}" >/dev/null 2>&1
fi
# If the work calendar is installed (work-calendar/install.sh), open it above the usage pane
# and give it 40% of the height.
W="$HOME/.config/rex/work-calendar/workcal.py"
if [[ -f "$W" ]] && py=$(command -v python3); then
  C=$(rex split -b "$B" -s "$REX_SESSION" --split=above --label "📅 Work calendar" --focus=false -- "$py" -I "$W" 2>/dev/null)
  if [[ "$C" == block:* ]]; then
    rex api call -s "$REX_SESSION" session.resize_pane "{\"direction\":\"vertical\",\"before_block_id\":\"$C\",\"after_block_id\":\"$B\",\"ratio\":0.4}" >/dev/null 2>&1
  fi
fi
exit 0
