# -*- coding: utf-8 -*-
import copy
import json
import os
import unittest

from _t import TmpCase, valid_state, write_transcript


class ValidateOrder(TmpCase):
    def validate(self, slug="demo-mission"):
        return self.run_script("validate_order.py", [slug, "--project", self.project])

    def test_valid_state_passes(self):
        self.make_mission()
        rc, out, err = self.validate()
        self.assertEqual(rc, 0, err)
        self.assertIn("OK", out)

    def test_missing_mission_names_existing(self):
        self.make_mission()
        rc, _o, err = self.run_script("validate_order.py", ["nope", "--project", self.project])
        self.assertEqual(rc, 2)
        self.assertIn("demo-mission", err)

    def test_bad_slug_names_valid_form(self):
        rc, _o, err = self.run_script("validate_order.py", ["Bad_Slug", "--project", self.project])
        self.assertEqual(rc, 2)
        self.assertIn("slug", err)
        self.assertIn("lowercase", err)

    def test_missing_order_file(self):
        self.make_mission(order=False)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("ORDRE.md", err)

    def test_trapped_state_names_both_problems(self):
        st = valid_state()
        st["capabilities"][0]["call"] = ""           # required capability without a call
        st["verification"]["commands"][0]["plan_b"] = ""  # verification without plan B
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("capabilities[0]", err)
        self.assertIn("'call'", err)
        self.assertIn("verification.commands[0]", err)
        self.assertIn("plan B", err)

    def test_code_mission_needs_a_command(self):
        st = valid_state()
        st["verification"]["commands"] = []
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("CODE", err)

    def test_non_code_mission_may_have_no_command(self):
        st = valid_state(**{"class": "DOCUMENT"})
        st["verification"]["commands"] = []
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 0, err)

    def test_criterion_needs_source_and_proof_or_unsourced(self):
        st = valid_state()
        st["verification"]["criteria"][0].update({"source": "", "proof": "", "unsourced": False})
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("verification.criteria[0]", err)
        st["verification"]["criteria"][0]["unsourced"] = True
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 0, err)

    def test_more_than_ten_requirements(self):
        st = valid_state()
        st["requirements"] = [{"id": "R%d" % i, "text": "x", "kind": "guessable"} for i in range(11)]
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("at most 10", err)

    def test_budget_rules(self):
        st = valid_state()
        st["budget"]["announced_k"] = 120
        st["budget"]["cap_k"] = 150
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("cap_k", err)
        st["budget"].update({"announced_k": 80, "cap_k": 60})
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("announced_k", err)

    def test_empty_lang_and_empty_deny(self):
        st = valid_state(lang="")
        st["permissions"]["deny"] = []
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("lang", err)
        self.assertIn("deny", err)

    def test_more_than_two_capabilities_per_phase(self):
        st = valid_state()
        caps = []
        for i in range(3):
            c = copy.deepcopy(st["capabilities"][0])
            c["id"] = "K%d" % (i + 1)
            caps.append(c)
        st["capabilities"] = caps
        self.make_mission(state=st)
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("at most 2 per phase", err)

    def test_secret_like_strings_are_flagged(self):
        for secret in ("sk-ant-api03-" + "A" * 30, "ghp_" + "b" * 36, "AKIA" + "C" * 16,
                       "api_key = " + "d" * 24, "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12):
            st = valid_state()
            st["assumptions"] = ["the key is " + secret]
            self.make_mission(state=st)
            rc, _o, err = self.validate()
            self.assertEqual(rc, 2, secret)
            self.assertIn("secret", err)

    def test_secret_in_order_file_is_flagged(self):
        d = self.make_mission()
        with open(os.path.join(d, "ORDRE.md"), "a", encoding="utf-8") as f:
            f.write("\ntoken: " + "x" * 30 + "\n")
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("ORDRE.md", err)

    def test_invalid_json_is_exit_2(self):
        d = self.make_mission()
        with open(os.path.join(d, "STATE.json"), "w", encoding="utf-8") as f:
            f.write("{not json")
        rc, _o, err = self.validate()
        self.assertEqual(rc, 2)
        self.assertIn("not valid JSON", err)

    def test_help(self):
        rc, out, _e = self.run_script("validate_order.py", ["--help"])
        self.assertEqual(rc, 0)
        self.assertIn("slug", out)


class MissionLifecycle(TmpCase):
    def m(self, *args, **kw):
        return self.run_script("mission.py", list(args), **kw)

    def test_init_start_close_flow(self):
        rc, out, err = self.m("init", "refund-fix", "--class", "CODE", "--tier", "standard", "--lang", "fr",
                              "--project", self.project, env_extra={"CLAUDE_CODE_SESSION_ID": "frame-9"})
        self.assertEqual(rc, 0, err)
        st = self.read_state("refund-fix")
        self.assertEqual(st["status"], "framing")
        self.assertEqual(st["framing_session_id"], "frame-9")
        self.assertTrue(os.path.isfile(os.path.join(self.project, ".super-reprompt", "refund-fix", "NOTES.md")))
        # fill in the mission as the framing session would
        full = valid_state("refund-fix", status="framing", lang="fr")
        d = os.path.join(self.project, ".super-reprompt", "refund-fix")
        with open(os.path.join(d, "STATE.json"), "w", encoding="utf-8") as f:
            json.dump(full, f)
        # ready fails without ORDRE.md
        rc, _o, err = self.m("ready", "refund-fix", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("ORDRE.md", err)
        from _t import ORDRE_TEXT
        with open(os.path.join(d, "ORDRE.md"), "w", encoding="utf-8") as f:
            f.write(ORDRE_TEXT)
        rc, _o, err = self.m("ready", "refund-fix", "--project", self.project)
        self.assertEqual(rc, 0, err)
        # start without a session id is refused with a helpful message
        rc, _o, err = self.m("start", "refund-fix", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("session", err)
        rc, out, err = self.m("start", "refund-fix", "--session-id", "exec-1", "--project", self.project)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read_state("refund-fix")["exec_session_id"], "exec-1")
        self.assertEqual(self.read_state("refund-fix")["status"], "executing")
        # idempotent in the same session
        rc, _o, _e = self.m("start", "refund-fix", "--session-id", "exec-1", "--project", self.project)
        self.assertEqual(rc, 0)
        # spent
        rc, out, _e = self.m("spent", "refund-fix", "12.5", "--project", self.project)
        self.assertEqual(rc, 0)
        self.assertEqual(self.read_state("refund-fix")["budget"]["spent_est_k"], 12.5)
        rc, _o, err = self.m("spent", "refund-fix", "-3", "--project", self.project)
        self.assertNotEqual(rc, 0)
        # check lists the open items
        rc, out, _e = self.m("check", "refund-fix", "--project", self.project)
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertFalse(data["ok"])
        self.assertEqual(data["capabilities_not_called"][0]["id"], "K1")
        # close refuses: required capability not called
        rc, _o, err = self.m("close", "refund-fix", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("K1", err)
        # a transcript showing the Skill call lets it close
        tr = os.path.join(self.tmp, "t.jsonl")
        write_transcript(tr, [("Skill", {"skill": "dataviz"})])
        report = os.path.join(self.tmp, "r.md")
        with open(report, "w", encoding="utf-8") as f:
            f.write("final report")
        rc, out, err = self.m("close", "refund-fix", "--transcript", tr, "--report", report, "--project", self.project)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read_state("refund-fix")["status"], "done")
        self.assertTrue(os.path.isfile(os.path.join(d, "REPORT.md")))

    def test_close_accepts_waiver(self):
        self.make_mission(state=valid_state(status="executing", exec_session_id="e1"))
        rc, _o, err = self.m("close", "demo-mission", "--project", self.project)
        self.assertEqual(rc, 2)
        rc, _o, err = self.m("waive", "demo-mission", "K1", "--reason", "skill not installed", "--project", self.project)
        self.assertEqual(rc, 0, err)
        rc, _o, err = self.m("close", "demo-mission", "--project", self.project)
        self.assertEqual(rc, 0, err)

    def test_start_requires_ready(self):
        self.make_mission(state=valid_state(status="framing"))
        rc, _o, err = self.m("start", "demo-mission", "--session-id", "x", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("ready", err)

    def test_reattach_moves_an_executing_mission_to_a_new_session(self):
        self.make_mission(state=valid_state(status="executing", exec_session_id="old"))
        rc, _o, err = self.m("start", "demo-mission", "--session-id", "new", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("--reattach", err)
        rc, _o, err = self.m("start", "demo-mission", "--session-id", "new", "--reattach", "--project", self.project)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read_state()["exec_session_id"], "new")

    def test_start_reads_env_session_id(self):
        self.make_mission()
        rc, _o, err = self.m("start", "demo-mission", "--project", self.project, env_extra={"CLAUDE_CODE_SESSION_ID": "from-env"})
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read_state()["exec_session_id"], "from-env")

    def test_invalid_inputs_name_field_and_valid_values(self):
        rc, _o, err = self.m("init", "ok-slug", "--class", "WRONG", "--tier", "standard", "--lang", "en", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("--class", err)
        self.assertIn("CODE", err)
        rc, _o, err = self.m("init", "ok-slug", "--class", "CODE", "--tier", "huge", "--lang", "en", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("quick", err)
        rc, _o, err = self.m("init", "ok-slug", "--class", "CODE", "--tier", "max", "--lang", "!!", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("--lang", err)

    def test_init_twice_is_refused(self):
        args = ["init", "twice", "--class", "OTHER", "--tier", "quick", "--lang", "en", "--project", self.project]
        self.assertEqual(self.m(*args)[0], 0)
        rc, _o, err = self.m(*args)
        self.assertEqual(rc, 2)
        self.assertIn("already exists", err)

    def test_status_and_path(self):
        self.make_mission()
        rc, out, _e = self.m("status", "demo-mission", "--project", self.project)
        self.assertEqual(rc, 0)
        self.assertIn("status=ready", out)
        rc, out, _e = self.m("status", "demo-mission", "--json", "--project", self.project)
        self.assertEqual(json.loads(out)["slug"], "demo-mission")
        rc, out, _e = self.m("path", "demo-mission", "--file", "ORDRE", "--project", self.project)
        self.assertTrue(out.strip().endswith("ORDRE.md"))

    def test_verify_and_criterion_commands(self):
        self.make_mission()
        rc, _o, err = self.m("verify", "demo-mission", "V1", "--state", "not_executable", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("--reason", err)
        rc, _o, err = self.m("verify", "demo-mission", "V1", "--state", "not_executable", "--reason", "no tests here", "--project", self.project)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read_state()["verification"]["commands"][0]["state"], "not_executable")
        rc, _o, err = self.m("criterion", "demo-mission", "C1", "--passes", "yes", "--project", self.project)
        self.assertEqual(rc, 0, err)
        self.assertTrue(self.read_state()["verification"]["criteria"][0]["passes"])
        rc, _o, err = self.m("verify", "demo-mission", "V9", "--state", "executed", "--project", self.project)
        self.assertEqual(rc, 2)
        self.assertIn("V1", err)

    def test_abort(self):
        self.make_mission()
        rc, _o, err = self.m("close", "demo-mission", "--abort", "--project", self.project)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.read_state()["status"], "aborted")

    def test_help_of_every_subcommand_exits_0(self):
        rc, out, _e = self.m("--help")
        self.assertEqual(rc, 0)
        for sub in ("init", "ready", "start", "status", "spent", "check", "waive", "verify", "criterion", "close", "path"):
            rc, _o, err = self.m(sub, "--help")
            self.assertEqual(rc, 0, "%s: %s" % (sub, err))


if __name__ == "__main__":
    unittest.main()
