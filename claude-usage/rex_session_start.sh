#!/bin/zsh
# Claude Code SessionStart hook: inside Rex, open the usage pane to the right of Claude's pane,
# with the work calendar above it when that is installed, and btop between the two.
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
    rex api call -s "$REX_SESSION" session.resize_pane "{\"direction\":\"vertical\",\"before_block_id\":\"$C\",\"after_block_id\":\"$B\",\"ratio\":0.35}" >/dev/null 2>&1
  fi
fi
# btop in the middle: split above the usage pane, so it lands below the calendar (if any).
# It takes 45% of what's left under the calendar (~30% of the column overall), or more if btop
# would otherwise be too short to draw anything (see below).
if bt=$(command -v btop || { [[ -x /opt/homebrew/bin/btop ]] && echo /opt/homebrew/bin/btop; }); then
  T=$(rex split -b "$B" -s "$REX_SESSION" --split=above --label "btop" --focus=false -- "$bt" 2>/dev/null)
  if [[ "$T" == block:* ]]; then
    rex api call -s "$REX_SESSION" session.resize_pane "{\"direction\":\"vertical\",\"before_block_id\":\"$T\",\"after_block_id\":\"$B\",\"ratio\":0.45}" >/dev/null 2>&1
    # btop shows only "Terminal size too small" below its minimum (80x24 with the default
    # cpu/mem/net/proc boxes). If the proportions above leave it shorter, take rows from the
    # usage pane, then the calendar, keeping each at least REX_PANE_MIN_ROWS. Rows don't map
    # exactly to ratios (each pane has a label bar), so measure, resize and measure again.
    python3 -I - "$REX_SESSION" "$T" "$B" "${C:-}" "${REX_BTOP_MIN_ROWS:-24}" "${REX_PANE_MIN_ROWS:-8}" <<'PY' 2>/dev/null
import json, subprocess, sys, time
sess, T, B, C, need, keep = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] or None, int(sys.argv[5]), int(sys.argv[6])

def call(method, args):
    out = subprocess.run(["rex", "api", "call", "-s", sess, method, json.dumps(args)],
                         capture_output=True, text=True, timeout=3).stdout
    return json.loads(out) if out.strip() else None

def size(b):
    return call("block.method", {"block_id": b, "method": "size"})

def leaves(node):
    if "split" in node:
        yield from leaves(node["split"]["before"])
        yield from leaves(node["split"]["after"])
    else:
        yield node

def heights():
    # Each tiled pane's height as a fraction of the window, from the window that holds btop.
    for w in call("session.view", {})["windows"]:
        for layer in w["layers"]:
            if layer["kind"] == "tiled":
                hs = {l["block_id"]: l["rect"][3] for l in leaves(layer["layout"])}
                if T in hs:
                    return hs
    return {}

def resize(before, after, ratio):
    call("session.resize_pane", {"direction": "vertical", "before_block_id": before,
                                 "after_block_id": after, "ratio": round(min(max(ratio, 0.02), 0.98), 4)})

# Until the app lays a pane out, it reports a default 80x24 with no owner, which would pass
# for big enough. Wait for real sizes; with no app showing the window there's nothing to fit.
col = [x for x in (C, T, B) if x]
for _ in range(20):
    if all(size(x)["owner"] for x in col):
        break
    time.sleep(0.1)
else:
    sys.exit(0)
time.sleep(0.2)

bump = 0.0
for _ in range(4):
    hs = heights()
    rows = {b: size(b)["rows"] for b in hs}
    if rows[T] >= need or not all(x in hs for x in col):
        break
    # A pane gets about H*h - oh rows: H is the window's height in rows and oh the rows its
    # label bar and border take. Fit both from every pane in the window (least squares).
    pts = [(hs[b], rows[b]) for b in hs]
    n = len(pts); mh = sum(h for h, _ in pts) / n; mr = sum(r for _, r in pts) / n
    var = sum((h - mh) ** 2 for h, _ in pts)
    if var < 1e-6:
        # All panes the same height: assume a 1-row overhead.
        oh = 1.0; H = (mr + oh) / mh
    else:
        H = sum((h - mh) * (r - mr) for h, r in pts) / var; oh = H * mh - mr
    if H <= 0:
        break
    frac = lambda r: (r + oh + 0.5) / H + bump   # height that gives at least r rows
    hT, hB, hC = hs[T], hs[B], hs[C] if C else 0.0
    want = frac(need) - hT
    from_b = max(0.0, min(want, hB - frac(keep)))
    from_c = max(0.0, min(want - from_b, hC - frac(keep))) if C else 0.0
    if from_b + from_c <= 1e-4:
        break  # the column is too short for btop's minimum; leave it as big as it can be
    hT += from_b + from_c; hB -= from_b; hC -= from_c
    if C and from_c:
        resize(C, B, hC / (hC + hT + hB))  # the calendar's share of the whole column
    resize(T, B, hT / (hT + hB))             # btop's share of the btop/usage split
    time.sleep(0.5)
    bump += 0.5 / H                          # if rounding still leaves it short, aim a little higher
PY
  fi
fi
exit 0
