"""Find plugins on the search path.

In order, later folders winning when two plugins share a name:
  1. <root>/plugins           built-ins shipped with rex-tricks (replaced on every install)
  2. <home>/plugins.d         your own plugins (install never touches them)
  3. $REX_TRICKS_PLUGIN_PATH  more folders, separated by ':'
Folders whose names start with '_' or '.' (such as _template) are skipped.
"""
import os
from . import ROOT, home
from .manifest import ManifestError, load


def search_path(root=None):
    root = root or ROOT
    out = [(os.path.join(root, "plugins"), "builtin"), (os.path.join(home(), "plugins.d"), "user")]
    for p in filter(None, os.environ.get("REX_TRICKS_PLUGIN_PATH", "").split(os.pathsep)):
        out.append((os.path.expanduser(p), "path"))
    return out


class Registry:
    def __init__(self, root=None):
        self.plugins = {}   # name -> Plugin
        self.errors = []    # strings: manifests that failed to load
        self.clashes = []   # (name, overridden dir, winning dir)
        for base, source in search_path(root):
            if not os.path.isdir(base):
                continue
            for entry in sorted(os.listdir(base)):
                d = os.path.join(base, entry)
                if entry[0] in "._" or not os.path.isdir(d):
                    continue
                if not os.path.isfile(os.path.join(d, "plugin.json")):
                    self.errors.append(f"{d}: no plugin.json")
                    continue
                try:
                    p = load(d, source)
                except ManifestError as e:
                    self.errors.append(str(e))
                    continue
                if p.name in self.plugins:
                    self.clashes.append((p.name, self.plugins[p.name].dir, d))
                self.plugins[p.name] = p

    def get(self, name):
        if name not in self.plugins:
            raise SystemExit(f"rex-tricks: no plugin named '{name}' (see 'rex-tricks list')")
        return self.plugins[name]
