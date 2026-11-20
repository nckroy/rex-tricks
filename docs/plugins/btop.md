# btop

Plugin: [`plugins/btop/plugin.json`](../../plugins/btop/plugin.json)

Puts the [btop](https://github.com/aristocratos/btop) system monitor in the [Claude column](../configuration.md#the-claude-column). The plugin is just a manifest. It runs `btop`, which must be installed (`brew install btop`). rex-tricks looks for it on `PATH` and in `/opt/homebrew/bin`.

```sh
rex-tricks enable btop --at 2    # between the calendar and the usage report
```

With its default boxes, btop draws nothing but "Terminal size too small" below 80×24. So the plugin sets `min_rows` to 24, and the column takes rows from the panes below btop, then from the ones above, to give btop its 24. The [column docs](../configuration.md#minimum-rows) explain how. If your btop config shows more boxes, raise the minimum:

```sh
rex-tricks set btop pane.min_rows 30
```

`REX_BTOP_MIN_ROWS` in the environment Claude Code starts in still works too.
