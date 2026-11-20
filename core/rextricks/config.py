"""The user's config, ~/.config/rex-tricks/config.json, and how it combines with manifests."""
import copy, json, os, tempfile
from . import home
from .manifest import validate_pane

DEFAULT = {
    "enabled": [],
    # The panes opened beside Claude Code when it starts, top to bottom.
    "column": {"panes": [], "width": 83, "min_rows": 8},
    # Per-plugin overrides: {"pane": {...}, "settings": {"NAME": "value"}}
    "plugins": {},
}


def path():
    return os.path.join(home(), "config.json")


def exists():
    return os.path.isfile(path())


def load():
    cfg = copy.deepcopy(DEFAULT)
    if exists():
        with open(path()) as f:
            user = json.load(f)
        if not isinstance(user, dict):
            raise SystemExit(f"rex-tricks: {path()} must hold a JSON object")
        cfg = merge(cfg, user)
    return cfg


def save(cfg):
    os.makedirs(home(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=home(), prefix=".config.", suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.replace(tmp, path())


def validate(cfg, registry):
    """Problems with a loaded config, given the plugins that exist."""
    errs = []
    if not isinstance(cfg.get("enabled"), list):
        errs.append("'enabled' must be a list of plugin names")
    col = cfg.get("column")
    if not isinstance(col, dict) or not isinstance(col.get("panes"), list):
        errs.append("'column.panes' must be a list of plugin names")
        col = {"panes": []}
    if not (isinstance(col.get("width", 83), int) and 20 <= col.get("width", 83) <= 400):
        errs.append("'column.width' must be a whole number of columns")
    for name in cfg.get("enabled") or []:
        if name not in registry.plugins:
            errs.append(f"'enabled' names '{name}', which isn't installed")
    for name in col["panes"]:
        p = registry.plugins.get(name)
        if p is None:
            errs.append(f"'column.panes' names '{name}', which isn't installed")
        elif not p.pane:
            errs.append(f"'column.panes' names '{name}', which has no pane")
    for name, over in (cfg.get("plugins") or {}).items():
        if not isinstance(over, dict) or set(over) - {"pane", "settings"}:
            errs.append(f"'plugins.{name}' may hold only 'pane' and 'settings'")
            continue
        errs += [f"'plugins.{name}.pane': {e}" for e in validate_pane(over.get("pane", {}), full=False)]
        for k, v in (over.get("settings") or {}).items():
            if not isinstance(v, str):
                errs.append(f"'plugins.{name}.settings.{k}' must be a string")
    return errs


def merge(base, over):
    """Deep-merge dict `over` onto a copy of `base`. Lists and scalars replace."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def effective_pane(plugin, cfg, environ=os.environ):
    """The plugin's pane section with the user's overrides applied, or None."""
    if not plugin.pane:
        return None
    pane = merge({"height": 0.3, "min_rows": 0, "keep_open": False}, plugin.pane)
    pane = merge(pane, ((cfg.get("plugins") or {}).get(plugin.name) or {}).get("pane") or {})
    # Kept from before plugins existed: REX_BTOP_MIN_ROWS still sets btop's minimum.
    if plugin.name == "btop" and environ.get("REX_BTOP_MIN_ROWS", "").isdigit():
        pane["min_rows"] = int(environ["REX_BTOP_MIN_ROWS"])
    return pane


def effective_settings(plugin, cfg):
    """Environment variables for the plugin: manifest defaults, then the user's values."""
    env = {k: v.get("default", "") for k, v in plugin.settings.items()}
    env.update(((cfg.get("plugins") or {}).get(plugin.name) or {}).get("settings") or {})
    return {k: v for k, v in env.items() if v != ""}


def column_min_rows(cfg, environ=os.environ):
    if environ.get("REX_PANE_MIN_ROWS", "").isdigit():
        return int(environ["REX_PANE_MIN_ROWS"])
    return int(cfg["column"].get("min_rows", 8))
