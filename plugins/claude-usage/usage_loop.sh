#!/bin/zsh
# Refreshing Claude usage view for one session. Usage: usage_loop.sh SESSION_ID
D=${0:A:h}
while true; do
  out=$(python3 -I "$D/usage_report.py" "$1" 2>&1)
  clear; print -r -- "$out"
  sleep 30
done
