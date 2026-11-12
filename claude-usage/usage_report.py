#!/usr/bin/env python3
"""Claude Code usage from local transcripts (~/.claude/projects/**/*.jsonl), in color.

Usage: usage_report.py SESSION_ID      (set NO_COLOR=1 to disable color)
Token counts come from each assistant message's `usage` block, de-duplicated by
message id (streamed responses are logged more than once). The 5-hour window is
reconstructed the way ccusage does it: a block starts at the hour floor of the first
message after a 5h+ gap and lasts 5 hours. This is an estimate from local logs; it is
not Anthropic's server-side limit meter (run /usage in Claude Code for that).
"""
import json, sys, glob, os
from datetime import datetime, timedelta, timezone
from collections import defaultdict

SESSION = sys.argv[1] if len(sys.argv) > 1 else ""
ROOT = os.path.expanduser("~/.claude/projects")
HOME_SLUG = os.path.expanduser("~").replace("/", "-")  # how Claude Code names project dirs, e.g. -Users-me
NOW = datetime.now(timezone.utc)
LOCAL = datetime.now().astimezone().tzinfo
W = 80
NO_COLOR = bool(os.environ.get("NO_COLOR"))


def c(code, text):
    return text if NO_COLOR else "\033[" + code + "m" + text + "\033[0m"


def H(t): return c("1;36", t)       # headings: bold cyan
def LBL(t): return c("37", t)       # labels
def NUM(t): return c("1;97", t)     # numbers
def DIM(t): return c("2", t)        # secondary text


RULE = DIM("─" * W)
ROW_COLORS = {
    "Input (uncached)": "35", "Cache writes": "33", "Cache reads": "34",
    "Output": "32", "  of which thinking": "2;32", "Total tokens": "1;97",
}


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def load():
    entries, seen = [], set()
    cutoff = NOW - timedelta(hours=12)
    for fpath in glob.glob(os.path.join(ROOT, "**", "*.jsonl"), recursive=True):
        try:
            if datetime.fromtimestamp(os.path.getmtime(fpath), timezone.utc) < cutoff:
                continue
            for line in open(fpath, encoding="utf-8", errors="replace"):
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("type") != "assistant":
                    continue
                m = d.get("message") or {}
                u = m.get("usage")
                if not u or not d.get("timestamp"):
                    continue
                key = (m.get("id"), d.get("requestId"))
                if key in seen:
                    continue
                seen.add(key)
                stu = u.get("server_tool_use")
                entries.append({
                    "t": ts(d["timestamp"]),
                    "session": d.get("sessionId") or os.path.basename(fpath).split(".")[0],
                    "file": fpath,
                    "side": bool(d.get("isSidechain")),
                    "model": m.get("model") or "?",
                    "in": u.get("input_tokens", 0) or 0,
                    "out": u.get("output_tokens", 0) or 0,
                    "think": (u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0,
                    "cw": u.get("cache_creation_input_tokens", 0) or 0,
                    "cr": u.get("cache_read_input_tokens", 0) or 0,
                    "web": sum(v for v in stu.values() if isinstance(v, int)) if isinstance(stu, dict) else 0,
                })
        except OSError:
            continue
    return sorted(entries, key=lambda e: e["t"])


def blocks(entries):
    out, cur = [], None
    for e in entries:
        if cur is None or e["t"] >= cur["end"] or (cur["items"] and e["t"] - cur["items"][-1]["t"] >= timedelta(hours=5)):
            start = e["t"].replace(minute=0, second=0, microsecond=0)
            cur = {"start": start, "end": start + timedelta(hours=5), "items": []}
            out.append(cur)
        cur["items"].append(e)
    return out


def tot(items):
    t = defaultdict(int)
    for e in items:
        for k in ("in", "out", "think", "cw", "cr", "web"):
            t[k] += e[k]
    t["n"] = len(items)
    t["all"] = t["in"] + t["out"] + t["cw"] + t["cr"]
    return t


def f(n):
    return f"{n:,}"


def hm(td):
    s = max(0, int(td.total_seconds()))
    return f"{s // 3600}h {s % 3600 // 60:02d}m"


def loc(dt):
    return dt.astimezone(LOCAL).strftime("%H:%M")


def row(label, value, color="97", lw=26, vw=16):
    return "  " + LBL(label.ljust(lw)) + c(color, value.rjust(vw))


def table(t):
    rows = [
        ("Requests (API calls)", f(t["n"])),
        ("Input (uncached)", f(t["in"])),
        ("Cache writes", f(t["cw"])),
        ("Cache reads", f(t["cr"])),
        ("Output", f(t["out"])),
        ("  of which thinking", f(t["think"])),
        ("Total tokens", f(t["all"])),
    ]
    if t["web"]:
        rows.append(("Server tool calls (web)", f(t["web"])))
    return "\n".join(row(a, b, ROW_COLORS.get(a, "97")) for a, b in rows)


def ctx(e):
    # tokens the request carried: uncached input + cache reads + cache writes
    return e["in"] + e["cr"] + e["cw"]


def context_stats(items):
    main = [e for e in items if not e["side"]] or items
    series = [ctx(e) for e in main]
    drops = sum(1 for a, b in zip(series, series[1:]) if a > 0 and b < a * 0.5)
    return {"now": series[-1], "peak": max(series), "first": series[0], "series": series, "compactions": drops}


SPARK = "▁▂▃▄▅▆▇█"


def spark(series, width=40):
    if not series:
        return ""
    n = len(series)
    pts = series if n <= width else [series[round(i * (n - 1) / (width - 1))] for i in range(width)]
    hi = max(pts) or 1
    return "".join(SPARK[min(7, int(v / hi * 7))] for v in pts)


def bar(frac, width=40):
    frac = min(max(frac, 0), 1)
    n = int(round(frac * width))
    col = "32" if frac < 0.5 else ("33" if frac < 0.8 else "31")
    return c(col, "█" * n) + DIM("░" * (width - n))


entries = load()
title = f" CLAUDE USAGE · updated {datetime.now().strftime('%a %b %d %H:%M:%S %Z').strip()} "
print(c("1;97;45", title.center(W)))
print(RULE)

# ---- this session
sess = [e for e in entries if SESSION and (e["session"] == SESSION or SESSION in e["file"])]
print("\n" + H("THIS SESSION") + "  " + DIM(SESSION[:8] + "…"))
if sess:
    side = [e for e in sess if e["side"]]
    span = hm(sess[-1]["t"] - sess[0]["t"])
    print("  " + LBL("Span:") + " " + NUM(loc(sess[0]["t"])) + " → " + NUM(loc(sess[-1]["t"])) + "  " + DIM("(" + span + ")"))
    t = tot(sess)
    print(table(t))
    denom = t["cr"] + t["cw"] + t["in"]
    if denom:
        rate = t["cr"] / denom
        print(row("Cache hit rate (input side)", f"{rate:.1%}", "1;32" if rate >= 0.8 else "1;33", 27, 15))
    cs = context_stats(sess)
    print("\n  " + H("Context") + DIM(" (tokens carried by the latest main-thread request)"))
    print(row("Current context", f(cs["now"]), "1;96"))
    print(row("Peak this session", f(cs["peak"]), "96"))
    print(row("At first request", f(cs["first"]), "2;96"))
    if cs["compactions"]:
        print(row("Likely compactions", str(cs["compactions"]), "1;33"))
    print("    " + c("96", spark(cs["series"])) + DIM("  growth over the session"))
    print(DIM("    /context in Claude Code shows this as a % of the model's window."))
    by_model = defaultdict(list)
    for e in sess:
        by_model[e["model"]].append(e)
    print("\n  " + H("By model"))
    for mname, its in sorted(by_model.items(), key=lambda kv: -len(kv[1])):
        tt = tot(its)
        print("    " + c("95", mname.ljust(28)) + NUM(f(tt["n"]).rjust(6)) + DIM(" req  ")
              + c("32", f(tt["out"]).rjust(10)) + DIM(" out  ") + NUM(f(tt["all"]).rjust(13)) + DIM(" total"))
    if side:
        print("\n  " + LBL("Subagent (sidechain) requests:") + " " + NUM(f(len(side))) + DIM(" · ") + NUM(f(tot(side)["all"])) + DIM(" tokens"))
    print("\n  " + H("Output tokens by hour") + DIM(" (local)"))
    hours = defaultdict(int)
    for e in sess:
        hours[e["t"].astimezone(LOCAL).strftime("%H:00")] += e["out"]
    peak = max(hours.values()) or 1
    for h, v in sorted(hours.items()):
        print("    " + LBL(h) + "  " + c("32", "█" * int(round(v / peak * 40))) + DIM("░" * (40 - int(round(v / peak * 40)))) + " " + NUM(f(v)))
    print("\n  " + H("Largest context additions") + DIM(" (cache write + uncached input)"))
    for e in sorted(sess, key=lambda e: -(e["cw"] + e["in"]))[:3]:
        print("    " + LBL(loc(e["t"])) + "  " + c("33", f(e["cw"] + e["in"]).rjust(10)) + DIM(" tokens"))
else:
    print(DIM("  No usage records found for this session yet."))

# ---- 5-hour window
print("\n" + RULE)
bl = blocks(entries)
active = bl[-1] if bl and NOW < bl[-1]["end"] else None
print("\n" + H("CURRENT 5-HOUR WINDOW") + DIM("  (reconstructed from local logs, all sessions)"))
if active:
    start, end = active["start"], active["end"]
    el, rem = NOW - start, end - NOW
    frac = el / timedelta(hours=5)
    print("  " + LBL("Window:") + " " + NUM(loc(start)) + " → " + NUM(loc(end)) + "   " + LBL("elapsed ") + NUM(hm(el))
          + DIM(" · ") + LBL("remaining ") + c("1;32" if rem > timedelta(hours=1) else "1;31", hm(rem)))
    print("  " + bar(frac, 60) + " " + NUM(f"{frac:.0%}"))
    t = tot(active["items"])
    print(table(t))
    mins = max(1, (active["items"][-1]["t"] - active["items"][0]["t"]).total_seconds() / 60)
    print(row("Output rate (tokens/min)", f(int(t["out"] / mins)), "32"))
    print(row("New input/min (uncached+writes)", f(int((t["in"] + t["cw"]) / mins)), "33", 32, 10))
    print(row("Requests/min", f"{t['n'] / mins:.1f}", "1;97"))
    print(DIM(f"  (rates over {hm(timedelta(minutes=mins))} of activity in this window)"))
    per = defaultdict(list)
    for e in active["items"]:
        per[e["session"]].append(e)
    print("\n  " + H("Sessions in this window") + " " + NUM(str(len(per))) + DIM("  (ctx = current context per session)"))
    for sid, its in sorted(per.items(), key=lambda kv: -tot(kv[1])["all"]):
        tt = tot(its)
        proj = os.path.basename(os.path.dirname(its[0]["file"])).replace(HOME_SLUG, "~").replace("-", "/") or "?"
        mark = c("1;35", "  ← this session") if sid == SESSION else ""
        cnow = context_stats(its)["now"]
        print("    " + c("36", sid[:8]) + "  " + NUM(f(tt["n"]).rjust(5)) + DIM(" req ") + NUM(f(tt["all"]).rjust(12))
              + DIM(" tok ") + c("96", f(cnow).rjust(8)) + DIM(" ctx  ") + LBL(proj[:16]) + mark)
else:
    print(DIM("  No active window: no Claude usage in the last 5 hours."))
if len(bl) > 1:
    prev = bl[-2] if active else bl[-1]
    print("\n  " + LBL("Previous window:") + " " + NUM(prev["start"].astimezone(LOCAL).strftime("%a %H:%M")) + " → "
          + NUM(loc(prev["end"])) + DIM(" · ") + NUM(f(tot(prev["items"])["all"])) + DIM(" tokens"))

print("\n" + RULE)
for line in (
    "  Notes: counts come from the local session logs on this Mac only (usage on",
    "  other machines or claude.ai isn't included). Anthropic doesn't publish the",
    "  plan limit in tokens, so this can't show % of your limit. Run /usage in",
    "  Claude Code for the server's own limit status. Refreshes every 30 s.",
):
    print(DIM(line))
