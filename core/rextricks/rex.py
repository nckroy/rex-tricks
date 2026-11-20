"""Thin wrappers over the rex CLI. Failures come back as None or {} rather than exceptions,
because the Claude Code hook must never break Claude's start-up."""
import json, subprocess


def _run(args, timeout):
    try:
        r = subprocess.run(["rex"] + args, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def api(session, method, args, timeout=5):
    out = _run(["api", "call", "-s", session, method, json.dumps(args)], timeout)
    try:
        return json.loads(out) if out and out.strip() else None
    except ValueError:
        return None


def split(session, anchor, direction, label, command, keep_open=False):
    """Open a pane beside `anchor` without taking focus. Returns its block ID, or None."""
    args = ["split", "-s", session, "-b", anchor, f"--split={direction}", "--label", label,
            "--focus=false", "--json"]
    if keep_open:
        args.append("--keep-open")
    out = _run(args + ["--"] + command, 10)
    try:
        return json.loads(out)["block_ids"][0] if out else None
    except (ValueError, KeyError, IndexError, TypeError):
        return None


def size(session, block):
    """The block's terminal size: {"columns", "rows", "owner", ...}, or {} if unknown.
    Until an app lays the pane out, it reports a default 80x24 with no owner."""
    return api(session, "block.method", {"block_id": block, "method": "size"}, timeout=3) or {}


def resize(session, direction, before, after, ratio):
    """Move the border between two blocks: `before` gets `ratio` of the split holding both.
    Returns None if the server refused."""
    return api(session, "session.resize_pane", {"direction": direction, "before_block_id": before,
                                         "after_block_id": after, "ratio": round(ratio, 4)})


def view(session):
    return api(session, "session.view", {}) or {}
