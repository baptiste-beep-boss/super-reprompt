# -*- coding: utf-8 -*-
"""Lanceur reel des hooks (hooks/run.sh), execute comme Claude Code le fait : la commande exacte de hooks.json
passee a un shell POSIX.  Defaut trouve le 24/11/2026 en conditions reelles : sous Windows, `python3` du PATH est
le raccourci du Microsoft Store (WindowsApps), qui sort en code 49 ; le pare-feu n'etait alors JAMAIS bloquant.
Ces tests rejouent ce cas : faux python3 en tete du PATH, puis aucun Python du tout."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import ROOT
from test_guard import Env


def posix_shell():
    """Git Bash sous Windows (celui qu'utilise Claude Code), jamais le bash WSL de System32."""
    if os.name != "nt":
        return shutil.which("sh") or shutil.which("bash")
    git = shutil.which("git")
    if git:
        base = os.path.dirname(os.path.dirname(os.path.realpath(git)))
        for rel in (("bin", "bash.exe"), ("usr", "bin", "bash.exe")):
            p = os.path.join(base, *rel)
            if os.path.isfile(p):
                return p
    for p in (shutil.which("bash"),):
        if p and "system32" not in p.lower():
            return p
    return None


SH = posix_shell()


def hook_command(event):
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
        cmd = json.load(f)["hooks"][event][0]["hooks"][0]["command"]
    return cmd.replace("${CLAUDE_PLUGIN_ROOT}", ROOT.replace("\\", "/"))


@unittest.skipUnless(SH, "aucun shell POSIX")
class RealLauncher(unittest.TestCase):
    def setUp(self):
        self.e = Env()
        self.home = tempfile.mkdtemp(prefix="srhome-")
        self.fake = tempfile.mkdtemp(prefix="WindowsApps-")      # le nom contient WindowsApps, comme le vrai
        for n in ("python3", "python"):
            p = os.path.join(self.fake, n)
            with open(p, "w", newline="\n") as f:
                f.write("#!/bin/sh\necho 'Python est introuvable' >&2\nexit 49\n")
            os.chmod(p, 0o755)

    def tearDown(self):
        self.e.close()
        shutil.rmtree(self.home, ignore_errors=True)
        shutil.rmtree(self.fake, ignore_errors=True)

    def run_hook(self, event, payload, path=None):
        env = dict(os.environ, SR_HOME=self.home, SUPER_REPROMPT_HOME=self.home, TEMP=self.e.scratch, TMP=self.e.scratch, TMPDIR=self.e.scratch)
        if path is not None:
            env["PATH"] = path
        return subprocess.run([SH, "-c", hook_command(event)], input=json.dumps(payload).encode("utf-8"), cwd=self.e.root,
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)

    def payload(self, cmd):
        return {"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": self.e.root}

    def test_real_command_blocks_push_force_in_sealed_mission(self):
        r = self.run_hook("PreToolUse", self.payload("git push --force origin main"))
        self.assertEqual(r.returncode, 2, r.stderr.decode("utf-8", "replace"))

    def test_real_command_lets_legit_action_pass(self):
        r = self.run_hook("PreToolUse", self.payload("git status"))
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))

    def test_store_stub_first_in_path_is_skipped(self):
        path = self.fake + os.pathsep + os.environ.get("PATH", "")
        r = self.run_hook("PreToolUse", self.payload("git push --force origin main"), path=path)
        self.assertEqual(r.returncode, 2, r.stderr.decode("utf-8", "replace"))
        self.assertNotIn("introuvable", r.stderr.decode("utf-8", "replace"))

    def test_no_python_at_all_fails_closed_in_sealed_mission(self):
        shdir = os.path.dirname(SH)
        if any(os.path.exists(os.path.join(shdir, n)) for n in ("python", "python3", "python.exe", "py.exe")):
            self.skipTest("un python est a cote du shell")
        r = self.run_hook("PreToolUse", self.payload("git status"), path=self.fake + os.pathsep + shdir)
        self.assertEqual(r.returncode, 2)
        self.assertIn("F00", r.stderr.decode("utf-8", "replace"))

    def test_no_python_outside_mission_stays_silent(self):
        shdir = os.path.dirname(SH)
        if any(os.path.exists(os.path.join(shdir, n)) for n in ("python", "python3", "python.exe", "py.exe")):
            self.skipTest("un python est a cote du shell")
        out = tempfile.mkdtemp(prefix="srnomission-")
        try:
            env = dict(os.environ, SR_HOME=self.home, PATH=self.fake + os.pathsep + shdir)
            r = subprocess.run([SH, "-c", hook_command("PreToolUse")], input=b"{}", cwd=out, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
            self.assertEqual((r.returncode, r.stdout), (0, b""))
        finally:
            shutil.rmtree(out, ignore_errors=True)

    def test_python_path_is_cached_and_a_stale_cache_is_ignored(self):
        self.run_hook("PreToolUse", self.payload("git status"))
        cache = os.path.join(self.home, "python-path")
        self.assertTrue(os.path.isfile(cache))
        with open(cache, "w") as f:
            f.write(os.path.join(self.fake, "python3") + "\n")      # cache pointant vers un raccourci du Store
        r = self.run_hook("PreToolUse", self.payload("git push --force origin main"))
        self.assertEqual(r.returncode, 2)

    def test_prompt_hook_runs_through_launcher(self):
        r = self.run_hook("UserPromptSubmit", {"session_id": "l-1", "cwd": self.e.root,
                          "prompt": "I want you to do a comprehensive audit of our codebase, analyze the architecture, and write a report with prioritized risks."})
        self.assertEqual(r.returncode, 0)
        self.assertIn("[super-reprompt]", r.stdout.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
