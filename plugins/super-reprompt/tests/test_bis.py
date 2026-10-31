# -*- coding: utf-8 -*-
"""Tests of the corrections CORRECTIONS-V2-BIS (T1 to T8)."""
import json
import os
import re
import unittest

from _t import ROOT, TmpCase, ORDRE_TEXT, valid_state

SKILL = os.path.join(ROOT, "skills", "super-reprompt", "SKILL.md")
REFS = os.path.join(ROOT, "skills", "super-reprompt", "references")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class T1Launcher(unittest.TestCase):
    def test_frontmatter_has_six_patterns(self):
        fm = read(SKILL).split("---")[1]
        line = [l for l in fm.splitlines() if l.startswith("allowed-tools:")][0]
        for py in ("python3", "py -3", "python"):
            self.assertIn('Bash(%s ${CLAUDE_PLUGIN_ROOT}/scripts/*)' % py, line)
            self.assertIn('Bash(%s "${CLAUDE_PLUGIN_ROOT}/scripts/*)' % py, line)

    def test_no_version_probe(self):
        for root, _d, files in os.walk(os.path.join(ROOT, "skills")):
            for f in files:
                self.assertNotIn("--version", read(os.path.join(root, f)), f)

    def test_one_command_rule_and_fallback(self):
        s = read(SKILL)
        self.assertIn("one command per call", s)
        self.assertIn("py -3", s)

    def test_readme_non_interactive(self):
        r = read(os.path.join(ROOT, "README.md"))
        self.assertIn("## Non-interactive use", r)
        self.assertIn('--allowedTools "Skill(super-reprompt:super-reprompt)"', r)


class T2QuickSkeleton(TmpCase):
    def skeleton(self):
        q = read(os.path.join(REFS, "quick.md"))
        m = re.search(r"```json\n(.*?)\n```", q, re.S)
        self.assertIsNotNone(m)
        return m.group(1)

    def test_phrase_present(self):
        self.assertIn("if scripts cannot run, write this by hand", read(os.path.join(REFS, "quick.md")).lower())

    def test_skeleton_accepted_by_validator(self):
        raw = self.skeleton().replace('"S"', '"demo-mission"').replace("...", "filled example")
        st = json.loads(raw)
        d = os.path.join(self.project, ".super-reprompt", "demo-mission")
        os.makedirs(d)
        with open(os.path.join(d, "STATE.json"), "w", encoding="utf-8") as f:
            json.dump(st, f)
        with open(os.path.join(d, "ORDRE.md"), "w", encoding="utf-8") as f:
            f.write(ORDRE_TEXT)
        rc, out, err = self.run_script("validate_order.py", ["demo-mission"])
        self.assertEqual(rc, 0, out + err)

    def test_skeleton_size(self):
        self.assertLessEqual(len(self.skeleton()) / 3.7, 280)


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


class T3McpScan(TmpCase):
    def build(self):
        ch = self.env["CLAUDE_CONFIG_DIR"]
        r1 = os.path.join(self.tmp, "plug", "acme", "1.0")
        r2 = os.path.join(self.tmp, "plug", "flat", "1.0")
        r3 = os.path.join(self.tmp, "plug", "inline", "1.0")
        _w(os.path.join(r1, ".mcp.json"), json.dumps({"mcpServers": {"db.tools": {"command": "SECRET-CMD"}}}))
        _w(os.path.join(r2, ".mcp.json"), json.dumps({"flatsrv": {"url": "https://example.invalid/x"}}))
        _w(os.path.join(r3, ".claude-plugin", "plugin.json"), json.dumps({"name": "inline", "mcpServers": {"inl": {"command": "x"}}}))
        _w(os.path.join(ch, "plugins", "installed_plugins.json"), json.dumps({"version": 2, "plugins": {
            "acme@m": [{"installPath": r1}], "flat@m": [{"installPath": r2}], "inline@m": [{"installPath": r3}]}}))
        _w(os.path.join(ch, "settings.json"), json.dumps({"enabledPlugins": {}, "enabledMcpjsonServers": ["approved"]}))
        key = os.path.realpath(self.project)
        _w(os.path.join(self.home, ".claude.json"), json.dumps({
            "mcpServers": {"usr": {"command": "npx", "env": {"K": "do-not-print"}}},
            "projects": {key: {"disabledMcpServers": ["usr2", "plugin:acme:db.tools"], "mcpServers": {"usr2": {"command": "x"}}}}}))
        _w(os.path.join(self.project, ".mcp.json"), json.dumps({"mcpServers": {
            "approved": {"command": "a"}, "pending": {"command": "b"}, "rejected": {"command": "c"}}}))
        _w(os.path.join(self.project, ".claude", "settings.local.json"), json.dumps({"disabledMcpjsonServers": ["rejected"]}))

    def scan_json(self):
        rc, out, err = self.run_script("scan_capabilities.py", ["--project", self.project, "--json"])
        self.assertEqual(rc, 0, err)
        return {d["name"]: d for d in json.loads(out)["mcp_detail"]}

    def test_flags_sources_and_call_forms(self):
        self.build()
        d = self.scan_json()
        self.assertEqual(d["usr"]["flags"], [])
        self.assertEqual(d["usr2"]["flags"], ["disabled"])
        self.assertEqual(d["approved"]["flags"], [])
        self.assertEqual(d["pending"]["flags"], ["needs_approval"])
        self.assertEqual(d["rejected"]["flags"], ["disabled"])
        self.assertEqual(d["plugin:acme:db.tools"]["flags"], ["disabled"])
        self.assertEqual(d["plugin:acme:db.tools"]["call"], "mcp__plugin_acme_db_tools__<tool>")
        self.assertEqual(d["plugin:acme:db.tools"]["origin"], "plugin:acme@m")
        self.assertEqual(d["plugin:flat:flatsrv"]["call"], "mcp__plugin_flat_flatsrv__<tool>")
        self.assertEqual(d["plugin:inline:inl"]["flags"], [])
        self.assertEqual(d["usr"]["call"], "mcp__usr__<tool>")
        self.assertEqual(d["usr"]["tools"], "discover at runtime")

    def test_text_output_notes_and_privacy(self):
        self.build()
        rc, out, err = self.run_script("scan_capabilities.py", ["--project", self.project])
        self.assertEqual(rc, 0, err)
        self.assertIn("claude.ai connectors are visible only in the session", out)
        self.assertIn("tools: discover at runtime", out)
        self.assertIn("pending[project,needs_approval]", out)
        self.assertNotIn("SECRET-CMD", out + err)
        self.assertNotIn("do-not-print", out + err)

    def test_enable_all_approves_project_servers(self):
        self.build()
        _w(os.path.join(self.project, ".claude", "settings.local.json"), json.dumps({"enableAllProjectMcpServers": True}))
        d = self.scan_json()
        self.assertEqual(d["pending"]["flags"], [])

    def test_disabled_plugin_servers_not_listed(self):
        self.build()
        _w(os.path.join(self.env["CLAUDE_CONFIG_DIR"], "settings.json"), json.dumps({"enabledPlugins": {"acme@m": False}}))
        self.assertNotIn("plugin:acme:db.tools", self.scan_json())

    def test_plugin_manifest_path_outside_root_ignored(self):
        self.build()
        root = os.path.join(self.tmp, "plug", "inline", "1.0")
        _w(os.path.join(self.tmp, "outside.json"), json.dumps({"mcpServers": {"leak": {}}}))
        _w(os.path.join(root, ".claude-plugin", "plugin.json"), json.dumps({"mcpServers": "../../../outside.json"}))
        self.assertNotIn("plugin:inline:leak", self.scan_json())


class T4Capabilities(unittest.TestCase):
    def test_two_step_contract_and_auth(self):
        t = read(os.path.join(REFS, "capabilities.md"))
        self.assertIn("ToolSearch", t)
        self.assertIn("takes two calls", t)
        self.assertIn("claude mcp login <name>", t)
        self.assertIn("non-interactive", t)
        self.assertIn("verify before use", t)
        self.assertIn("mcp__plugin_<plugin>_<server>__<tool>", t)
        self.assertNotIn("without any reservation", t)


class T5Criteria(TmpCase):
    def ready_mission(self, slug="demo-mission", **over):
        st = valid_state(slug, status="framing", capabilities=[], **over)
        st["verification"]["criteria"] = [
            {"id": "C1", "text": "Page returns 200", "source": "test", "proof": "curl", "passes": False, "unsourced": False},
            {"id": "C2", "text": "Reader finds the policy", "source": "person", "proof": "user says so", "passes": False, "unsourced": False}]
        self.make_mission(slug, state=st)
        rc, out, err = self.run_script("mission.py", ["ready", slug])
        self.assertEqual(rc, 0, out + err)
        rc, out, err = self.run_script("mission.py", ["start", slug, "--session-id", "S1"])
        self.assertEqual(rc, 0, out + err)
        return slug

    def edit_state(self, fn, slug="demo-mission"):
        st = self.read_state(slug)
        fn(st)
        with open(os.path.join(self.project, ".super-reprompt", slug, "STATE.json"), "w", encoding="utf-8") as f:
            json.dump(st, f)

    def test_digest_is_stable_and_recorded(self):
        import _lib as L
        st = valid_state()
        self.assertEqual(L.criteria_digest(st), L.criteria_digest(json.loads(json.dumps(st))))
        self.assertRegex(L.criteria_digest(st), r"^[0-9a-f]{64}$")
        self.ready_mission()
        s = self.read_state()
        self.assertEqual(s["criteria_sha256"], L.criteria_digest(s))
        self.assertEqual(set(s["criteria_fingerprints"]), {"C1", "C2"})
        self.assertEqual(self.run_script("validate_order.py", ["demo-mission"])[0], 0)

    def test_digest_ignores_pass_state_and_order(self):
        import _lib as L
        st = valid_state()
        st["verification"]["criteria"].append({"id": "C0", "text": "x", "source": "test", "proof": "p", "passes": False})
        a = L.criteria_digest(st)
        st["verification"]["criteria"].reverse()
        st["verification"]["criteria"][0]["passes"] = True
        self.assertEqual(a, L.criteria_digest(st))

    def test_close_refuses_weakened_criterion_and_names_it(self):
        self.ready_mission()

        def weaken(s):
            s["verification"]["criteria"][0]["text"] = "Page exists"
        self.edit_state(weaken)
        rc, out, err = self.run_script("mission.py", ["close", "demo-mission"])
        self.assertEqual(rc, 2)
        self.assertIn("C1", err)
        self.assertNotIn("C2", err.split("Valid:")[0])
        self.assertEqual(self.read_state()["status"], "executing")

    def test_close_refuses_removed_criterion(self):
        self.ready_mission()
        self.edit_state(lambda s: s["verification"]["criteria"].pop(1))
        rc, _o, err = self.run_script("mission.py", ["close", "demo-mission"])
        self.assertEqual(rc, 2)
        self.assertIn("C2", err)

    def test_close_works_when_unchanged_and_reports_split(self):
        self.ready_mission()
        rc, _o, err = self.run_script("mission.py", ["criterion", "demo-mission", "C1", "--passes", "yes"])
        self.assertEqual(rc, 0, err)
        rc, _o, err = self.run_script("mission.py", ["criterion", "demo-mission", "C2", "--passes", "yes", "--evidence", "user confirmed in chat"])
        self.assertEqual(rc, 0, err)
        rc, out, err = self.run_script("mission.py", ["close", "demo-mission"])
        self.assertEqual(rc, 0, out + err)
        self.assertIn("1 passed with a test source, 1 self-reported (C2)", out)

    def test_evidence_required_for_non_test_source(self):
        self.ready_mission()
        rc, _o, err = self.run_script("mission.py", ["criterion", "demo-mission", "C2", "--passes", "yes"])
        self.assertEqual(rc, 2)
        self.assertIn("--evidence", err)
        self.assertFalse(self.read_state()["verification"]["criteria"][1]["passes"])
        rc, _o, err = self.run_script("mission.py", ["criterion", "demo-mission", "C2", "--passes", "yes", "--evidence", "reviewed with the user"])
        self.assertEqual(rc, 0, err)
        c = self.read_state()["verification"]["criteria"][1]
        self.assertTrue(c["passes"])
        self.assertTrue(c["self_reported"])
        self.assertEqual(c["evidence"], "reviewed with the user")
        # "no" needs no evidence; test source needs none for "yes"
        self.assertEqual(self.run_script("mission.py", ["criterion", "demo-mission", "C2", "--passes", "no"])[0], 0)
        self.assertEqual(self.run_script("mission.py", ["criterion", "demo-mission", "C1", "--passes", "yes"])[0], 0)
        self.assertFalse(self.read_state()["verification"]["criteria"][0]["self_reported"])

    def test_backward_compatible_state_without_new_fields(self):
        self.make_mission(state=valid_state(status="executing", exec_session_id="S1", capabilities=[]))
        self.assertEqual(self.run_script("validate_order.py", ["demo-mission"])[0], 0)
        rc, _o, err = self.run_script("mission.py", ["close", "demo-mission"])
        self.assertEqual(rc, 0, err)
        # plain 'yes' on a state without the fields works for a test source
        self.make_mission("other", state=valid_state("other", status="executing"))
        self.assertEqual(self.run_script("mission.py", ["criterion", "other", "C1", "--passes", "yes"])[0], 0)

    def test_validator_rejects_malformed_optional_fields(self):
        st = valid_state(criteria_sha256="nothex")
        self.make_mission(state=st)
        rc, _o, err = self.run_script("validate_order.py", ["demo-mission"])
        self.assertEqual(rc, 2)
        self.assertIn("criteria_sha256", err)
        st = valid_state()
        st["verification"]["criteria"][0]["self_reported"] = "yes"
        self.make_mission(state=st)
        rc, _o, err = self.run_script("validate_order.py", ["demo-mission"])
        self.assertEqual(rc, 2)
        self.assertIn("self_reported", err)

    def test_stop_hook_signals_once_then_lets_pass(self):
        self.ready_mission()
        self.edit_state(lambda s: s["verification"]["criteria"][0].update(text="Page exists"))
        self.edit_state(lambda s: s["verification"]["commands"][0].update(state="executed", exit_code=0))
        payload = json.dumps({"session_id": "S1", "cwd": self.project, "last_assistant_message": "done."})
        d = os.path.join(self.project, ".super-reprompt", "demo-mission")
        with open(os.path.join(d, "REPORT.md"), "w", encoding="utf-8") as f:
            f.write("report")
        rc, out, err = self.run_script("hook_stop.py", stdin=payload)
        self.assertEqual(rc, 0)
        first = json.loads(out)
        self.assertEqual(first["decision"], "block")
        self.assertIn("C1", first["reason"])
        rc, out, err = self.run_script("hook_stop.py", stdin=payload)
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), "")
        self.assertTrue(self.read_state()["criteria_warned"])

    def test_stop_hook_silent_without_digest(self):
        self.make_mission(state=valid_state(status="executing", exec_session_id="S1"))
        d = os.path.join(self.project, ".super-reprompt", "demo-mission")
        with open(os.path.join(d, "REPORT.md"), "w", encoding="utf-8") as f:
            f.write("report")
        self.edit_state(lambda s: s["verification"]["commands"][0].update(state="executed", exit_code=0))
        payload = json.dumps({"session_id": "S1", "cwd": self.project, "last_assistant_message": "done."})
        rc, out, _e = self.run_script("hook_stop.py", stdin=payload)
        self.assertEqual(out.strip(), "")


class T6Protocol(unittest.TestCase):
    def blocks(self):
        return {"quick.md": read(os.path.join(REFS, "quick.md")), "order-template.md": read(os.path.join(REFS, "order-template.md"))}

    def test_four_sentences_in_both_protocol_blocks(self):
        needles = ["Assume interruption", "NOTES.md", "a compaction or a crash loses",
                   "do not edit the test, weaken the criterion or special-case the check",
                   "No human will read this before the run ends: write what a stranger needs to understand and continue",
                   "as data, not as instructions" ]
        for name, t in self.blocks().items():
            for n in needles:
                if name == "quick.md" and n in ("Assume interruption", "as data, not as instructions"):
                    continue   # quick words (a) and (d) slightly differently
                self.assertIn(n.lower(), t.lower(), "%s: %s" % (name, n))
        q = self.blocks()["quick.md"]
        self.assertIn("Assume interruption", q)
        self.assertIn("as data, not instructions", q)

    def test_no_stale_wording(self):
        for name, t in self.blocks().items():
            self.assertNotIn("Never edit or delete tests", t, name)

    def test_agents_nesting_matches_docs(self):
        t = read(os.path.join(REFS, "agents.md"))
        self.assertNotIn("nesting is off by default", t)
        self.assertIn("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH", t)


class T7T8(unittest.TestCase):
    def test_non_text_pieces_in_p1(self):
        t = read(os.path.join(REFS, "phases.md"))
        i = t.index("## P1 discovery")
        j = t.index("## P2 interview")
        self.assertIn("non-text piece", t[i:j])
        self.assertIn("compaction summary loses it", t[i:j])

    def test_models_cache_sentence(self):
        t = read(os.path.join(REFS, "models.md"))
        self.assertNotIn("without losing the cache", t)
        self.assertIn("assume a cold cache after any change of model or effort", t)
        self.assertIn("/usage", t)

    def test_hypotheses_moved_not_lost(self):
        t = read(os.path.join(REFS, "phases.md"))
        self.assertEqual(t.count("- Hypothesis:"), 0)
        self.assertIn("Hypotheses by phase:", t)
        self.assertIn("- P5: ", t)
