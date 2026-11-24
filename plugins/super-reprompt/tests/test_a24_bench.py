# -*- coding: utf-8 -*-
"""A24 bench, PREPARED ONLY (lot L10): three frozen projects hashed BEFORE any run, a 4-arm protocol with a blind judge
and hidden tests, a results template. Running it costs quota and needs the user's written approval (CDC §12)."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import shutil
import unittest

from _t import ROOT

BENCH = os.path.join(ROOT, "evals", "v3-a24")
LEVELS = ("facile", "moyen", "difficile")
ARMS = ("Claude nu", "v2.5", "v3 sans Relais", "v3 complete")


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class A24Bench(unittest.TestCase):
    def test_three_frozen_projects_with_hidden_tests(self):
        for lvl in LEVELS:
            d = os.path.join(BENCH, "projets", lvl)
            self.assertTrue(os.path.isfile(os.path.join(d, "ENONCE.md")), lvl)
            hidden = [f for f in os.listdir(os.path.join(d, "caches")) if f.startswith("test_") and f.endswith(".py")]
            self.assertTrue(hidden, lvl)

    def test_manifest_matches_every_frozen_file(self):
        with open(os.path.join(BENCH, "MANIFEST.json"), encoding="utf-8") as f:
            man = json.load(f)
        self.assertTrue(man["fige_le"])
        on_disk = {}
        for dp, _d, fs in os.walk(os.path.join(BENCH, "projets")):
            for fn in fs:
                if "__pycache__" in dp:
                    continue
                p = os.path.join(dp, fn)
                on_disk[os.path.relpath(p, BENCH).replace("\\", "/")] = sha(p)
        self.assertEqual(on_disk, man["fichiers"])

    def test_hidden_tests_are_real_tests(self):
        """Against an empty implementation every hidden suite must fail: a bench that passes on nothing measures nothing."""
        for lvl in LEVELS:
            d = os.path.join(BENCH, "projets", lvl)
            with open(os.path.join(d, "ENONCE.md"), encoding="utf-8") as f:
                mod = [l.split("`")[1] for l in f if l.startswith("Module :")][0]
            tmp = tempfile.mkdtemp()
            try:
                with open(os.path.join(tmp, mod), "w", encoding="utf-8") as f:
                    f.write("")
                for t in os.listdir(os.path.join(d, "caches")):
                    shutil.copy(os.path.join(d, "caches", t), tmp)
                p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", tmp], cwd=tmp, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=120)
                self.assertNotEqual(p.returncode, 0, lvl)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    def test_protocol_and_results_template(self):
        with open(os.path.join(BENCH, "PROTOCOLE.md"), encoding="utf-8") as f:
            proto = f.read()
        for need in ARMS + ("juge aveugle", "tests caches", "n = 3", "accord", "Hooks personnels coupes", "non inferieure"):
            self.assertIn(need, proto)
        with open(os.path.join(BENCH, "RESULTS.md"), encoding="utf-8") as f:
            res = f.read()
        self.assertIn("NON LANCE", res)
        for arm in ARMS:
            for lvl in LEVELS:
                self.assertIn("| %s | %s |" % (arm, lvl), res)


if __name__ == "__main__":
    unittest.main()
