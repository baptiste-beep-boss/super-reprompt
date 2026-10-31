# -*- coding: utf-8 -*-
import json
import os
import re
import shutil
import subprocess
import sys
import unittest

from _t import ROOT, SCRIPTS, TmpCase, valid_state, write_transcript

import hook_suggest as HS  # noqa: E402  (scripts dir is on sys.path via _t)
import _lib as L  # noqa: E402


def load_cases():
    with open(os.path.join(ROOT, "tests", "hook_suggest_cases.json"), encoding="utf-8") as f:
        return json.load(f)["cases"]


class SuggestScorer(unittest.TestCase):
    def test_dataset_shape(self):
        cases = load_cases()
        self.assertGreaterEqual(len(cases), 60)
        neg = [c for c in cases if not c["should_trigger"]]
        self.assertGreaterEqual(len(neg) / len(cases), 0.40)
        self.assertEqual(len({c["id"] for c in cases}), len(cases))
        self.assertTrue({"fr", "en"} <= {c["lang"] for c in cases})

    def test_metrics_on_synthetic_set(self):
        tp = fp = fn = tn = 0
        for c in load_cases():
            score, _labels, why, _lang = HS.score_prompt(c["prompt"])
            fired = why is None and score >= HS.THRESHOLD
            if fired and c["should_trigger"]:
                tp += 1
            elif fired:
                fp += 1
            elif c["should_trigger"]:
                fn += 1
            else:
                tn += 1
        recall = tp / float(tp + fn)
        fp_rate = fp / float(fp + tn)
        self.assertGreaterEqual(recall, 0.90, "recall %.3f (fn=%d)" % (recall, fn))
        self.assertLessEqual(fp_rate, 0.10, "false positive rate %.3f (fp=%d)" % (fp_rate, fp))

    def test_suppressions(self):
        big = "Fais l'audit complet du projet, analyse l'architecture, rédige un rapport avec sources et budget."
        self.assertIsNone(HS.score_prompt(big)[2])
        for text, reason in (("/" + big, "command"), ("!" + big, "command"), ("go direct " + big, "waiver"),
                             ("sans cadrage " + big, "waiver"), ("no framing: " + big, "waiver"),
                             ("don't ask me questions. " + big, "waiver"), ("ok", "short"),
                             ("super-reprompt " + big, "mentions-skill")):
            self.assertEqual(HS.score_prompt(text)[2], reason, text)

    def test_ack_with_long_request_is_still_scored(self):
        s, _l, why, _lang = HS.score_prompt("ok, go: fais l'audit complet du projet et rédige un rapport détaillé avec les sources et un budget.")
        self.assertIsNone(why)
        self.assertGreaterEqual(s, HS.THRESHOLD)

    def test_paths_do_not_count_as_requests(self):
        p = 'regarde ce fichier "C:\\Users\\x\\Documents\\audit complet architecture rapport.pdf" et dis-moi ce que tu en penses stp'
        s, labels, why, _l = HS.score_prompt(p)
        self.assertLess(s, HS.THRESHOLD, labels)

    def test_accents_and_case_are_ignored(self):
        a = HS.score_prompt("STRATÉGIE d'ALLOCATION du PORTEFEUILLE : analyse approfondie et rapport, sources à l'appui")[0]
        b = HS.score_prompt("strategie d'allocation du portefeuille : analyse approfondie et rapport, sources a l'appui")[0]
        self.assertEqual(a, b)

    def test_language_detection(self):
        self.assertEqual(HS.score_prompt("Je veux une analyse complète de mon projet avec un rapport et un budget détaillé")[3], "fr")
        self.assertEqual(HS.score_prompt("I want a complete analysis of my project with a report and a detailed budget")[3], "en")


class SuggestHook(TmpCase):
    BIG_EN = "I want you to do a comprehensive audit of our codebase, analyze the architecture, and write a report with prioritized risks."

    def call(self, prompt, sid="s1", env_extra=None, cwd=None):
        payload = json.dumps({"session_id": sid, "cwd": cwd or self.project, "hook_event_name": "UserPromptSubmit", "prompt": prompt})
        return self.run_script("hook_suggest.py", stdin=payload, env_extra=env_extra)

    def test_emits_one_line_then_cooldown(self):
        rc, out, _e = self.call(self.BIG_EN)
        self.assertEqual(rc, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("/super-reprompt:super-reprompt", out)
        rc, out2, _e = self.call(self.BIG_EN)
        self.assertEqual((rc, out2), (0, ""))
        rc, out3, _e = self.call(self.BIG_EN, sid="another-session")
        self.assertIn("super-reprompt", out3)

    def test_french_output_for_french_prompt(self):
        rc, out, _e = self.call("Je veux que tu fasses l'audit complet de mon projet web, que tu analyses l'architecture et que tu me rédiges un rapport avec les risques.")
        self.assertIn("mission", out)
        self.assertIn("go direct", out)

    def test_silent_on_small_prompt(self):
        rc, out, _e = self.call("Rename the variable foo to bar in utils.py, please, nothing else.")
        self.assertEqual((rc, out), (0, ""))

    def test_off_switch(self):
        rc, out, _e = self.call(self.BIG_EN, env_extra={"SUPER_REPROMPT_HOOKS": "0"})
        self.assertEqual((rc, out), (0, ""))

    def test_empty_invalid_and_odd_stdin(self):
        for payload in ("", "   ", "not json {{", "[]", '{"prompt": 5}', '{"prompt": null}', '"text"', "\xff\xfe\x00"):
            rc, out, _e = self.run_script("hook_suggest.py", stdin=payload.encode("latin-1", errors="replace") if isinstance(payload, str) else payload)
            self.assertEqual((rc, out), (0, ""), repr(payload))

    def test_silent_while_framing_in_this_session(self):
        self.make_mission(state=valid_state(status="framing", framing_session_id="sess-F"))
        rc, out, _e = self.call(self.BIG_EN, sid="sess-F")
        self.assertEqual((rc, out), (0, ""))
        rc, out, _e = self.call(self.BIG_EN, sid="sess-other")
        self.assertIn("super-reprompt", out)

    def test_log_is_written_and_rotated(self):
        self.call(self.BIG_EN)
        log = os.path.join(self.env["SUPER_REPROMPT_HOME"], "hook.log")
        self.assertTrue(os.path.isfile(log))
        with open(log, "a", encoding="utf-8") as f:
            f.write("x" * (210 * 1024))
        env = dict(self.env, SUPER_REPROMPT_HOME=self.env["SUPER_REPROMPT_HOME"])
        old = os.environ.get("SUPER_REPROMPT_HOME")
        os.environ["SUPER_REPROMPT_HOME"] = self.env["SUPER_REPROMPT_HOME"]
        try:
            L.log("test", "after the limit")
        finally:
            if old is None:
                os.environ.pop("SUPER_REPROMPT_HOME", None)
            else:
                os.environ["SUPER_REPROMPT_HOME"] = old
        self.assertTrue(os.path.isfile(log + ".1"))
        self.assertLess(os.path.getsize(log), 1024)

    def test_help(self):
        rc, out, _e = self.run_script("hook_suggest.py", ["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("UserPromptSubmit", out)


class CompactHook(TmpCase):
    def call(self, sid, source="compact"):
        payload = json.dumps({"session_id": sid, "cwd": self.project, "hook_event_name": "SessionStart", "source": source})
        return self.run_script("hook_compact.py", stdin=payload)

    def test_reminder_for_executing_session(self):
        self.make_mission(state=valid_state(status="executing", exec_session_id="exec-1"))
        rc, out, _e = self.call("exec-1")
        self.assertEqual(rc, 0)
        self.assertIn("demo-mission", out)
        self.assertIn("ORDRE.md", out)
        self.assertIn("NOTES.md", out)
        self.assertLessEqual(len(out), 1700)  # ~400 tokens
        self.assertIn("1 required capability", out)

    def test_reminder_for_framing_session_and_french(self):
        self.make_mission(state=valid_state(status="framing", framing_session_id="fr-1", lang="fr"))
        rc, out, _e = self.call("fr-1", "resume")
        self.assertIn("CADRAGE", out)
        self.assertLessEqual(len(out), 1700)

    def test_silent_cases(self):
        self.make_mission(state=valid_state(status="executing", exec_session_id="exec-1"))
        self.assertEqual(self.call("someone-else"), (0, "", ""))
        self.assertEqual(self.call("exec-1", "startup"), (0, "", ""))
        self.assertEqual(self.call(""), (0, "", ""))
        rc, out, _e = self.run_script("hook_compact.py", stdin="garbage")
        self.assertEqual((rc, out), (0, ""))
        rc, out, _e = self.run_script("hook_compact.py", stdin="")
        self.assertEqual((rc, out), (0, ""))

    def test_done_mission_is_silent(self):
        self.make_mission(state=valid_state(status="done", exec_session_id="exec-1"))
        self.assertEqual(self.call("exec-1"), (0, "", ""))

    def test_off_switch(self):
        self.make_mission(state=valid_state(status="executing", exec_session_id="exec-1"))
        payload = json.dumps({"session_id": "exec-1", "cwd": self.project, "source": "compact"})
        rc, out, _e = self.run_script("hook_compact.py", stdin=payload, env_extra={"SUPER_REPROMPT_HOOKS": "0"})
        self.assertEqual((rc, out), (0, ""))


class StopHook(TmpCase):
    def call(self, sid="exec-1", transcript=None, last="Done.", extra=None):
        d = {"session_id": sid, "cwd": self.project, "hook_event_name": "Stop", "stop_hook_active": False,
             "last_assistant_message": last, "transcript_path": transcript or ""}
        if extra:
            d.update(extra)
        return self.run_script("hook_stop.py", stdin=json.dumps(d))

    def executing(self, **over):
        st = valid_state(status="executing", exec_session_id="exec-1", **over)
        return self.make_mission(state=st)

    def test_silent_without_mission_or_other_session(self):
        self.assertEqual(self.call(), (0, "", ""))
        self.executing()
        self.assertEqual(self.call(sid="not-the-exec-session"), (0, "", ""))

    def test_blocks_on_missing_capability_and_report_then_gives_up_after_three(self):
        d = self.executing()
        tr = os.path.join(self.tmp, "t.jsonl")
        write_transcript(tr, [("Bash", {"command": "ls"})])
        seen = []
        for i in range(3):
            rc, out, _e = self.call(transcript=tr)
            self.assertEqual(rc, 0)
            data = json.loads(out)
            self.assertEqual(data["decision"], "block")
            self.assertLessEqual(len(data["reason"].split()), 80)
            self.assertIn("dataviz", data["reason"])
            self.assertIn("REPORT.md", data["reason"])
            seen.append(data["reason"])
        self.assertEqual(self.read_state()["stop_blocks"], 3)
        rc, out, _e = self.call(transcript=tr)   # 4th time: lets go
        self.assertEqual((rc, out), (0, ""))
        with open(os.path.join(d, "NOTES.md"), encoding="utf-8") as f:
            self.assertIn("not executable:", f.read())

    def test_gate_passes_when_everything_is_done(self):
        d = self.executing()
        tr = os.path.join(self.tmp, "t.jsonl")
        write_transcript(tr, [("Skill", {"skill": "dataviz"})])
        with open(os.path.join(d, "REPORT.md"), "w", encoding="utf-8") as f:
            f.write("report")
        rc, out, _e = self.call(transcript=tr)
        self.assertEqual((rc, out), (0, ""))
        st = self.read_state()
        self.assertEqual(st["verification"]["commands"][0]["state"], "executed")
        self.assertEqual(st["verification"]["commands"][0]["exit_code"], 0)
        self.assertGreaterEqual(st["calls"]["K1"], 1)

    def test_plugin_namespaced_skill_counts(self):
        d = self.executing()
        tr = os.path.join(self.tmp, "t.jsonl")
        write_transcript(tr, [("Skill", {"skill": "some-plugin:dataviz"})])
        with open(os.path.join(d, "REPORT.md"), "w", encoding="utf-8") as f:
            f.write("report")
        self.assertEqual(self.call(transcript=tr), (0, "", ""))

    def test_waived_capability_does_not_block(self):
        st = valid_state(status="executing", exec_session_id="exec-1")
        st["capabilities"][0]["removed_reason"] = "skill not installed on this machine"
        d = self.make_mission(state=st)
        with open(os.path.join(d, "REPORT.md"), "w", encoding="utf-8") as f:
            f.write("report")
        tr = os.path.join(self.tmp, "t.jsonl")
        write_transcript(tr, [])
        self.assertEqual(self.call(transcript=tr), (0, "", ""))

    def test_failing_command_blocks_and_missing_command_is_declared_not_executable(self):
        st = valid_state(status="executing", exec_session_id="exec-1")
        st["capabilities"] = []
        st["verification"]["commands"] = [
            {"id": "V1", "cmd": "exit 3", "state": "pending", "reason": None, "plan_b": "run by hand"},
            {"id": "V2", "cmd": "definitely-not-a-real-command-xyz", "state": "pending", "reason": None, "plan_b": "say so"},
            {"id": "V3", "cmd": "git push origin main", "state": "pending", "reason": None, "plan_b": "never"}]
        d = self.make_mission(state=st)
        with open(os.path.join(d, "REPORT.md"), "w", encoding="utf-8") as f:
            f.write("report")
        rc, out, _e = self.call()
        data = json.loads(out)
        self.assertIn("V1 failed (exit 3)", data["reason"])
        self.assertNotIn("V2", data["reason"])
        after = self.read_state()["verification"]["commands"]
        self.assertEqual(after[0]["state"], "executed")
        self.assertEqual(after[0]["exit_code"], 3)
        self.assertEqual(after[1]["state"], "not_executable")
        self.assertEqual(after[2]["state"], "not_executable")
        self.assertIn("refused", after[2]["reason"])

    def test_question_means_waiting_for_user(self):
        self.executing()
        self.assertEqual(self.call(last="Which of the two options do you prefer?"), (0, "", ""))
        self.assertEqual(self.read_state()["stop_blocks"], 0)

    def test_french_block_message(self):
        self.executing(lang="fr")
        rc, out, _e = self.call()
        self.assertIn("inachevée", json.loads(out)["reason"])

    def test_garbage_and_off_switch(self):
        self.executing()
        for payload in ("", "nope", "[]", "{}"):
            rc, out, _e = self.run_script("hook_stop.py", stdin=payload)
            self.assertEqual((rc, out), (0, ""))
        rc, out, _e = self.run_script("hook_stop.py", stdin=json.dumps({"session_id": "exec-1", "cwd": self.project}),
                                      env_extra={"SUPER_REPROMPT_HOOKS": "0"})
        self.assertEqual((rc, out), (0, ""))

    def test_corrupt_state_does_not_crash(self):
        d = self.executing()
        with open(os.path.join(d, "STATE.json"), "w", encoding="utf-8") as f:
            f.write("{broken")
        self.assertEqual(self.call(), (0, "", ""))


class TranscriptCounting(TmpCase):
    def test_counts_assistant_lines_only_and_forms(self):
        tr = os.path.join(self.tmp, "t.jsonl")
        write_transcript(tr, [("Skill", {"skill": "a"}), ("Skill", {"skill": "a"}), ("Agent", {"subagent_type": "reprompt-reviewer", "prompt": "x"}),
                              ("mcp__srv__tool", {}), ("Bash", {"command": "python mission.py status x"})])
        t = L.count_tool_calls(tr)
        self.assertEqual(t["counts"]["Skill:a"], 2)       # the duplicated blobs are ignored
        self.assertEqual(t["counts"]["Agent:reprompt-reviewer"], 1)
        self.assertEqual(t["counts"]["mcp__srv__tool"], 1)
        self.assertTrue(L.capability_called({"name": "reprompt-reviewer", "kind": "agent"}, t))
        self.assertTrue(L.capability_called({"name": "srv", "kind": "mcp"}, t))
        self.assertTrue(L.capability_called({"name": "mission.py", "kind": "script"}, t))
        self.assertFalse(L.capability_called({"name": "b", "kind": "skill"}, t))

    def test_missing_or_broken_transcript(self):
        self.assertEqual(L.count_tool_calls(os.path.join(self.tmp, "none.jsonl"))["counts"], {})
        p = os.path.join(self.tmp, "bad.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"type":"assistant", "tool_use" broken\n\x00\n')
        self.assertEqual(L.count_tool_calls(p)["counts"], {})


@unittest.skipUnless(shutil.which("bash"), "bash not available")
class LauncherChain(TmpCase):
    """Runs the exact command string from hooks/hooks.json through bash (as Claude Code does in shell form)."""

    def command_for(self, event, script):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            cmd = json.load(f)["hooks"][event][0]["hooks"][0]["command"]
        root = ROOT.replace("\\", "/")
        return cmd.replace("${CLAUDE_PLUGIN_ROOT}", root)

    def run_bash(self, cmd, stdin, path=None):
        env = dict(self.env)
        if path is not None:
            env["PATH"] = path
        p = subprocess.run([shutil.which("bash"), "-c", cmd], input=stdin.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=60)
        return p.returncode, p.stdout.decode("utf-8", errors="replace")

    def test_chain_runs_a_working_launcher(self):
        cmd = self.command_for("UserPromptSubmit", "hook_suggest.py")
        payload = json.dumps({"session_id": "chain-1", "cwd": self.project,
                              "prompt": "I want you to do a comprehensive audit of our codebase, analyze the architecture, and write a report with prioritized risks."})
        rc, out = self.run_bash(cmd, payload)
        self.assertEqual(rc, 0)
        self.assertIn("[super-reprompt]", out)

    def test_chain_is_silent_and_exits_0_without_any_python(self):
        cmd = self.command_for("Stop", "hook_stop.py")
        bashdir = os.path.dirname(shutil.which("bash"))
        # PATH holds only bash's own folder when it has no python next to it; skip otherwise
        if any(os.path.exists(os.path.join(bashdir, n)) for n in ("python", "python3", "python.exe", "py.exe")):
            self.skipTest("a python sits next to bash")
        rc, out = self.run_bash(cmd, "{}", path=bashdir)
        self.assertEqual((rc, out), (0, ""))

    def test_all_three_commands_have_the_fallback_chain_and_quoting(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            hooks = json.load(f)["hooks"]
        for event, entries in hooks.items():
            cmd = entries[0]["hooks"][0]["command"]
            self.assertIn("python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/", cmd)
            self.assertIn("|| py -3 \"${CLAUDE_PLUGIN_ROOT}/scripts/", cmd)
            self.assertIn("|| python \"${CLAUDE_PLUGIN_ROOT}/scripts/", cmd)
            self.assertTrue(cmd.rstrip().endswith("; exit 0"))


if __name__ == "__main__":
    unittest.main()
