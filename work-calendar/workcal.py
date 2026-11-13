#!/usr/bin/env python3
"""Text-mode work calendar for a Rex pane, fed by Claude's Microsoft 365 connector.

Usage:
  workcal.py                     interactive calendar (curses)
  workcal.py --fetch [MONDAY]    fetch one week (default: this week), print the events as JSON
  workcal.py --agenda [DATE]     print one day's agenda as plain text and exit
  workcal.py --demo              interactive calendar with made-up events (no fetching), for screenshots

No program outside Claude can call a claude.ai connector, so a fetch runs a headless
`claude -p`. That run can use only the connector's outlook_calendar_search tool (all
built-in tools are off), makes its page requests in parallel in a single turn, and is
stopped by --max-turns 1 before the model reads the results. The events come from
the raw tool results in the stream-json output, not from anything the model writes.
Each event carries its position in the result set (`offset`), so a fetch can tell
whether it got every page and asks again for any that are missing.

Events are cached per week in ~/Library/Caches/rex-work-calendar (mode 600).

Environment:
  WORKCAL_REFRESH_MIN   minutes between automatic refreshes of the week shown (default 15)
  WORKCAL_CLAUDE        claude binary (default: claude on PATH)
  WORKCAL_MODEL         model for the fetch run (default: haiku)
  NO_COLOR              disable color
"""
import fcntl, json, os, re, subprocess, sys, threading, time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TOOL = "mcp__claude_ai_Microsoft_365__outlook_calendar_search"
PAGE = 15                 # events per page; bigger pages get spilled to a file instead of returned inline
FIRST_PAGES = 7           # pages requested on the first try (covers 105 events in a week)
CACHE = os.path.expanduser("~/Library/Caches/rex-work-calendar")
REFRESH_MIN = float(os.environ.get("WORKCAL_REFRESH_MIN", "15") or 15)
CLAUDE = os.environ.get("WORKCAL_CLAUDE", "claude")
MODEL = os.environ.get("WORKCAL_MODEL", "haiku")
RETRY_SEC = 120           # minimum gap between automatic fetch attempts for one week


def local_zone():
    # A named zone, not today's fixed offset, so times stay right across a DST change.
    try:
        return ZoneInfo(os.path.realpath("/etc/localtime").split("zoneinfo/", 1)[1])
    except Exception:
        return datetime.now().astimezone().tzinfo


LOCAL = local_zone()

# Graph labels times with Windows zone names. Unknown names are treated as local time.
WINDOWS_TZ = {
    "UTC": "UTC", "Coordinated Universal Time": "UTC", "GMT Standard Time": "Europe/London",
    "Eastern Standard Time": "America/New_York", "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver", "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles", "Alaskan Standard Time": "America/Anchorage",
    "Hawaiian Standard Time": "Pacific/Honolulu", "Atlantic Standard Time": "America/Halifax",
    "W. Europe Standard Time": "Europe/Berlin", "Romance Standard Time": "Europe/Paris",
    "Central European Standard Time": "Europe/Warsaw", "Tokyo Standard Time": "Asia/Tokyo",
    "AUS Eastern Standard Time": "Australia/Sydney", "India Standard Time": "Asia/Kolkata",
}


# ---------------------------------------------------------------- fetching

def monday(d):
    return d - timedelta(days=d.weekday())


def iso(d):
    return d.strftime("%Y-%m-%dT00:00:00")


def run_claude(start, end, offsets):
    """One headless run that requests the given pages. Returns (events, total, error)."""
    calls = ", ".join(str(o) for o in offsets)
    prompt = (
        f"In a single response, make {len(offsets)} outlook_calendar_search calls in parallel, "
        f"all with query '*', afterDateTime {iso(start)}, beforeDateTime {iso(end)}, order oldest, "
        f"limit {PAGE}, and offset {calls} respectively (one call per offset). Do nothing else."
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("REX_")}  # keep Rex hooks from opening panes
    os.makedirs(CACHE, mode=0o700, exist_ok=True)
    cmd = [CLAUDE, "-p", "--model", MODEL, "--output-format", "stream-json", "--verbose",
           "--tools", "", "--no-session-persistence", "--max-turns", "1", "--allowedTools", TOOL]
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, cwd=CACHE, timeout=180)
    except FileNotFoundError:
        return [], None, f"{CLAUDE} not found"
    except subprocess.TimeoutExpired:
        return [], None, "claude timed out"
    want = {"afterDateTime": iso(start), "beforeDateTime": iso(end)}
    good_calls, events, total, errors = set(), [], None, []
    for line in p.stdout.splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        content = (msg.get("message") or {}).get("content") or []
        if msg.get("type") == "assistant":
            for c in content:
                if c.get("type") == "tool_use" and c.get("name") == TOOL:
                    a = c.get("input") or {}
                    if all(a.get(k) == v for k, v in want.items()) and a.get("query") in ("*", "", None):
                        good_calls.add(c.get("id"))
        elif msg.get("type") == "user":
            for c in content:
                if c.get("type") != "tool_result" or c.get("tool_use_id") not in good_calls:
                    continue
                body = c.get("content")
                if isinstance(body, str) or c.get("is_error"):
                    errors.append(str(body)[:200])
                    continue
                for part in body or []:
                    try:
                        item = json.loads(part.get("text", ""))
                    except ValueError:
                        errors.append(part.get("text", "")[:200])
                        continue
                    if "uri" in item:
                        events.append(item)
                    if "totalResultCount" in item:
                        total = item["totalResultCount"]
    if not good_calls:
        tail = (p.stderr or p.stdout).strip().splitlines()[-1:] or [f"exit {p.returncode}"]
        return [], None, "no calendar calls: " + tail[0][:200]
    return events, total, "; ".join(errors) or None


def fetch_week(mon):
    """All events overlapping the week starting at Monday `mon`, or raise RuntimeError."""
    start, end = mon, mon + timedelta(days=7)
    by_offset, total, offsets = {}, None, [i * PAGE for i in range(FIRST_PAGES)]
    for _ in range(4):
        events, t, err = run_claude(start, end, offsets)
        for e in events:
            by_offset[e.get("offset")] = e
        total = t if t is not None else total
        if total is None:
            raise RuntimeError(err or "no result count from the connector")
        missing = sorted({(o // PAGE) * PAGE for o in range(total) if o not in by_offset})
        if not missing:
            break
        offsets = missing
    else:
        raise RuntimeError(f"got {len(by_offset)} of {total} events")
    out = [normalize(by_offset[o]) for o in range(total)]
    out = [e for e in out if e]
    return {"week": mon.isoformat(), "fetched": time.time(), "events": out}


def to_local(dt_str, tz_name):
    dt = datetime.fromisoformat(dt_str[:19])
    tz = WINDOWS_TZ.get(tz_name)
    if tz_name and not tz:
        try:
            tz = ZoneInfo(tz_name).key
        except Exception:
            tz = None
    return dt.replace(tzinfo=ZoneInfo(tz) if tz else LOCAL).astimezone(LOCAL).replace(tzinfo=None)


def normalize(e):
    try:
        s, en = e["start"], e["end"]
        all_day = bool(e.get("isAllDay"))
        if all_day:
            start, end = datetime.fromisoformat(s["dateTime"][:10]), datetime.fromisoformat(en["dateTime"][:10])
        else:
            start, end = to_local(s["dateTime"], s.get("timeZone")), to_local(en["dateTime"], en.get("timeZone"))
    except (KeyError, TypeError, ValueError):
        return None
    loc = (e.get("location") or "").strip()
    link = next(iter(re.findall(r"https?://\S+", loc)), "")
    return {
        "id": e.get("id"), "subject": (e.get("subject") or "(no title)").strip(),
        "start": start.isoformat(), "end": end.isoformat(), "allDay": all_day,
        "showAs": e.get("showAs") or "busy", "cancelled": bool(e.get("isCancelled")),
        "location": "" if link else loc, "link": link, "webLink": e.get("webLink") or "",
        "organizer": e.get("organizerName") or "", "isOrganizer": bool(e.get("isOrganizer")),
        "attendees": len(e.get("attendees") or []),
    }


def cache_path(mon):
    return os.path.join(CACHE, f"week-{mon.isoformat()}.json")


def load_cache(mon):
    try:
        with open(cache_path(mon)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_cache(data):
    os.makedirs(CACHE, mode=0o700, exist_ok=True)
    path = cache_path(date.fromisoformat(data["week"]))
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.replace(tmp, path)


# ---------------------------------------------------------------- model

def clean(s):
    """One line of text: control characters and runs of whitespace (newlines too) become one space."""
    return re.sub(r"[\s\x00-\x1f\x7f]+", " ", s or "").strip()


def clip(s, n):
    return s if len(s) <= n else s[: max(0, n - 1)] + "…" if n > 0 else ""


def parse(e):
    e = dict(e)
    for k in ("subject", "location", "organizer"):
        e[k] = clean(e.get(k))
    e["s"], e["e"] = datetime.fromisoformat(e["start"]), datetime.fromisoformat(e["end"])
    return e


def day_events(weeks, day):
    """(all_day, timed) events overlapping `day`, from whichever cached week holds it."""
    data = weeks.get(monday(day))
    if not data:
        return None, None
    lo, hi = datetime.combine(day, datetime.min.time()), datetime.combine(day + timedelta(days=1), datetime.min.time())
    evs = [parse(e) for e in data["events"]]
    evs = [e for e in evs if e["s"] < hi and (e["e"] > lo or e["s"] == e["e"] == lo)]
    all_day = sorted([e for e in evs if e["allDay"]], key=lambda e: (e["s"], e["subject"].lower()))
    timed = sorted([e for e in evs if not e["allDay"]], key=lambda e: (e["s"], e["e"]))
    return all_day, timed


def hm(dt):
    return dt.strftime("%-I:%M").rjust(5) + ("a" if dt.hour < 12 else "p")


def dur(td):
    m = -int(-td.total_seconds() // 60)  # round up, so a meeting 20 seconds away is "in 1m"
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def ago(ts):
    s = time.time() - ts
    return "just now" if s < 60 else f"{int(s // 60)}m ago" if s < 3600 else f"{int(s // 3600)}h ago"


MARK = {"busy": "█", "tentative": "▒", "oof": "◆", "workingElsewhere": "◇", "free": "·"}


# ---------------------------------------------------------------- plain agenda

def print_agenda(day):
    mon = monday(day)
    data = load_cache(mon)
    if not data or time.time() - data["fetched"] > REFRESH_MIN * 60:
        data = fetch_week(mon)
        save_cache(data)
    all_day, timed = day_events({mon: data}, day)
    print(day.strftime("%A %B %-d, %Y"))
    for e in all_day:
        print(f"  all day        {e['subject']}")
    for e in timed:
        x = " (cancelled)" if e["cancelled"] else ""
        print(f"  {(hm(e['s']) + '–' + hm(e['e']).strip()):<14} {MARK.get(e['showAs'], ' ')} {e['subject']}{x}")



# ---------------------------------------------------------------- demo data

DEMO = False

# (weekday, start, minutes, subject, showAs, link?) — made-up events for screenshots.
DEMO_EVENTS = [
    (0, "09:00", 30, "Team standup", "busy", True), (0, "11:00", 60, "Lunch", "busy", False),
    (0, "13:00", 60, "Sprint planning", "busy", True), (0, "15:00", 30, "1:1 with Alex", "busy", True),
    (1, "09:00", 30, "Team standup", "busy", True), (1, "10:00", 90, "Architecture review", "busy", True),
    (1, "14:00", 60, "Vendor demo: log pipeline", "tentative", True),
    (2, "09:00", 30, "Team standup", "busy", True), (2, "12:00", 60, "Lunch & learn: OpenTofu", "busy", True),
    (2, "15:00", 120, "Focus time", "free", False),
    (3, "09:00", 30, "Team standup", "busy", True), (3, "11:00", 60, "Lunch", "busy", False),
    (3, "13:30", 60, "Incident review: DNS outage", "busy", True), (3, "16:00", 30, "Release go/no-go", "busy", True),
    (4, "09:00", 30, "Team standup", "busy", True), (4, "10:00", 60, "Design review: SSO for the portal", "busy", True),
    (4, "11:00", 60, "Lunch", "busy", False), (4, "12:00", 60, "Customer call: Example University", "busy", True),
    (4, "13:00", 30, "1:1 with Sam", "busy", True), (4, "14:00", 90, "Quarterly planning", "busy", True),
    (4, "15:00", 30, "Security office hours", "tentative", True), (4, "16:30", 30, "Timesheets due", "busy", False),
]


def demo_week(mon):
    evs = []
    for n, (wd, hhmm, mins, subj, show, link) in enumerate(DEMO_EVENTS):
        s = datetime.combine(mon + timedelta(days=wd), datetime.strptime(hhmm, "%H:%M").time())
        evs.append({"id": f"demo{n}", "subject": subj, "start": s.isoformat(),
                    "end": (s + timedelta(minutes=mins)).isoformat(), "allDay": False, "showAs": show,
                    "cancelled": False, "location": "", "link": f"https://example.zoom.us/j/{1000 + n}" if link else "",
                    "webLink": "", "organizer": "Example Organizer", "isOrganizer": False, "attendees": 6 if link else 0})
    for d0, d1, subj, show in [(0, 5, "Conference week: TechConf (remote)", "free"), (4, 5, "Pat out of office", "free")]:
        evs.append({"id": subj, "subject": subj, "start": datetime.combine(mon + timedelta(days=d0), datetime.min.time()).isoformat(),
                    "end": datetime.combine(mon + timedelta(days=d1), datetime.min.time()).isoformat(), "allDay": True,
                    "showAs": show, "cancelled": False, "location": "", "link": "", "webLink": "", "organizer": "",
                    "isOrganizer": True, "attendees": 0})
    return {"week": mon.isoformat(), "fetched": time.time(), "events": evs}


# ---------------------------------------------------------------- curses UI

class App:
    def __init__(self, scr):
        import curses
        self.c, self.scr = curses, scr
        self.day = date.today()
        self.weeks = {}            # monday -> cached data
        self.fetching = set()      # mondays being fetched
        self.errors = {}           # monday -> last error
        self.tried = {}            # monday -> time of the last fetch attempt
        self.sel = None            # index into the selectable rows of the day
        self.view = "day"
        self.msg, self.msg_until = "", 0
        self.lock = threading.Lock()
        self.wake = threading.Event()
        curses.curs_set(0)
        scr.timeout(1000)
        self.color = curses.has_colors() and not os.environ.get("NO_COLOR")
        if self.color:
            curses.use_default_colors()
            for i, fg in enumerate([curses.COLOR_CYAN, curses.COLOR_GREEN, curses.COLOR_YELLOW,
                                    curses.COLOR_RED, curses.COLOR_MAGENTA, curses.COLOR_BLUE], 1):
                curses.init_pair(i, fg, -1)

    def a(self, name):
        c = self.c
        if not self.color:
            return {"head": c.A_BOLD, "now": c.A_REVERSE, "sel": c.A_REVERSE, "dim": c.A_DIM}.get(name, 0)
        return {
            "head": c.color_pair(1) | c.A_BOLD, "accent": c.color_pair(1), "now": c.color_pair(4) | c.A_BOLD,
            "cur": c.color_pair(2) | c.A_BOLD, "tent": c.color_pair(3), "oof": c.color_pair(5),
            "dim": c.A_DIM, "sel": c.A_REVERSE, "link": c.color_pair(6), "err": c.color_pair(4),
            "today": c.color_pair(2) | c.A_BOLD,
        }.get(name, 0)

    # data -------------------------------------------------------------
    def ensure(self, mon, force=False):
        if DEMO:
            self.weeks.setdefault(mon, demo_week(mon))
            return
        with self.lock:
            if mon in self.fetching:
                return
            data = self.weeks.get(mon)
            if not data or time.time() - data["fetched"] >= REFRESH_MIN * 60:
                # Another calendar pane may have fetched this week since; use its copy if it's newer.
                cached = load_cache(mon)
                if cached and (not data or cached["fetched"] > data["fetched"]):
                    self.weeks[mon] = data = cached
            fresh = data and time.time() - data["fetched"] < REFRESH_MIN * 60
            # Each attempt is a claude run, so after one fails wait before trying again.
            backoff = time.time() - self.tried.get(mon, 0) < RETRY_SEC
            if not force and (fresh or backoff):
                return
            self.tried[mon] = time.time()
            self.fetching.add(mon)
        threading.Thread(target=self._fetch, args=(mon, force), daemon=True).start()

    def _fetch(self, mon, force):
        asked = time.time()
        try:
            # One fetch per week at a time across every calendar pane: wait for the lock,
            # then skip the fetch if another pane has just written the cache.
            os.makedirs(CACHE, mode=0o700, exist_ok=True)
            with open(os.path.join(CACHE, f"week-{mon.isoformat()}.lock"), "w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                data = load_cache(mon)
                if not data or (data["fetched"] < asked if force else time.time() - data["fetched"] >= REFRESH_MIN * 60):
                    data = fetch_week(mon)
                    save_cache(data)
            with self.lock:
                self.weeks[mon] = data
                self.errors.pop(mon, None)
        except Exception as ex:  # keep showing the cache; report the failure in the header
            with self.lock:
                self.errors[mon] = str(ex) or ex.__class__.__name__
        finally:
            with self.lock:
                self.fetching.discard(mon)
            self.wake.set()

    # drawing ----------------------------------------------------------
    def put(self, y, x, text, attr=0):
        h, w = self.scr.getmaxyx()
        if 0 <= y < h and x < w:
            try:
                self.scr.addnstr(y, x, text, max(0, w - x - (1 if y == h - 1 else 0)), attr)
            except self.c.error:
                pass

    def draw(self):
        scr = self.scr
        scr.erase()
        h, w = scr.getmaxyx()
        now = datetime.now()
        mon = monday(self.day)
        with self.lock:
            data, busy, err = self.weeks.get(mon), mon in self.fetching, self.errors.get(mon)

        # header
        title = "Work calendar"
        status = "fetching…" if busy else ""
        if data:
            status = (status + " " if status else "") + "updated " + ago(data["fetched"])
        if err:
            status = "⚠ " + status
        self.put(0, 1, title, self.a("head"))
        self.put(0, max(len(title) + 3, w - len(status) - 1), status, self.a("err") if err else self.a("dim"))
        clock = now.strftime("%a %b %-d  %-I:%M %p")
        if w > len(title) + len(status) + len(clock) + 8:
            self.put(0, (w - len(clock)) // 2, clock, self.a("accent"))

        # week strip
        days = [mon + timedelta(days=i) for i in range(7)]
        counts = []
        for d in days:
            tm = day_events(self.weeks, d)[1]
            counts.append(len([e for e in (tm or []) if not e["cancelled"]]))
        # widest week strip that fits: " Mon 9·10 ", " Mon 9 ", " Mo9 ", "M9"
        styles = [("%a %-d", True, 1, 2), ("%a %-d", False, 1, 2), ("%a", False, 1, 1), ("", False, 0, 1)]
        for fmt, show_n, pad, gap in styles:
            cells = [(d.strftime(fmt)[:2] + d.strftime("%-d") if fmt == "%a" else d.strftime(fmt) or
                      d.strftime("%a")[0] + d.strftime("%-d"))
                     + (f"·{n}" if n and show_n else "") for d, n in zip(days, counts)]
            if sum(len(s) + 2 * pad for s in cells) + gap * 6 + 1 <= w:
                break
        x, y = 1, 2
        for d, cell in zip(days, cells):
            attr = self.a("sel") if d == self.day else self.a("today") if d == date.today() else (
                self.a("dim") if d.weekday() >= 5 else 0)
            self.put(y, x, " " * pad + cell + " " * pad, attr)
            x += len(cell) + 2 * pad + gap
        self.put(y + 1, 1, "─" * (w - 2), self.a("dim"))
        y += 2

        if self.view == "week":
            self.draw_week(y, h, w, mon, now)
        else:
            self.draw_day(y, h, w, now, data, busy, err)

        # footer
        msg = self.msg if time.time() < self.msg_until else ""
        if err and not msg:
            msg = "fetch failed: " + err
        keys = "←→ day  ↑↓ pick  ⏎ join  o outlook  t today  w week  r refresh  q quit"
        if w < len(keys) + 2:
            keys = "←→ ↑↓ ⏎ o t w r q"
        self.put(h - 1, 1, msg[: w - 2] if msg else keys, self.a("err") if err and msg else self.a("dim"))
        scr.refresh()

    def draw_day(self, y, h, w, now, data, busy, err):
        all_day, timed = day_events(self.weeks, self.day)
        self.put(y, 1, self.day.strftime("%A, %B %-d"), self.a("head"))
        y += 1
        if all_day is None:
            self.put(y + 1, 3, "Fetching this week…" if busy else "No data for this week yet.", self.a("dim"))
            self.rows = []
            return
        for e in all_day[: max(0, (h - y - 6) // 3)]:
            span = ""
            last = (e["e"] - timedelta(days=1)).date()
            if e["s"].date() != last:
                span = f"  ({e['s']:%b %-d}–{last:%b %-d})"
            self.put(y, 3, "◦ " + e["subject"] + span, self.a("oof") if e["showAs"] == "oof" else self.a("dim"))
            y += 1
        y += 1
        self.rows = timed
        if not timed:
            self.put(y, 3, "No meetings.", self.a("dim"))
            return
        if self.sel is not None:
            self.sel = max(0, min(self.sel, len(timed) - 1))
        is_today = self.day == now.date()
        # conflicts: overlaps with another non-cancelled, non-free event
        live = [e for e in timed if not e["cancelled"] and e["showAs"] != "free"]
        clash = {id(e) for e in live for o in live if o is not e and o["s"] < e["e"] and e["s"] < o["e"]}
        lines, now_at = [], None
        for i, e in enumerate(timed):
            if is_today and now_at is None and e["s"] > now:
                now_at = len(lines)
                lines.append(("now", None))
            lines.append(("ev", i))
        if is_today and now_at is None:
            lines.append(("now", None))
        # scroll so the selected row, or else the now line, stays visible
        room = h - 2 - y - 1
        focus = next((k for k, (t, i) in enumerate(lines) if t == "ev" and i == self.sel), now_at or 0)
        top = max(0, min(focus - room // 3, len(lines) - room))
        tw = 15
        for t, i in lines[top: top + room]:
            if t == "now":
                nxt = next((e for e in timed if e["s"] > now and not e["cancelled"]), None)
                label = f" now {now:%-I:%M} "
                if nxt:
                    tail = f" in {dur(nxt['s'] - now)} "
                    label += "· " + clip(nxt["subject"], max(8, min(40, w - 12 - len(label) - len(tail)))) + tail
                self.put(y, 1, "──" + label + "─" * max(0, w - 4 - len(label)), self.a("now"))
                y += 1
                continue
            e = timed[i]
            past = is_today and e["e"] <= now or self.day < now.date()
            current = is_today and e["s"] <= now < e["e"]
            attr = self.a("dim") if past or e["cancelled"] else self.a("cur") if current else (
                self.a("tent") if e["showAs"] == "tentative" else self.a("oof") if e["showAs"] == "oof" else 0)
            when = f"{hm(e['s'])}–{hm(e['e']).strip()}"
            mark = "✕" if e["cancelled"] else MARK.get(e["showAs"], " ")
            flag = "!" if id(e) in clash else " "
            room_txt = max(0, w - 6 - tw - (2 if e["link"] else 0))  # keep room for the ↗ join marker
            text = clip(e["subject"] + (" (cancelled)" if e["cancelled"] else ""), room_txt)
            left = room_txt - len(text)
            extra = " ↗" if e["link"] else (clip(f"  @ {e['location']}", left) if e["location"] and left > 8 else "")
            row_attr = attr | (self.a("sel") if i == self.sel else 0)
            self.put(y, 1, when.ljust(tw), row_attr)
            self.put(y, 1 + tw, flag, self.a("err"))
            self.put(y, 2 + tw, mark + " ", row_attr)
            self.put(y, 4 + tw, text, row_attr)
            if len(extra) <= left:
                self.put(y, 4 + tw + len(text), extra, self.a("link") if e["link"] else self.a("dim"))
            y += 1
        if self.sel is not None and y < h - 2:
            e = timed[self.sel]
            info = f"{dur(e['e'] - e['s'])} · {e['showAs']}" + (f" · {e['organizer']}" if e["organizer"] and not e["isOrganizer"] else "") + (
                f" · {e['attendees']} invited" if e["attendees"] else "") + (f" · {e['link']}" if e["link"] else "")
            self.put(h - 2, 1, info[: w - 2], self.a("dim"))

    def draw_week(self, y, h, w, mon, now):
        # The next seven days from the selected one, so it starts at the top even in a short pane.
        self.rows = []
        self.ensure(monday(self.day + timedelta(days=6)))
        for i in range(7):
            d = self.day + timedelta(days=i)
            all_day, timed = day_events(self.weeks, d)
            if y >= h - 2:
                break
            head = d.strftime("%a %b %-d")
            self.put(y, 1, head, self.a("sel") if d == self.day else self.a("today") if d == now.date() else self.a("head"))
            if all_day:
                self.put(y, 2 + len(head), "  " + " · ".join(e["subject"] for e in all_day), self.a("dim"))
            y += 1
            for e in timed or []:
                if y >= h - 2:
                    break
                past = e["e"] <= now
                attr = self.a("dim") if past or e["cancelled"] else self.a("cur") if e["s"] <= now < e["e"] else (
                    self.a("tent") if e["showAs"] == "tentative" else 0)
                mark = "✕" if e["cancelled"] else MARK.get(e["showAs"], " ")
                self.put(y, 3, f"{hm(e['s'])} {mark} {e['subject']}"[: w - 4], attr)
                y += 1
            if timed == []:
                self.put(y, 3, "—", self.a("dim"))
                y += 1

    # input ------------------------------------------------------------
    def flash(self, text):
        self.msg, self.msg_until = text, time.time() + 4

    def open_selected(self, outlook=False):
        if self.view != "day" or self.sel is None or not self.rows:
            self.flash("Pick a meeting with ↑/↓ first.")
            return
        e = self.rows[self.sel]
        url = e["webLink"] if outlook else e["link"] or e["webLink"]
        if not url:
            self.flash("No link for this event.")
            return
        subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.flash("Opening " + ("in Outlook" if url == e["webLink"] else url[:60]))

    def run(self):
        c = self.c
        last_tick = 0
        while True:
            if time.time() - last_tick > 30:
                self.ensure(monday(self.day))
                if monday(date.today()) != monday(self.day):
                    self.ensure(monday(date.today()))
                last_tick = time.time()
            self.draw()
            k = self.scr.getch()
            if self.wake.is_set():
                self.wake.clear()
            if k == ord("q"):
                return
            moved = None
            if k in (c.KEY_RIGHT, ord("l"), ord("n")):
                moved = self.day + timedelta(days=1)
            elif k in (c.KEY_LEFT, ord("h"), ord("p")):
                moved = self.day - timedelta(days=1)
            elif k in (ord("L"), ord("N"), c.KEY_NPAGE):
                moved = self.day + timedelta(days=7)
            elif k in (ord("H"), ord("P"), c.KEY_PPAGE):
                moved = self.day - timedelta(days=7)
            elif k == ord("t"):
                moved = date.today()
            elif k == ord("w"):
                self.view = "day" if self.view == "week" else "week"
            elif k == ord("r"):
                self.ensure(monday(self.day), force=True)
                self.flash("Refreshing…")
            elif k in (c.KEY_DOWN, ord("j")) and self.view == "day" and getattr(self, "rows", None):
                now = datetime.now()
                first = next((i for i, e in enumerate(self.rows) if e["e"] > now), 0) if self.day == now.date() else 0
                self.sel = first if self.sel is None else min(self.sel + 1, len(self.rows) - 1)
            elif k in (c.KEY_UP, ord("k")) and self.view == "day" and getattr(self, "rows", None):
                self.sel = len(self.rows) - 1 if self.sel is None else max(self.sel - 1, 0)
            elif k in (10, 13, c.KEY_ENTER):
                self.open_selected()
            elif k == ord("o"):
                self.open_selected(outlook=True)
            elif k == c.KEY_RESIZE:
                pass
            if moved:
                self.day, self.sel = moved, None
                self.ensure(monday(moved))


def main():
    args = sys.argv[1:]
    if args[:1] == ["--fetch"]:
        mon = monday(date.fromisoformat(args[1]) if len(args) > 1 else date.today())
        data = fetch_week(mon)
        save_cache(data)
        json.dump(data, sys.stdout, indent=1)
        print()
        return
    if args[:1] == ["--agenda"]:
        print_agenda(date.fromisoformat(args[1]) if len(args) > 1 else date.today())
        return
    global DEMO
    if args[:1] == ["--demo"]:
        DEMO, args = True, args[1:]
    if args:
        print(__doc__.strip())
        sys.exit(2)
    import curses
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(lambda scr: App(scr).run())


if __name__ == "__main__":
    main()
