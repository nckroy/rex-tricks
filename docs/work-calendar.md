# Work calendar pane

Files: [`work-calendar/`](../work-calendar/): [`workcal.py`](../work-calendar/workcal.py) (calendar), [`workcal-pane.sh`](../work-calendar/workcal-pane.sh) (opens it in a Rex pane), [`install.sh`](../work-calendar/install.sh)

A text-mode view of your Outlook (Microsoft 365) calendar for a Rex pane. Its events come from Claude's Microsoft 365 connector, so you don't need an ICS link, an app registration or an account in macOS Calendar.

- **Day view:** the day's all-day events, then its meetings with a red `now` line that names the next meeting and how long until it starts. The meeting in progress is green, past meetings are dimmed, and tentative ones are yellow. `!` marks a meeting that overlaps another one you're busy for, and `↗` marks one with a join link.
- **Week strip:** the seven days of the week with a meeting count for each, when the pane is wide enough.
- **Week view (`w`):** the next seven days from the selected one, as a compact list.

| Key | Action |
|---|---|
| `←` `→` (or `h` `l`) | previous / next day |
| `PgUp` `PgDn` (or `H` `L`) | previous / next week |
| `t` | today |
| `↑` `↓` (or `k` `j`) | pick a meeting; the bottom line shows its length, organizer, invite count and link |
| `Enter` | open the picked meeting's join link (its location URL), or Outlook if it has none |
| `o` | open the picked meeting in Outlook on the web |
| `w` | switch between day and week view |
| `r` | refresh now |
| `q` | quit |

## How it fetches events

No program outside Claude can call a claude.ai connector, so each fetch runs a headless `claude -p` (Haiku by default). That run is locked down:

- `--tools ""` turns off every built-in tool, and `--allowedTools` allows only the connector's `outlook_calendar_search`, so the run can't read files, run commands or call any other connector.
- The prompt asks for all the pages of one week in a single turn of parallel calls. `--max-turns 1` stops the run as soon as they return, so the model never reads your events, and text in an event can't steer it.
- The events are taken from the raw tool results in the `stream-json` output, not from anything the model writes. Results from a call with different dates than were asked for are ignored.
- Every event carries its position in the result set, so the fetcher checks it got all of them and asks again for any missing pages.
- `REX_*` variables are removed from the run's environment, so Claude Code hooks that open Rex panes (like the [Claude usage pane](claude-usage-pane.md)) don't fire.

Pages hold 15 events, because the connector's larger pages are spilled to a file instead of being returned inline. A week of about 50 events takes about 10 seconds and costs about $0.015.

The week on screen refreshes every 15 minutes, and other weeks load when you move to them. Calendar panes share one cache, and a lock file lets only one of them fetch a given week at a time. When one pane has fetched, the others pick up its copy. So several Claude sessions, each with its own calendar pane, cost no more than one. Events are cached per week in `~/Library/Caches/rex-work-calendar/` (directory mode 700, files mode 600), so the pane opens instantly with the last fetch and keeps showing it if a fetch fails. The cache holds real titles, including those of events marked private, and stays on your machine.

Graph labels times with Windows zone names (`Mountain Standard Time`). The pane converts them to the Mac's time zone, by name, so times stay right across a daylight saving change.

## Requirements

- Rex on macOS with the `rex` CLI on `PATH`, and `python3` (3.9 or later).
- Claude Code (`claude` on `PATH`), signed in with a claude.ai account whose Microsoft 365 connector is connected and allowed by your organization.

## Install

```sh
work-calendar/install.sh
```

This copies the scripts to `~/.config/rex/work-calendar/` and links `workcal` and `workcal-pane` into `~/.local/bin`.

If the [Claude usage pane](claude-usage-pane.md) is installed too, its hook opens the calendar above the usage pane every time you start `claude` in Rex; run `claude-usage/install.sh` again after pulling, so the installed hook script includes the calendar. You can also open it yourself, in any Rex pane:

```sh
workcal-pane            # open the calendar to the right
workcal-pane --below    # or below
```

`workcal` runs the calendar in the current terminal. `workcal --agenda [YYYY-MM-DD]` prints one day as plain text, and `workcal --fetch [YYYY-MM-DD]` fetches the week containing that date and prints it as JSON, which is useful for checking the connector. `work-calendar/install.sh uninstall` removes the links and the cache.

| Variable | Default | Effect |
|---|---|---|
| `WORKCAL_REFRESH_MIN` | `15` | minutes between automatic refreshes |
| `WORKCAL_MODEL` | `haiku` | model for the fetch run |
| `WORKCAL_CLAUDE` | `claude` | path to the Claude Code CLI |
| `NO_COLOR` | | plain text |

## Limitations

- **Default calendar only.** Shared and delegated calendars aren't fetched.
- **Join links come from the location field.** A Teams or Zoom link that's only in the invite body isn't found; `Enter` then opens the event in Outlook, where you can join.
- **Each refresh costs a little.** At the default 15 minutes, calendar panes left open for a 10-hour day make about 40 fetches between them, about $0.60. Raise `WORKCAL_REFRESH_MIN` to spend less.
- **It's read-only.** You can't accept, decline or edit events from the pane.
- **A failed fetch waits two minutes** before it tries again (press `r` to retry sooner). The header shows `⚠` and the footer shows the error, while the cached events stay on screen.
