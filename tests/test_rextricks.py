"""Unit tests for rex-tricks. Run from the repo root:  python3 -m unittest discover tests"""
import json, os, shutil, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

from rextricks import column, config, install  # noqa: E402
from rextricks.manifest import validate, validate_pane  # noqa: E402
from rextricks.registry import Registry  # noqa: E402


class Scratch(unittest.TestCase):
    """Each test gets its own REX_TRICKS_HOME, bin dir and plugin path."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.env = {k: os.environ.get(k) for k in ("REX_TRICKS_HOME", "REX_TRICKS_BIN", "REX_TRICKS_PLUGIN_PATH")}
        os.environ["REX_TRICKS_HOME"] = os.path.join(self.tmp, "home")
        os.environ["REX_TRICKS_BIN"] = os.path.join(self.tmp, "bin")
        os.environ.pop("REX_TRICKS_PLUGIN_PATH", None)

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp)

    def make_plugin(self, base, name, **data):
        d = os.path.join(base, name)
        os.makedirs(d)
        with open(os.path.join(d, "plugin.json"), "w") as f:
            json.dump(dict({"name": name, "description": "test"}, **data), f)
        return d


class TestBuiltins(unittest.TestCase):
    def test_every_builtin_manifest_is_valid(self):
        base = os.path.join(ROOT, "plugins")
        for name in os.listdir(base):
            if name.startswith("_"):
                continue
            with open(os.path.join(base, name, "plugin.json")) as f:
                self.assertEqual(validate(json.load(f), os.path.join(base, name)), [], name)

    def test_template_is_valid_once_renamed(self):
        with open(os.path.join(ROOT, "plugins", "_template", "plugin.json")) as f:
            data = json.load(f)
        tmp = tempfile.mkdtemp()
        try:
            d = os.path.join(tmp, "my-plugin")
            shutil.copytree(os.path.join(ROOT, "plugins", "_template"), d)
            self.assertEqual(validate(data, d), [])
        finally:
            shutil.rmtree(tmp)


class TestManifest(Scratch):
    def test_problems_are_reported(self):
        d = os.path.join(self.tmp, "bad")
        os.makedirs(d)
        errs = validate({"name": "Bad Name", "extra": 1, "pane": {"height": 2}}, d)
        text = "\n".join(errs)
        for want in ("unknown key 'extra'", "'name' must be", "'description' is required",
                     "'label' is required", "'height' must be"):
            self.assertIn(want, text)

    def test_partial_pane_for_overrides(self):
        self.assertEqual(validate_pane({"min_rows": 30}, full=False), [])
        self.assertTrue(validate_pane({"min_rows": -1}, full=False))


class TestRegistry(Scratch):
    def test_user_plugins_override_builtins_and_bad_ones_are_reported(self):
        user = os.path.join(os.environ["REX_TRICKS_HOME"], "plugins.d")
        self.make_plugin(user, "btop", pane={"label": "mine", "command": ["top"]})
        os.makedirs(os.path.join(user, "broken"))
        self.make_plugin(user, "_ignored")
        reg = Registry(ROOT)
        self.assertEqual(reg.plugins["btop"].pane["label"], "mine")
        self.assertEqual(reg.plugins["btop"].source, "user")
        self.assertEqual([c[0] for c in reg.clashes], ["btop"])
        self.assertTrue(any("broken" in e for e in reg.errors))
        self.assertNotIn("_ignored", reg.plugins)

    def test_extra_plugin_path(self):
        extra = os.path.join(self.tmp, "extra")
        self.make_plugin(extra, "clock", pane={"label": "c", "command": ["date"]})
        os.environ["REX_TRICKS_PLUGIN_PATH"] = extra
        self.assertEqual(Registry(ROOT).plugins["clock"].source, "path")


class TestConfig(Scratch):
    def test_overrides_merge_over_the_manifest(self):
        p = Registry(ROOT).plugins["btop"]
        cfg = config.merge(config.DEFAULT, {"plugins": {"btop": {"pane": {"min_rows": 30}}}})
        pane = config.effective_pane(p, cfg, environ={})
        self.assertEqual((pane["min_rows"], pane["height"], pane["label"]), (30, 0.30, "btop"))
        self.assertEqual(config.effective_pane(p, cfg, environ={"REX_BTOP_MIN_ROWS": "40"})["min_rows"], 40)

    def test_settings_defaults_and_overrides(self):
        p = Registry(ROOT).plugins["work-calendar"]
        cfg = config.merge(config.DEFAULT, {"plugins": {"work-calendar": {"settings": {"WORKCAL_MODEL": "sonnet"}}}})
        env = config.effective_settings(p, cfg)
        self.assertEqual(env["WORKCAL_MODEL"], "sonnet")
        self.assertEqual(env["WORKCAL_REFRESH_MIN"], "15")
        self.assertNotIn("WORKCAL_CLAUDE", env)  # empty default: not set at all

    def test_validate_names_unknown_plugins(self):
        reg = Registry(ROOT)
        cfg = config.merge(config.DEFAULT, {"enabled": ["nope"], "column": {"panes": ["vault-pane"]}})
        text = "\n".join(config.validate(cfg, reg))
        self.assertIn("'nope'", text)
        self.assertIn("'vault-pane', which has no pane", text)

    def test_save_and_load_round_trip(self):
        cfg = config.load()
        cfg["enabled"] = ["btop"]
        config.save(cfg)
        self.assertEqual(config.load()["enabled"], ["btop"])


class TestLayout(unittest.TestCase):
    def test_ratios_reproduce_the_old_column(self):
        # calendar 0.35, btop 0.30, usage 0.35 -> 0.35 of the column, then 0.30/0.65 of the rest
        r = column.ratios([0.35, 0.30, 0.35])
        self.assertAlmostEqual(r[0], 0.35)
        self.assertAlmostEqual(r[1], 0.30 / 0.65)

    def test_fit_rows_recovers_height_and_overhead(self):
        H, oh = 75.0, 2.0
        pts = [(1.0, H - oh), (0.35, 0.35 * H - oh), (0.2925, 0.2925 * H - oh)]
        fH, foh = column.fit_rows(pts)
        self.assertAlmostEqual(fH, H)
        self.assertAlmostEqual(foh, oh)

    def test_plan_takes_rows_from_the_bottom_first(self):
        # Today's window: calendar 26 rows, btop 21, usage 26, in a 75-row window.
        H, oh = 75.0, 0.25
        hs = [0.35, 0.2925, 0.3575]
        rows = [26, 21, 26]
        new = column.plan(hs, rows, [0, 24, 0], 8, H, oh)
        self.assertGreaterEqual(new[1] * H - oh, 24)
        self.assertAlmostEqual(new[0], hs[0])  # calendar untouched: usage had room
        self.assertAlmostEqual(sum(new), sum(hs))

    def test_split_ratio_finds_the_split_between_two_blocks(self):
        leaf = lambda b: {"block_id": b}
        tree = {"split": {"ratio": 0.7, "before": leaf("claude"), "after": {"split": {
            "ratio": 0.35, "before": leaf("cal"), "after": {"split": {
                "ratio": 0.46, "before": leaf("btop"), "after": leaf("usage")}}}}}}
        self.assertEqual(column.split_ratio(tree, "claude", "cal"), 0.7)
        self.assertEqual(column.split_ratio(tree, "cal", "btop"), 0.35)
        self.assertEqual(column.split_ratio(tree, "btop", "usage"), 0.46)
        self.assertIsNone(column.split_ratio(tree, "usage", "cal"))

    def test_plan_keeps_donors_at_the_floor_and_gives_up_when_full(self):
        H, oh = 30.0, 1.0
        new = column.plan([0.3, 0.4, 0.3], [8, 11, 8], [0, 24, 0], 8, H, oh)
        self.assertIsNone(new)  # both donors are already at 8 rows


class TestClaudeHook(Scratch):
    def setUp(self):
        super().setUp()
        self.claude = os.path.join(self.tmp, ".claude")
        install.CLAUDE_DIR = self.claude
        os.makedirs(self.claude)
        with open(os.path.join(self.claude, "settings.json"), "w") as f:
            json.dump({"hooks": {"SessionStart": [
                {"matcher": "startup", "hooks": [{"type": "command", "command": "rex hook"}]},
                {"matcher": "startup", "hooks": [{"type": "command",
                 "command": "/bin/zsh -c '\"$HOME/.claude/scripts/claude-usage/rex_session_start.sh\"'"}]},
            ]}, "theme": "dark"}, f)

    def tearDown(self):
        install.CLAUDE_DIR = os.path.expanduser("~/.claude")
        super().tearDown()

    def hooks(self):
        with open(os.path.join(self.claude, "settings.json")) as f:
            return [h["command"] for e in json.load(f)["hooks"].get("SessionStart", []) for h in e["hooks"]]

    def test_replaces_the_old_hook_keeps_others_and_backs_up(self):
        self.assertTrue(install.set_claude_hook(True))
        cmds = self.hooks()
        self.assertEqual(len(cmds), 2)
        self.assertEqual(cmds[0], "rex hook")
        self.assertIn("/core/claude_hook.sh", cmds[1])
        self.assertFalse(install.set_claude_hook(True))  # already there: no change, no backup
        self.assertEqual(len(os.listdir(os.path.join(self.claude, "backups"))), 1)
        self.assertTrue(install.set_claude_hook(False))
        self.assertEqual(self.hooks(), ["rex hook"])


if __name__ == "__main__":
    unittest.main()
