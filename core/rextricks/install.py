"""Installing: copying files into place, linking commands, running plugin hooks and adding
the Claude Code hook that opens the column."""
import json, os, shutil, stat, subprocess, sys, time
from . import ROOT, bin_dir, config, home

CLAUDE_DIR = os.path.expanduser("~/.claude")
HOOK_MARKER = "/core/claude_hook.sh"  # any rex-tricks home
OLD_HOOK_MARKER = "claude-usage/rex_session_start.sh"  # the single-add-on hook this replaced


def say(msg):
    print(msg)


# ---- files ----------------------------------------------------------------------------------

def sync():
    """Copy bin/, core/ and plugins/ from this checkout into home(). Files are copied rather
    than linked: a LaunchAgent reading ~/Documents or iCloud folders gets privacy prompts.
    Your own plugins in plugins.d/ and config.json aren't touched."""
    dst = home()
    if os.path.realpath(ROOT) == os.path.realpath(dst):
        return
    os.makedirs(dst, exist_ok=True)
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    for d in ("bin", "core", "plugins"):
        target = os.path.join(dst, d)
        if os.path.isdir(target):
            shutil.rmtree(target)
        shutil.copytree(os.path.join(ROOT, d), target, ignore=ignore)
    for base, _, files in os.walk(dst):
        for f in files:
            if f.endswith((".sh", ".py", ".zsh", ".lua")) or base.endswith("/bin"):
                p = os.path.join(base, f)
                os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    link("rex-tricks", os.path.join(dst, "bin", "rex-tricks"))


def link(name, target):
    os.makedirs(bin_dir(), exist_ok=True)
    path = os.path.join(bin_dir(), name)
    if os.path.lexists(path):
        if not os.path.islink(path):
            say(f"  not linking {path}: a file that isn't a link is already there")
            return
        os.remove(path)
    os.symlink(target, path)
    if ":" + bin_dir() + ":" not in ":" + os.environ.get("PATH", "") + ":":
        say(f"  note: {bin_dir()} isn't on your PATH")


def unlink(name, plugin_dir):
    path = os.path.join(bin_dir(), name)
    if os.path.islink(path):
        os.remove(path)


# ---- plugins ----------------------------------------------------------------------------------

def hook_env(plugin, cfg):
    env = dict(os.environ)
    env.update(config.effective_settings(plugin, cfg))
    env.update(REX_TRICKS_HOME=home(), REX_TRICKS_PLUGIN_DIR=plugin.dir,
               REX_TRICKS_BIN=bin_dir(), REX_TRICKS_PYTHON=sys.executable)
    return env


def run_hook(plugin, which, cfg):
    script = plugin.hooks.get(which)
    if not script:
        return True
    r = subprocess.run(["/bin/sh", os.path.join(plugin.dir, script)], env=hook_env(plugin, cfg),
                       cwd=plugin.dir)
    if r.returncode:
        say(f"  {plugin.name}: {which} hook failed (exit {r.returncode})")
    return r.returncode == 0


def install_plugin(plugin, cfg):
    missing = plugin.missing()
    if missing:
        say(f"  {plugin.name}: warning: needs {', '.join(missing)}")
    for name, target in plugin.links.items():
        link(name, os.path.join(plugin.dir, target))
    ok = run_hook(plugin, "install", cfg)
    say(f"  {plugin.name}: installed" if ok else f"  {plugin.name}: installed with errors")


def uninstall_plugin(plugin, cfg):
    run_hook(plugin, "uninstall", cfg)
    for name in plugin.links:
        unlink(name, plugin.dir)
    say(f"  {plugin.name}: removed")


# ---- Claude Code hook -----------------------------------------------------------------------

def settings_path():
    return os.path.join(CLAUDE_DIR, "settings.json")


def _hook_command():
    script = os.path.join(home(), "core", "claude_hook.sh")
    h = os.path.expanduser("~")
    script = '"$HOME' + script[len(h):] + '"' if script.startswith(h + "/") else json.dumps(script)
    return f"/bin/zsh -c '{script} 2>/dev/null || true'"


def _has(entry, marker):
    return any(marker in (h.get("command") or "") for h in entry.get("hooks") or [])


def set_claude_hook(on):
    """Add (on=True) or remove the SessionStart hook. Also removes the old claude-usage hook.
    settings.json is backed up to ~/.claude/backups/ before any change."""
    path = settings_path()
    data = {}
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    entries = (data.get("hooks") or {}).get("SessionStart") or []
    keep = [e for e in entries if not _has(e, OLD_HOOK_MARKER) and not _has(e, HOOK_MARKER)]
    if on:
        keep.append({"matcher": "startup",
                     "hooks": [{"type": "command", "command": _hook_command(), "timeout": 10}]})
    if keep == entries:
        return False
    if os.path.exists(path):
        os.makedirs(os.path.join(CLAUDE_DIR, "backups"), exist_ok=True)
        shutil.copy2(path, os.path.join(CLAUDE_DIR, "backups",
                                        "settings.json.pre-rex-tricks-" + time.strftime("%Y%m%d-%H%M%S")))
    data.setdefault("hooks", {})["SessionStart"] = keep
    if not keep:
        del data["hooks"]["SessionStart"]
        if not data["hooks"]:
            del data["hooks"]
    os.makedirs(CLAUDE_DIR, exist_ok=True)
    tmp = path + ".rex-tricks.tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)
    return True


# ---- migration from the separate add-on installers ---------------------------------------------

OLD_INSTALLS = {
    "claude-usage": "~/.claude/scripts/claude-usage",
    "work-calendar": "~/.config/rex/work-calendar",
    "vault-pane": "~/.config/rex/vault-pane",
    "context-panes": "~/Library/LaunchAgents/io.github.nckroy.rex-context-watch.plist",
}


def detect_old(registry):
    """A starting config that matches what the old per-add-on installers set up."""
    cfg = config.load()
    found = [n for n, p in OLD_INSTALLS.items() if os.path.exists(os.path.expanduser(p))]
    if "claude-usage" in found and registry.plugins.get("btop") and not registry.plugins["btop"].missing():
        found.append("btop")
    cfg["enabled"] = [n for n in ["context-panes", "claude-usage", "work-calendar", "btop", "vault-pane"]
                      if n in found]
    cfg["column"]["panes"] = [n for n in ["work-calendar", "btop", "claude-usage"] if n in found]
    return cfg, found


def leftovers():
    """Old install folders that are no longer used, for the user to delete."""
    out = [os.path.expanduser(p) for n, p in OLD_INSTALLS.items() if n != "context-panes"]
    out += [os.path.expanduser(p) for p in ("~/.config/rex/context-watch.lua",)]
    return [p for p in out if os.path.exists(p)]
