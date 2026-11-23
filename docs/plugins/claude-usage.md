# Claude usage pane

Plugin: [`plugins/claude-usage/`](../../plugins/claude-usage/): [`usage_report.py`](../../plugins/claude-usage/usage_report.py) (report), [`usage_loop.sh`](../../plugins/claude-usage/usage_loop.sh) (refresh loop), [`plugin.json`](../../plugins/claude-usage/plugin.json)

When you start [Claude Code](https://claude.com/claude-code) in a Rex pane, this opens a pane to its right with a color report of your Claude usage, refreshed every 30 seconds:

- **This session:** span, requests, uncached input, cache writes and reads, output (and thinking), total tokens, cache hit rate, usage by model, subagent requests, output by hour and the largest context additions.
- **Context:** the tokens the latest main-thread request carried, the peak and starting size, likely compactions (a drop of more than half), and a sparkline of growth over the session.
- **Current 5-hour window:** start, end, elapsed and remaining time with a bar showing how far through the 5 hours the window is (time, not usage), totals for every session in the window, output and new-input rates, and a per-session list with each session's current context.

## When it opens

The pane is one of the panes in the [Claude column](../configuration.md#the-claude-column), which rex-tricks opens to the right of Claude Code each time a new `claude` session starts in Rex (not on resume or `/clear`). The column's hook passes this pane the session's `session_id`. By default the column is the [work calendar](work-calendar.md), [btop](btop.md) and this report, top to bottom, with each plugin included only when it's enabled. Run `rex-tricks column` to change the order.

The `session_id` the hook receives isn't always the id of the transcript the conversation writes to: a conversation can keep writing to an earlier transcript (logged as `sessionId`) while each record also carries the running process's id (logged as `session_id`). The report matches either one. When they differ, the header shows both, for example `b69955af… (transcript 30ee408f)`.

Running `/resume` inside a session is different: recent Claude Code versions open the old conversation as a background session whose records carry only the old conversation's id, never the new session's. The only link is in the new session's own transcript, which logs the `/resume` output ("running in the background (03df1d61)") and a `continued-in` record. The report reads those and counts the resumed conversation too, following chains of resumes. It counts the resumed conversation's records from the last 12 hours, including ones from before the resume.

The report fits itself to the pane. It reads the width from the pane's terminal (`/dev/tty`), because the refresh loop captures its output, then falls back to `$COLUMNS` and then to 80. Set `USAGE_WIDTH` to force a width. Dividers, bars and the sparkline scale between 40 and 120 columns, the notes rewrap, and any line still too long is cut with `…`. A resized pane catches up on the next refresh.

## Requirements

- Rex on macOS with the `rex` CLI on `PATH`, Claude Code and `python3` (3.9 or later).

## Install

```sh
rex-tricks enable claude-usage
```

This puts the report in the Claude column and adds the column's `SessionStart` hook to `~/.claude/settings.json`, after backing that file up to `~/.claude/backups/`. Existing hooks, including Rex's own `SessionStart` hook, are kept. `rex-tricks disable claude-usage` takes it out again.

Set `USAGE_WIDTH` to force a width with `rex-tricks set claude-usage USAGE_WIDTH 100`. To see the report without the hook, run `python3 ~/.config/rex-tricks/plugins/claude-usage/usage_report.py <session-id>`. Set `NO_COLOR=1` for plain text.

## Limitations

- **Counts are estimates from local logs.** They come from the `usage` block of each assistant message in `~/.claude/projects/**/*.jsonl`, de-duplicated by message and request ID. Usage on other machines or on claude.ai isn't included.
- **The 5-hour window is reconstructed, not read from Anthropic.** It's worked out the way ccusage does it: a window starts at the hour of the first message after a gap of 5 hours or more. Anthropic doesn't publish plan limits in tokens, so the pane can't show a percentage of your limit. Run `/usage` in Claude Code for the server's own figures.
- **Context isn't shown as a percentage** of the model's window. `/context` in Claude Code shows that.
- **Pane size is set once,** when the column opens. After you change the font size or the window, drag the border or close and reopen the pane.
