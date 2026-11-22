# -*- coding: utf-8 -*-
"""Lot L2 (barre) : le mod hooks/bar est branché, silencieux hors mission, sans réseau, et son moteur est vert.
Bibliothèque standard seulement. Les tests du mod lui-même (claude plugin test) et la validation
(claude plugin validate) sont lancés à la main ; ici on verrouille ce qui peut régresser sans l'app."""
import json
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BAR = os.path.join(ROOT, "hooks", "bar")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class BarWiring(unittest.TestCase):
    def test_hooks_json_declares_the_module_and_keeps_the_command_hooks(self):
        h = json.loads(read(os.path.join(ROOT, "hooks", "hooks.json")))
        self.assertEqual(h["modules"], ["./bar/register.tsx"])
        self.assertEqual(sorted(h["hooks"]), ["SessionStart", "Stop", "UserPromptSubmit"])

    def test_manifest_still_declares_no_vendor_and_names_the_contract(self):
        m = json.loads(read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        self.assertEqual(m["types"], "./hooks/bar/types/index.d.ts")
        self.assertTrue(os.path.isfile(os.path.join(ROOT, m["types"])))

    def test_every_hook_is_gated_by_the_mission_flag(self):  # I7
        src = read(os.path.join(BAR, "register.tsx"))
        self.assertIn("missionActive", src)
        for ev in ("turn.start", "turn.complete", "tool.call"):
            self.assertRegex(src, r"on\('%s'[^\n]*\n\s*if \(!active\) return next\(e\)" % re.escape(ev))
        self.assertIn("active = await missionActive($, cwd)\n    if (!active) return next(e)", src)
        self.assertIn("!active || v === null", src)  # ui.render
        self.assertIn("isDeferred: true", src)  # aucun schéma d'outil au repos

    def test_no_network_no_telemetry_no_personal_path_in_the_mod(self):  # I2, I4, I5
        for name in os.listdir(BAR):
            p = os.path.join(BAR, name)
            if not os.path.isfile(p):
                continue
            t = read(p)
            self.assertNotRegex(t, r"\bfetch\(|XMLHttpRequest|WebSocket|https?://(?!www\.w3\.org/2000/svg)[a-z0-9.-]+\.[a-z]{2,}/", name)
            self.assertNotRegex(t, r"(?i)telemetry|C:[\/]+Users|des" + "ag", name)

    def test_bar_is_one_line_without_ring_or_badge(self):  # §5.1 (version remplacée)
        t = read(os.path.join(BAR, "bar.tsx"))
        self.assertNotRegex(t, r"(?i)<animate|<circle|gradient|backdrop-filter")
        self.assertIn("Math.min(360", t)


@unittest.skipUnless(shutil.which("node"), "node absent : tests du moteur non exécutables")
class BarEngine(unittest.TestCase):
    def test_engine_and_signal_tests_pass(self):  # A9
        p = subprocess.run(["node", "--test", "tests/bar/engine.test.mjs", "tests/bar/signals.test.mjs"],
                           cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
        out = p.stdout.decode("utf-8", "replace")
        self.assertEqual(p.returncode, 0, out[-2000:])
        self.assertRegex(out, r"fail 0")


if __name__ == "__main__":
    unittest.main()
