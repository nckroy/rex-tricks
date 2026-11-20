"""rex-tricks: plugins for the Rex terminal, and the tool that installs and arranges them.

Stdlib only, Python 3.9+, so it runs on the python3 that ships with macOS.
"""
import os

# Where everything is installed. Override with REX_TRICKS_HOME (the tests do).
def home():
    return os.path.expanduser(os.environ.get("REX_TRICKS_HOME") or "~/.config/rex-tricks")

# Where plugin commands are linked. Override with REX_TRICKS_BIN.
def bin_dir():
    return os.path.expanduser(os.environ.get("REX_TRICKS_BIN") or "~/.local/bin")

# The checkout or install this code runs from: the folder holding bin/, core/ and plugins/.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
