#!/bin/zsh
# Claude Code SessionStart hook: inside Rex, open the rex-tricks column of panes to the
# right of Claude's pane. The panes, their order and sizes come from
# ~/.config/rex-tricks/config.json (see 'rex-tricks column').
# Reads the hook JSON on stdin for session_id. Does nothing outside Rex. Never blocks startup.
[[ -n "$REX_SESSION" && -n "$REX_BLOCK" ]] || exit 0
command -v rex >/dev/null || exit 0
py=$(command -v python3) || exit 0
"$py" -I "${0:A:h}/../bin/rex-tricks" claude-hook 2>>"${TMPDIR:-/tmp}/rex-tricks-column.log"
exit 0
