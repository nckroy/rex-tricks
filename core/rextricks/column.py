"""The column of panes that opens to the right of Claude Code when it starts.

`open_column` runs inside the Claude Code SessionStart hook, which has a 10-second
timeout, so it only opens the panes and sets their proportions. Making panes at least
their `min_rows` tall needs the sizes the Rex app gives them, which can take several
seconds after a cold start, so `fit` runs detached afterwards.
"""
import json, os, subprocess, sys, time
from . import ROOT, config, rex
from .manifest import which
from .registry import Registry

LOG = os.path.join(os.environ.get("TMPDIR") or "/tmp", "rex-tricks-column.log")


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, file=sys.stderr, flush=True)


# ---- pure layout math (unit tested) ---------------------------------------------------

def ratios(heights):
    """Nested split ratios for panes stacked top to bottom. Pane i and everything below it
    share one split, so pane i's ratio is its height over the height of pane i and below."""
    return [heights[i] / sum(heights[i:]) for i in range(len(heights) - 1)]


def fit_rows(pts):
    """Given (height as a fraction of the window, rows) for each pane in a window, fit
    rows ~= H*h - oh: H is the window's height in rows, oh the rows a pane's label bar and
    border take. Least squares; with every pane the same height, assume oh = 1."""
    n = len(pts)
    mh = sum(h for h, _ in pts) / n
    mr = sum(r for _, r in pts) / n
    var = sum((h - mh) ** 2 for h, _ in pts)
    if var < 1e-6:
        oh = 1.0
        return (mr + oh) / mh, oh
    H = sum((h - mh) * (r - mr) for h, r in pts) / var
    return H, H * mh - mr


def plan(heights, rows, mins, floor, H, oh, bump=0.0):
    """New heights (fractions of the window) that give every pane its minimum rows, taking
    the room from the other panes, bottom pane first, down to max(floor, their own minimum).
    Returns None when nothing can move."""
    frac = lambda r: (r + oh + 0.5) / H + bump   # height that gives at least r rows
    new = list(heights)
    moved = False
    for i in range(len(new)):
        if rows[i] >= mins[i]:
            continue
        want = frac(mins[i]) - new[i]
        for j in reversed(range(len(new))):
            if j == i or want <= 1e-4:
                continue
            give = max(0.0, min(want, new[j] - frac(max(floor, mins[j]))))
            if give > 1e-4:
                new[j] -= give
                new[i] += give
                want -= give
                moved = True
    return new if moved else None


def expand(command, plugin, claude_session_id="", rex_session=""):
    subs = {"{dir}": plugin.dir, "{python}": sys.executable,
            "{claude_session_id}": claude_session_id, "{rex_session}": rex_session}
    out = []
    for word in command:
        for k, v in subs.items():
            word = word.replace(k, v)
        out.append(word)
    # Resolve a bare program name now: the hook's PATH may differ from the pane's.
    if "/" not in out[0]:
        out[0] = which(out[0]) or out[0]
    return out


# ---- opening the column -----------------------------------------------------------------

def column_panes(cfg, reg):
    """[(plugin, pane, env)] for the panes to open, top to bottom."""
    out = []
    enabled = set(cfg.get("enabled") or [])
    for name in cfg["column"]["panes"]:
        p = reg.plugins.get(name)
        if p is None or name not in enabled or not p.pane:
            log(f"skipping '{name}': not installed, not enabled or not a pane")
            continue
        missing = p.missing()
        if missing:
            log(f"skipping '{name}': needs {', '.join(missing)}")
            continue
        out.append((p, config.effective_pane(p, cfg), config.effective_settings(p, cfg)))
    return out


def open_column(session, block, claude_session_id):
    cfg = config.load()
    panes = column_panes(cfg, Registry())
    built = []  # (block id, pane)
    before = rex.size(session, block)  # Claude's pane, normally laid out already
    total = before.get("columns") if before.get("owner") else None
    for p, pane, env in panes:
        cmd = expand(pane["command"], p, claude_session_id, session)
        if env:
            cmd = ["/usr/bin/env"] + [f"{k}={v}" for k, v in sorted(env.items())] + cmd
        if not built:
            b = rex.split(session, block, "right", pane["label"], cmd, pane["keep_open"])
            if not b:
                log(f"couldn't open '{p.name}' beside {block}")
                return
        else:
            b = rex.split(session, built[-1][0], "below", pane["label"], cmd, pane["keep_open"])
            if not b:
                log(f"couldn't open '{p.name}'")
                continue
        built.append((b, pane))
    if not built:
        return
    blocks = [b for b, _ in built]
    # Width: split --ratio doesn't take effect, so move the border. Done after the vertical
    # splits, and retried, because a pane rex split just returned isn't always resizable yet.
    if total:
        r = 1 - int(cfg["column"].get("width", 83)) / total
        resize(session, "horizontal", block, blocks[0], min(max(r, 0.3), 0.9))
    else:
        log("Claude's pane has no size yet; leaving the column's width as Rex made it")
    for i, r in enumerate(ratios([pane["height"] for _, pane in built])):
        resize(session, "vertical", blocks[i], blocks[i + 1], r)
    mins = [int(pane["min_rows"]) for _, pane in built]
    spawn_fit(session, block, int(cfg["column"].get("width", 83)), blocks, mins,
              config.column_min_rows(cfg))


def resize(session, direction, before, after, ratio, tries=10):
    for _ in range(tries):
        if rex.resize(session, direction, before, after, ratio) is not None:
            return True
        time.sleep(0.2)
    log(f"couldn't move the {direction} border between {before} and {after}")
    return False


def spawn_fit(session, anchor, width, blocks, mins, floor):
    args = json.dumps({"session": session, "anchor": anchor, "width": width, "blocks": blocks,
                       "mins": mins, "floor": floor})
    with open(LOG, "a") as err:
        subprocess.Popen([sys.executable, "-I", os.path.join(ROOT, "bin", "rex-tricks"), "column-fit", args],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err,
                         start_new_session=True)


# ---- fitting minimum rows (detached) ------------------------------------------------------

def leaves(node):
    if "split" in node:
        yield from leaves(node["split"]["before"])
        yield from leaves(node["split"]["after"])
    else:
        yield node


def split_ratio(node, before, after):
    """The ratio of the split with `before` on one side and `after` on the other, or None."""
    if "split" not in node:
        return None
    sp = node["split"]
    ids = lambda n: {l["block_id"] for l in leaves(n)}
    if before in ids(sp["before"]) and after in ids(sp["after"]):
        return sp["ratio"]
    return split_ratio(sp["before"], before, after) or split_ratio(sp["after"], before, after)


def layout_of(session, block):
    for w in rex.view(session).get("windows", []):
        for layer in w.get("layers", []):
            if layer.get("kind") == "tiled" and block in {l["block_id"] for l in leaves(layer["layout"])}:
                return layer["layout"]
    return {}


def window_heights(session, block):
    """Each tiled pane's height as a fraction of the window, in the window holding `block`."""
    for w in rex.view(session).get("windows", []):
        for layer in w.get("layers", []):
            if layer.get("kind") == "tiled":
                hs = {l["block_id"]: l["rect"][3] for l in leaves(layer["layout"])}
                if block in hs:
                    return hs
    return {}


def wait_for_layout(session, blocks, timeout=30):
    """Wait until the app has sized every block (it has an owner) and the sizes have stopped
    changing. After a cold start of Rex that took about 8 seconds."""
    deadline, prev = time.time() + timeout, None
    while True:
        s = [rex.size(session, b) for b in blocks]
        cur = [(x.get("rows"), x.get("columns")) for x in s] if all(x.get("owner") for x in s) else None
        if cur and cur == prev:
            return True
        if time.time() > deadline:
            return False
        prev = cur
        time.sleep(0.5)


def fit_width(session, anchor, first, width):
    """Check the column's width against the laid-out sizes and fix it. When the hook ran,
    Claude's pane may have reported a stale width (just after a layout change)."""
    a, c = rex.size(session, anchor).get("columns"), rex.size(session, first).get("columns")
    current = split_ratio(layout_of(session, anchor), anchor, first)
    if not (a and c and current):
        return
    want = min(max(1 - width / (a + c + 1), 0.3), 0.9)
    if abs(want - current) > 0.01:
        log(f"column width off ({c} columns); moving the border from {current:.3f} to {want:.3f}")
        resize(session, "horizontal", anchor, first, want)
        time.sleep(0.5)
        wait_for_layout(session, [anchor, first], timeout=5)


def fit(session, blocks, mins, floor, anchor=None, width=None):
    if not wait_for_layout(session, ([anchor] if anchor else []) + blocks):
        log("no app laid the column out within 30s; leaving it as it is")
        return
    if anchor and width:
        fit_width(session, anchor, blocks[0], width)
    if len(blocks) < 2 or not any(mins):
        return
    bump = 0.0
    for _ in range(4):
        hs = window_heights(session, blocks[0])
        if not all(b in hs for b in blocks):
            return
        rows = {b: rex.size(session, b).get("rows") for b in hs}
        if any(rows[b] is None for b in blocks):
            return
        col_rows = [rows[b] for b in blocks]
        if all(r >= m for r, m in zip(col_rows, mins)):
            return
        H, oh = fit_rows([(hs[b], r) for b, r in rows.items() if r])
        if H <= 0:
            return
        new = plan([hs[b] for b in blocks], col_rows, mins, floor, H, oh, bump)
        if not new:
            log(f"column too short for minimums {mins}; rows are {col_rows}")
            return  # leave each pane as big as it can be
        for i, r in enumerate(ratios(new)):
            resize(session, "vertical", blocks[i], blocks[i + 1], min(max(r, 0.02), 0.98))
        time.sleep(0.5)
        bump += 0.5 / H  # if rounding still leaves a pane short, aim a little higher
