# -*- coding: utf-8 -*-
"""A23 : uninstalling leaves no trace. The plugin is exercised in a throwaway HOME (state, logs, relay home, vault index),
then scripts/uninstall.py --yes runs; the HOME must be byte-for-byte what it was before. Missions inside projects are the
user's data: listed, never deleted unless asked by path."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import ROOT, SCRIPTS


def snapshot(d):
    out = {}
    for dp, dns, fs in os.walk(d):
        for n in dns + fs:
            p = os.path.join(dp, n)
            out[os.path.relpath(p, d)] = os.path.getsize(p) if os.path.isfile(p) else "dir"
    return out


class A23Uninstall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sr-a23-")
        self.home = os.path.join(self.tmp, "home")
        self.proj = os.path.join(self.tmp, "proj")
        self.vault = os.path.join(self.tmp, "vault")
        for d in (self.home, self.proj, os.path.join(self.vault, "projets")):
            os.makedirs(d)
        with open(os.path.join(self.home, "rien-a-voir.txt"), "w") as f:
            f.write("fichier de l'utilisateur")
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(("SUPER_REPROMPT", "SR_", "RELAIS", "CLAUDE_"))}
        self.env.update(USERPROFILE=self.home, HOME=self.home, PYTHONIOENCODING="utf-8", SR_VAULT_PATH=self.vault)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_py(self, *args, cwd=None):
        p = subprocess.run([sys.executable] + list(args), cwd=cwd or self.proj, env=self.env, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, timeout=120)
        return p.returncode, p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")

    def test_home_is_restored_exactly(self):
        before = snapshot(self.home)
        # exercise the plugin: relay state, vault index and journal, a mission in a project
        self.run_py(os.path.join(ROOT, "net", "relais.py"), "status")
        self.run_py(os.path.join(SCRIPTS, "vault.py"), "init", "essai")
        self.run_py(os.path.join(SCRIPTS, "vault.py"), "index")
        self.run_py(os.path.join(SCRIPTS, "vault.py"), "log", "essai", "une ligne")
        after_use = snapshot(self.home)
        self.assertNotEqual(after_use, before, "the exercise left nothing to uninstall: the test proves nothing")
        rc, out = self.run_py(os.path.join(SCRIPTS, "uninstall.py"))            # dry run: lists, removes nothing
        self.assertEqual(rc, 0, out)
        self.assertIn("rien n'est supprime", out)
        self.assertEqual(snapshot(self.home), after_use)
        rc, out = self.run_py(os.path.join(SCRIPTS, "uninstall.py"), "--yes")
        self.assertEqual(rc, 0, out)
        self.assertEqual(snapshot(self.home), before)
        # the user's data stays: project missions and the vault notes are listed, not deleted
        self.assertTrue(os.path.isdir(os.path.join(self.proj, ".super-reprompt", "essai")))
        self.assertTrue(os.listdir(os.path.join(self.vault, "projets")))

    def test_refuses_a_home_that_is_not_the_plugin_state(self):
        rc, out = self.run_py(os.path.join(SCRIPTS, "uninstall.py"), "--yes", cwd=self.proj)
        self.assertEqual(rc, 0, out)
        self.env["SUPER_REPROMPT_HOME"] = self.home               # pointing the state dir at the whole HOME must be refused
        rc, out = self.run_py(os.path.join(SCRIPTS, "uninstall.py"), "--yes")
        self.assertNotEqual(rc, 0)
        self.assertTrue(os.path.isfile(os.path.join(self.home, "rien-a-voir.txt")))


if __name__ == "__main__":
    unittest.main()
