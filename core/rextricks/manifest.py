"""Load and validate a plugin's plugin.json."""
import json, os, re, shutil, sys

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SETTING_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TOP_KEYS = {"name", "description", "requires", "files", "links", "hooks", "pane", "settings"}
PANE_KEYS = {"label", "command", "height", "min_rows", "keep_open"}
HOOK_KEYS = {"install", "uninstall"}
# Places a required command may live besides PATH. A Claude Code hook can start with a
# PATH that leaves out Homebrew.
EXTRA_PATH = ["/opt/homebrew/bin", "/usr/local/bin"]


class ManifestError(Exception):
    pass


class Plugin:
    def __init__(self, path, data, source):
        self.dir = path
        self.data = data
        self.source = source  # "builtin", "user" or "path"

    name = property(lambda self: self.data["name"])
    description = property(lambda self: self.data.get("description", ""))
    pane = property(lambda self: self.data.get("pane"))
    links = property(lambda self: self.data.get("links") or {})
    hooks = property(lambda self: self.data.get("hooks") or {})
    settings = property(lambda self: self.data.get("settings") or {})

    def kinds(self):
        k = []
        if self.pane: k.append("pane")
        if self.links: k.append("command")
        if self.hooks.get("install"): k.append("service")
        return k

    def missing(self):
        """Requirements this machine doesn't meet, as readable strings."""
        req = self.data.get("requires") or {}
        out = [f"command '{c}'" for c in req.get("commands", []) if not which(c)]
        py = req.get("python")
        if py and sys.version_info[:2] < tuple(int(x) for x in str(py).split(".")[:2]):
            out.append(f"python {py}+ (this is {sys.version_info[0]}.{sys.version_info[1]})")
        return out


def which(cmd):
    return shutil.which(cmd, path=os.pathsep.join([os.environ.get("PATH", "")] + EXTRA_PATH))


def validate(data, path):
    """Return a list of problems with a parsed manifest found in folder `path`."""
    errs = []
    if not isinstance(data, dict):
        return ["plugin.json must hold a JSON object"]
    for k in sorted(set(data) - TOP_KEYS):
        errs.append(f"unknown key '{k}'")
    name = data.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        errs.append("'name' must be lowercase letters, digits and dashes")
    elif os.path.basename(path) != name:
        errs.append(f"'name' is '{name}' but the folder is '{os.path.basename(path)}'")
    if not isinstance(data.get("description"), str) or not data.get("description"):
        errs.append("'description' is required")
    req = data.get("requires", {})
    if not isinstance(req, dict) or set(req) - {"commands", "python"}:
        errs.append("'requires' may hold only 'commands' and 'python'")
    elif not _str_list(req.get("commands", [])):
        errs.append("'requires.commands' must be a list of strings")
    if "files" in data and not _str_list(data["files"]):
        errs.append("'files' must be a list of glob patterns")
    for key, val in (data.get("links") or {}).items():
        if not isinstance(val, str) or "/" in key:
            errs.append(f"'links.{key}' must map a command name to a file in the plugin")
        elif not os.path.isfile(os.path.join(path, val)):
            errs.append(f"'links.{key}': no file {val}")
    hooks = data.get("hooks") or {}
    for k in sorted(set(hooks) - HOOK_KEYS):
        errs.append(f"unknown hook '{k}'")
    for k in HOOK_KEYS & set(hooks):
        if not os.path.isfile(os.path.join(path, hooks[k])):
            errs.append(f"'hooks.{k}': no file {hooks[k]}")
    if "pane" in data:
        errs += ["pane: " + e for e in validate_pane(data["pane"], full=True)]
    sets = data.get("settings") or {}
    if not isinstance(sets, dict):
        errs.append("'settings' must be an object")
    else:
        for k, v in sets.items():
            if not SETTING_RE.match(k):
                errs.append(f"setting '{k}' isn't a valid environment variable name")
            if not isinstance(v, dict) or not isinstance(v.get("default", ""), str):
                errs.append(f"setting '{k}' must be an object with a string 'default'")
    return errs


def validate_pane(pane, full):
    """Problems with a pane section. With full=False, check only the keys given (config overrides)."""
    if not isinstance(pane, dict):
        return ["must be an object"]
    errs = [f"unknown key '{k}'" for k in sorted(set(pane) - PANE_KEYS)]
    if full:
        for k in ("label", "command"):
            if k not in pane:
                errs.append(f"'{k}' is required")
    if "label" in pane and not isinstance(pane["label"], str):
        errs.append("'label' must be a string")
    if "command" in pane and (not _str_list(pane["command"]) or not pane["command"]):
        errs.append("'command' must be a non-empty list of strings")
    if "height" in pane and not (_num(pane["height"]) and 0 < pane["height"] <= 1):
        errs.append("'height' must be a number above 0 and at most 1")
    if "min_rows" in pane and not (isinstance(pane["min_rows"], int) and pane["min_rows"] >= 0):
        errs.append("'min_rows' must be a whole number")
    if "keep_open" in pane and not isinstance(pane["keep_open"], bool):
        errs.append("'keep_open' must be true or false")
    return errs


def load(path, source="builtin"):
    f = os.path.join(path, "plugin.json")
    try:
        with open(f) as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise ManifestError(f"{f}: {e}")
    errs = validate(data, path)
    if errs:
        raise ManifestError(f"{f}:\n  " + "\n  ".join(errs))
    return Plugin(path, data, source)


def _str_list(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)
