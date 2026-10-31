# -*- coding: utf-8 -*-
import glob
import json
import os
import re
import sys
import unittest

from _t import ROOT, SCRIPTS, TmpCase, valid_state

import scan_capabilities as SC  # noqa: E402
import launch as LA  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class FrontMatter(unittest.TestCase):
    def test_plain_quoted_and_folded(self):
        fm = SC.parse_frontmatter('---\nname: demo\ndescription: "Quoted: value"\nother: >\n  folded text\n  continues\ndisable-model-invocation: true\n---\nbody')
        self.assertEqual(fm["name"], "demo")
        self.assertEqual(fm["description"], "Quoted: value")
        self.assertEqual(fm["other"], "folded text continues")
        self.assertEqual(SC.skill_flags(fm), ["manual-only"])

    def test_no_front_matter(self):
        self.assertEqual(SC.parse_frontmatter("just text"), {})
        self.assertEqual(SC.parse_frontmatter("---\nname: x\n"), {})


class ScanCapabilities(TmpCase):
    def build_tree(self):
        ch = self.env["CLAUDE_CONFIG_DIR"]
        write(os.path.join(ch, "skills", "alpha", "SKILL.md"), "---\nname: alpha\ndescription: " + ("Long description. " * 30) + "\n---\nbody")
        write(os.path.join(ch, "skills", "beta", "SKILL.md"), "---\ndescription: Beta skill\ndisable-model-invocation: true\n---\n")
        write(os.path.join(ch, "agents", "helper.md"), "---\nname: helper\ndescription: Helps\nmodel: haiku\ntools: Read\n---\n")
        write(os.path.join(self.project, ".claude", "skills", "projskill", "SKILL.md"), "---\nname: projskill\ndescription: Project only\n---\n")
        root = os.path.join(self.tmp, "plug", "acme", "1.0.0")
        write(os.path.join(root, "skills", "review", "SKILL.md"), "---\nname: review\ndescription: Reviews things\n---\n")
        write(os.path.join(root, "agents", "bot.md"), "---\nname: bot\ndescription: A bot\n---\n")
        write(os.path.join(ch, "plugins", "installed_plugins.json"), json.dumps(
            {"version": 2, "plugins": {"acme@market": [{"scope": "user", "installPath": root, "version": "1.0.0"}],
                                       "off@market": [{"scope": "user", "installPath": root, "version": "1.0.0"}]}}))
        write(os.path.join(ch, "settings.json"), json.dumps({"enabledPlugins": {"off@market": False}, "env": {"SECRET_TOKEN": "do-not-print-me"}}))
        write(os.path.join(self.home, ".claude.json"), json.dumps(
            {"mcpServers": {"memory": {"command": "npx", "env": {"API_KEY": "do-not-print-me-either"}}}, "projects": {}}))
        write(os.path.join(self.project, ".mcp.json"), json.dumps({"mcpServers": {"projsrv": {"url": "https://example.invalid/mcp", "headers": {"Authorization": "Bearer xxx"}}}}))

    def test_index_content_budget_and_privacy(self):
        self.build_tree()
        rc, out, err = self.run_script("scan_capabilities.py", ["--project", self.project])
        self.assertEqual(rc, 0, err)
        self.assertIn("alpha (user)", out)
        self.assertIn("beta (user)", out)
        self.assertIn("[manual-only]", out)
        self.assertIn("projskill (project)", out)
        self.assertIn("helper (user)", out)
        self.assertIn("memory", out)
        self.assertIn("projsrv", out)
        self.assertIn("plugin acme@market", out)
        self.assertNotIn("off@market", out)           # disabled plugin skipped
        self.assertNotIn("do-not-print-me", out + err)  # secrets never read into the output
        self.assertNotIn("Bearer", out)
        self.assertIn("fingerprint=", out)
        # description cut at 120 characters
        alpha = [ln for ln in out.splitlines() if ln.startswith("- alpha")][0]
        self.assertLessEqual(len(alpha.split(": ", 1)[1]), 121)
        self.assertLessEqual(len(out) / 3.5, 1500)

    def test_deterministic(self):
        self.build_tree()
        a = self.run_script("scan_capabilities.py", ["--project", self.project])
        b = self.run_script("scan_capabilities.py", ["--project", self.project])
        self.assertEqual(a, b)

    def test_budget_truncates(self):
        self.build_tree()
        ch = self.env["CLAUDE_CONFIG_DIR"]
        for i in range(200):
            write(os.path.join(ch, "skills", "s%03d" % i, "SKILL.md"), "---\nname: s%03d\ndescription: %s\n---\n" % (i, "word " * 30))
        rc, out, _e = self.run_script("scan_capabilities.py", ["--project", self.project, "--max-tokens", "600"])
        self.assertEqual(rc, 0)
        self.assertLessEqual(len(out) / 3.5, 600)
        self.assertIn("omitted", out)

    def test_json_mode_and_empty_machine(self):
        rc, out, err = self.run_script("scan_capabilities.py", ["--project", self.project, "--json"])
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["total"], 0)
        self.assertIn("warning", err)   # missing sources are only warnings

    def test_profile_detected(self):
        write(os.path.join(self.env["SUPER_REPROMPT_HOME"], "profile.md"), "---\nlevel: pro\nlang: fr\n---\ntext")
        rc, out, _e = self.run_script("scan_capabilities.py", ["--project", self.project])
        self.assertIn("user=found(lang=fr,level=pro)", out)

    def test_bad_max_tokens(self):
        rc, _o, err = self.run_script("scan_capabilities.py", ["--max-tokens", "5"])
        self.assertEqual(rc, 2)
        self.assertIn("--max-tokens", err)


class LaunchScript(TmpCase):
    def test_version_parse(self):
        self.assertEqual(LA.parse_version("2.1.266 (Claude Code)"), (2, 1, 266))
        self.assertIsNone(LA.parse_version("nothing"))

    def test_dry_run_builds_expected_command(self):
        self.make_mission()
        fake = os.path.join(self.tmp, "bin")
        os.makedirs(fake)
        if os.name == "nt":
            write(os.path.join(fake, "claude.cmd"),
                  "@echo off\r\nif \"%1\"==\"--version\" goto v\r\necho   --bg, --background  Start as background agent\r\nexit /b 0\r\n:v\r\necho 2.1.300 Claude Code\r\nexit /b 0\r\n")
        else:
            write(os.path.join(fake, "claude"), "#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo '2.1.300 (Claude Code)'; else echo '  --bg, --background  Start as background agent'; fi\n")
            os.chmod(os.path.join(fake, "claude"), 0o755)
        env = {"PATH": fake + os.pathsep + self.env.get("PATH", "")}
        rc, out, err = self.run_script("launch.py", ["demo-mission", "--project", self.project, "--dry-run"], env_extra=env)
        self.assertEqual(rc, 0, err + out)
        self.assertIn("DRY RUN", out)
        self.assertIn("--bg", out)
        self.assertIn("--name demo-mission", out)
        self.assertIn("--model sonnet", out)
        self.assertIn("--effort medium", out)
        self.assertIn("--permission-mode default", out)
        self.assertIn("ORDRE.md", out)
        self.assertNotIn("/fork", out)

    def test_fallback_when_claude_missing(self):
        self.make_mission()
        env = {"PATH": os.path.dirname(sys.executable)}  # python only: no claude
        rc, out, err = self.run_script("launch.py", ["demo-mission", "--project", self.project, "--dry-run"], env_extra=env)
        self.assertEqual(rc, 3, err)
        self.assertIn("Manual fallback", out)

    def test_refuses_unready_or_invalid_mission(self):
        self.make_mission(state=valid_state(status="framing"))
        rc, _o, err = self.run_script("launch.py", ["demo-mission", "--project", self.project, "--dry-run"])
        self.assertEqual(rc, 2)
        self.assertIn("ready", err)
        st = valid_state()
        st["launch"]["effort"] = "turbo"
        self.make_mission(state=st)
        rc, _o, err = self.run_script("launch.py", ["demo-mission", "--project", self.project, "--dry-run"])
        self.assertEqual(rc, 2)
        self.assertIn("effort", err)


class EveryScriptHasHelp(unittest.TestCase):
    def test_help_exit_codes(self):
        import subprocess
        for name in sorted(os.path.basename(p) for p in glob.glob(os.path.join(SCRIPTS, "*.py"))):
            if name == "_lib.py":
                continue
            p = subprocess.run([sys.executable, os.path.join(SCRIPTS, name), "--help"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            self.assertEqual(p.returncode, 0, name)
            self.assertTrue(p.stdout.strip(), name)


class PluginFiles(unittest.TestCase):
    def test_manifest(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["name"], "super-reprompt")
        self.assertRegex(m["name"], r"^[a-z0-9-]+$")
        self.assertNotIn("claude", m["name"])

    def test_hooks_file(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            h = json.load(f)["hooks"]
        self.assertEqual(sorted(h), ["SessionStart", "Stop", "UserPromptSubmit"])
        self.assertEqual(h["SessionStart"][0]["matcher"], "compact|resume")
        for event, groups in h.items():
            for g in groups:
                for hk in g["hooks"]:
                    self.assertEqual(hk["type"], "command")
                    self.assertNotIn("onFailure", hk)
                    self.assertLessEqual(hk["timeout"], 300)
        self.assertLessEqual(h["UserPromptSubmit"][0]["hooks"][0]["timeout"], 10)

    def test_agents(self):
        want = {"reprompt-scout": "Read, Glob, Grep", "reprompt-reviewer": "Read, Glob, Grep", "reprompt-reader": "Read"}
        for name, tools in want.items():
            with open(os.path.join(ROOT, "agents", name + ".md"), encoding="utf-8") as f:
                fm = SC.parse_frontmatter(f.read())
            self.assertEqual(fm["name"], name)
            self.assertTrue(fm["description"])
            self.assertEqual(fm["tools"], tools)     # read-only
            self.assertNotIn(":", fm["name"])
            for banned in ("permissionMode", "hooks", "mcpServers", "initialPrompt"):
                self.assertNotIn(banned, fm)         # ignored in plugin agents
        with open(os.path.join(ROOT, "agents", "reprompt-reader.md"), encoding="utf-8") as f:
            self.assertEqual(SC.parse_frontmatter(f.read())["omitClaudeMd"], "true")

    def test_profile_example_is_generic_and_parseable(self):
        with open(os.path.join(ROOT, "profile-example", "profile.md"), encoding="utf-8") as f:
            text = f.read()
        fm = SC.parse_frontmatter(text)
        self.assertEqual(fm["level"], "mixed")
        self.assertLess(len(text.split()), 700)

    # The one string the maintainer published on purpose: the repository's GitHub handle. The install line and
    # the manifest's homepage cannot work without it, and a public account handle is not a leak. Every other
    # form of the same name stays banned, which the next test checks.
    PUBLIC_HANDLE = "bapti" + "ste-beep-boss"
    # Anchored: the handle is neutralised only when nothing word-like follows it, so a longer string that
    # merely starts with it (a private repository name, say) is still caught.
    HANDLE_RX = re.compile(PUBLIC_HANDLE + r"(?![\w-])", re.I)

    def test_no_personal_data_in_the_plugin(self):
        # words are assembled so this test file itself stays clean
        banned = [re.compile(p, re.I) for p in ("des" + "ag", "bapti" + "ste", "gm" + "gn", r"\bbour" + "se", "second" + r"\s*brain")]
        banned.append(re.compile(r"\b" + "M" + "IE" + r"\b"))
        hits = []
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
            for fn in filenames:
                if fn == "CONTRAT.md" or fn.endswith(".pyc"):   # CONTRAT.md is the orchestrator's brief, not part of the product
                    continue
                p = os.path.join(dirpath, fn)
                try:
                    with open(p, encoding="utf-8", errors="replace") as f:
                        text = f.read()
                except Exception:
                    continue
                text = self.HANDLE_RX.sub("<handle>", text)
                for rx in banned:
                    if rx.search(text):
                        hits.append((os.path.relpath(p, ROOT), rx.pattern))
        self.assertEqual(hits, [])

    def test_the_handle_exemption_is_exactly_the_handle_and_nothing_else(self):
        """The exemption must not become a hole: any other form of the name is still caught."""
        rx = re.compile("bapti" + "ste", re.I)
        for leak in ("bapti" + "ste", "bapti" + "ste D.", "C:/Users/bapti" + "ste/notes",
                     self.PUBLIC_HANDLE + "-private", self.PUBLIC_HANDLE + "2"):
            self.assertIsNotNone(rx.search(self.HANDLE_RX.sub("<handle>", leak)), leak)
        for allowed in (self.PUBLIC_HANDLE, self.PUBLIC_HANDLE + "/super-reprompt",
                        "https://github.com/" + self.PUBLIC_HANDLE):
            self.assertIsNone(rx.search(self.HANDLE_RX.sub("<handle>", allowed)), allowed)

    def test_scripts_use_only_the_standard_library_and_no_network(self):
        allowed = {"argparse", "copy", "shlex", "hashlib", "json", "os", "re", "shutil", "subprocess", "sys", "time", "unicodedata", "pathlib", "_lib",
                   "validate_order", "glob", "tempfile", "unittest"}
        net = re.compile(r"(?m)^\s*(?:import|from)\s+(socket|urllib|http|requests|ftplib|smtplib|ssl|xmlrpc)\b")
        for p in glob.glob(os.path.join(SCRIPTS, "*.py")):
            with open(p, encoding="utf-8") as f:
                text = f.read()
            for m in re.finditer(r"(?m)^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)", text):
                self.assertIn(m.group(1), allowed, "%s imports %s" % (os.path.basename(p), m.group(1)))
            self.assertIsNone(net.search(text), os.path.basename(p))


if __name__ == "__main__":
    unittest.main()
