# -*- coding: utf-8 -*-
"""Shared helpers for the unit tests (standard library only)."""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, SCRIPTS)


def valid_state(slug="demo-mission", **over):
    st = {
        "schema": 1, "slug": slug, "created": "2026-01-01T00:00:00Z", "lang": "en", "level": "mixed",
        "class": "CODE", "tier": "standard", "status": "ready",
        "framing_session_id": "frame-1", "exec_session_id": None,
        "budget": {"announced_k": 35, "spent_est_k": 0, "cap_k": 100, "exec_estimate_k": [150, 400]},
        "requirements": [{"id": "R1", "text": "Page shows the refund policy", "kind": "unguessable"}],
        "assumptions": ["Plain HTML is fine"],
        "out_of_scope": ["Payment flow"],
        "permissions": {"allow": ["edit files in src/"], "deny": ["delete files", "git push", "network writes", "credentials"]},
        "capabilities": [
            {"id": "K1", "name": "dataviz", "kind": "skill", "phase": "P4", "trigger": "any chart",
             "call": "Skill(dataviz)", "proof": "a Skill tool_use named dataviz appears in the transcript",
             "required": True, "side_effects": False, "plan_b": "draw the chart by hand and say so", "removed_reason": None}],
        "verification": {
            "commands": [{"id": "V1", "cmd": "exit 0", "state": "pending", "reason": None, "plan_b": "run the checks by hand and report"}],
            "criteria": [{"id": "C1", "text": "The refund page returns HTTP 200", "source": "test", "proof": "curl output", "passes": False, "unsourced": False}]},
        "agents": [{"name": "worker-1", "model": "sonnet", "effort": "medium", "max_turns": 30, "skills": [], "isolation": "none", "report_max_tokens": 1500}],
        "launch": {"model": "sonnet", "effort": "medium", "permission_mode": "default", "name": slug, "unattended": False},
        "stop_blocks": 0,
    }
    st.update(over)
    return st


ORDRE_TEXT = "\n".join("## %d Section %d\ntext\n" % (i, i) for i in range(1, 12))


class TmpCase(unittest.TestCase):
    """Creates an isolated project dir and an isolated 'home' for every test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sr-test-")
        self.project = os.path.join(self.tmp, "proj")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.project)
        os.makedirs(self.home)
        self.env = dict(os.environ)
        for k in ("SUPER_REPROMPT_HOOKS", "CLAUDE_CODE_SESSION_ID", "CLAUDE_PROJECT_DIR", "CLAUDE_CONFIG_DIR"):
            self.env.pop(k, None)
        self.env["SUPER_REPROMPT_HOME"] = os.path.join(self.home, "sr")
        self.env["CLAUDE_CONFIG_DIR"] = os.path.join(self.home, "claude")
        self.env["USERPROFILE"] = self.home
        self.env["HOME"] = self.home
        self.env["PYTHONIOENCODING"] = "utf-8"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_script(self, name, args=(), stdin=None, env_extra=None, cwd=None, timeout=60):
        env = dict(self.env)
        if env_extra:
            env.update(env_extra)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, name)] + list(args),
                           input=(stdin.encode("utf-8") if isinstance(stdin, str) else stdin),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=cwd or self.project, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", errors="replace"), p.stderr.decode("utf-8", errors="replace")

    def make_mission(self, slug="demo-mission", state=None, order=True):
        d = os.path.join(self.project, ".super-reprompt", slug)
        os.makedirs(d, exist_ok=True)
        st = state if state is not None else valid_state(slug)
        with open(os.path.join(d, "STATE.json"), "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
        if order:
            with open(os.path.join(d, "ORDRE.md"), "w", encoding="utf-8") as f:
                f.write(ORDRE_TEXT)
        return d

    def read_state(self, slug="demo-mission"):
        with open(os.path.join(self.project, ".super-reprompt", slug, "STATE.json"), encoding="utf-8") as f:
            return json.load(f)


def write_transcript(path, tool_uses, dup_blobs=True):
    """Write a minimal transcript shaped like the ones Claude Code writes (observed layout)."""
    with open(path, "w", encoding="utf-8") as f:
        for name, inp in tool_uses:
            blk = {"type": "tool_use", "id": "toolu_x", "name": name, "input": inp}
            f.write(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [blk]}}) + "\n")
            if dup_blobs:
                f.write(json.dumps({"type": "api-request-blob", "message": {"content": [blk]}}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "hello"}]}}) + "\n")
