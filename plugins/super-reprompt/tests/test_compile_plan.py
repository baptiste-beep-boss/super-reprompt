# -*- coding: utf-8 -*-
"""Lot 2 V3.1 : ORDRE + STATE valides -> PLAN.json compile (IDs stables, dependances, criteres, source_order_hash),
scelle automatiquement avec l'empreinte structurelle du plan ; `mission.py ready` declenche tout."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import SCRIPTS, TmpCase, valid_state

import contracts as C
import compile_plan as CP


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Compile(TmpCase):
    def mdir(self, slug="demo-mission"):
        return os.path.join(self.project, ".super-reprompt", slug)

    def test_fallback_one_task_per_requirement_plus_verification(self):
        self.make_mission()
        plan, rep = CP.compile_plan(self.project, "demo-mission")
        ids = [t["id"] for t in plan["tasks"]]
        self.assertEqual(ids, ["T-R1", "T-VERIF"])
        self.assertEqual(plan["source_order_hash"], _sha(os.path.join(self.mdir(), "ORDRE.md")))
        self.assertEqual(C.validate("plan", plan, strict=True), [])
        v = plan["tasks"][1]
        self.assertEqual(v["deps"], ["T-R1"])
        self.assertIn("C1", v["covers"])
        self.assertEqual(v["preuve"], "exit 0")
        self.assertTrue(all(t["status"] in ("ready", "proposed") for t in plan["tasks"]))
        self.assertEqual(plan["tasks"][0]["status"], "ready")
        self.assertEqual(plan["tasks"][1]["status"], "proposed")
        self.assertEqual(C.read_json(os.path.join(self.mdir(), "PLAN.json")), plan)

    def test_explicit_tasks_from_framing_are_honoured(self):
        st = valid_state("demo-mission", tasks=[
            {"id": "T1", "title": "page", "covers": ["R1"], "files": ["site/"], "preuve": "V1", "model": "sonnet", "volume_tokens": 50000},
            {"id": "T2", "title": "controle", "deps": ["T1"], "covers": ["C1"], "acceptance_criteria": ["HTTP 200"], "preuve": "exit 0"}])
        self.make_mission(state=st)
        plan, _ = CP.compile_plan(self.project, "demo-mission")
        self.assertEqual([t["id"] for t in plan["tasks"]], ["T1", "T2"])
        self.assertEqual(plan["tasks"][0]["preuve"], "exit 0")           # V1 resolved to its command
        self.assertEqual(plan["tasks"][0]["model"], "sonnet")
        self.assertEqual(plan["tasks"][0]["acceptance_criteria"], ["V1 : exit 0"])

    def test_errors_are_named_and_nothing_written(self):
        bad = valid_state("demo-mission", tasks=[{"id": "T1", "covers": ["R1"], "deps": ["T9"], "preuve": "exit 0"}])
        self.make_mission(state=bad)
        with self.assertRaises(C.ContractError) as e:
            CP.compile_plan(self.project, "demo-mission")
        self.assertIn("T9", str(e.exception))
        self.assertIn("C1", str(e.exception))                              # criterion covered by no task
        self.assertFalse(os.path.exists(os.path.join(self.mdir(), "PLAN.json")))

    def test_missing_order_refused(self):
        self.make_mission(order=False)
        with self.assertRaises(C.ContractError):
            CP.compile_plan(self.project, "demo-mission")

    def test_recompile_is_idempotent_and_keeps_progress(self):
        self.make_mission()
        CP.compile_plan(self.project, "demo-mission")
        p = os.path.join(self.mdir(), "PLAN.json")
        plan = C.read_json(p)
        plan["tasks"][0]["status"] = "running"
        C.atomic_write_json(p, plan)
        plan2, rep = CP.compile_plan(self.project, "demo-mission")
        self.assertEqual(plan2["tasks"][0]["status"], "running")
        self.assertEqual(rep["action"], "inchange")

    def test_changed_order_after_start_needs_an_amendment(self):
        self.make_mission()
        CP.compile_plan(self.project, "demo-mission")
        p = os.path.join(self.mdir(), "PLAN.json")
        plan = C.read_json(p)
        plan["tasks"][0]["status"] = "running"
        C.atomic_write_json(p, plan)
        with open(os.path.join(self.mdir(), "ORDRE.md"), "a", encoding="utf-8") as f:
            f.write("\nexigence ajoutee\n")
        with self.assertRaises(C.ContractError) as e:
            CP.compile_plan(self.project, "demo-mission")
        self.assertIn("avenant", str(e.exception))

    def test_structure_sha_ignores_progress_fields(self):
        self.make_mission()
        plan, _ = CP.compile_plan(self.project, "demo-mission")
        a = C.plan_structure_sha(plan)
        plan["tasks"][0].update(status="done", attempt=3, receipt="r1", updated_at="2026-11-24T00:00:00Z")
        self.assertEqual(C.plan_structure_sha(plan), a)
        plan["tasks"][0]["deps"] = ["T-VERIF"]
        self.assertNotEqual(C.plan_structure_sha(plan), a)


class ReadyCompilesAndSeals(TmpCase):
    """End to end: framing -> `mission.py ready` -> PLAN.json + SCELLE.json linked by hashes, without a manual step."""

    def test_ready_compiles_plan_and_seals_it(self):
        st = valid_state("demo-mission", status="framing", seal={"perimeter": ["site"], "color": "vert"})
        d = self.make_mission(state=st)
        rc, out, err = self.run_script("mission.py", ["ready", "demo-mission", "--project", self.project])
        self.assertEqual(rc, 0, out + err)
        md = os.path.join(self.project, ".super-reprompt", "demo-mission")
        plan = C.read_json(os.path.join(md, "PLAN.json"))
        seal = C.read_json(os.path.join(md, "SCELLE.json"))
        self.assertEqual(C.validate("plan", plan, strict=True), [])
        self.assertEqual(C.validate("seal", seal), [])
        self.assertEqual(seal["order_sha256"], plan["source_order_hash"])
        self.assertEqual(seal["plan_sha256"], C.plan_structure_sha(plan))
        self.assertEqual((seal["perimeter"], seal["color"]), (["site"], "vert"))
        types = [e["event_type"] for e in C.read_events(md)]
        self.assertIn("plan.compiled", types)
        self.assertIn("seal.written", types)
        self.assertIn("PLAN", out)

    def test_drift_flags_a_restructured_plan_not_progress(self):
        st = valid_state("demo-mission", status="framing")
        self.make_mission(state=st)
        self.assertEqual(self.run_script("mission.py", ["ready", "demo-mission", "--project", self.project])[0], 0)
        md = os.path.join(self.project, ".super-reprompt", "demo-mission")
        p = os.path.join(md, "PLAN.json")
        plan = C.read_json(p)
        plan["tasks"][0]["status"] = "running"
        C.atomic_write_json(p, plan)
        rc, out, err = self.run_script("guard.py", ["drift", "--project", self.project, "--slug", "demo-mission"])
        self.assertNotIn("PLAN_MODIFIE", out)
        plan["tasks"].append({"id": "T-X", "title": "en douce", "status": "ready", "deps": [], "covers": [], "files": ["*"],
                              "acceptance_criteria": ["x"], "preuve": "exit 0"})
        C.atomic_write_json(p, plan)
        rc, out, err = self.run_script("guard.py", ["drift", "--project", self.project, "--slug", "demo-mission"])
        self.assertIn("PLAN_MODIFIE", out)
        self.assertNotEqual(rc, 0)


class FrontierReadsCompiledStatuses(unittest.TestCase):
    def test_ready_and_unblocked_proposed_are_dispatchable(self):
        import econ
        plan = {"tasks": [{"id": "T1", "status": "ready", "deps": []}, {"id": "T2", "status": "proposed", "deps": ["T1"]},
                          {"id": "T3", "status": "proposed", "deps": []}, {"id": "T4", "status": "running", "deps": []},
                          {"id": "T5", "status": "todo", "deps": []}]}
        self.assertEqual([t["id"] for t in econ.frontier(plan)], ["T1", "T3", "T5"])
        plan["tasks"][0]["status"] = "done"
        self.assertEqual([t["id"] for t in econ.frontier(plan)], ["T2", "T3", "T5"])


class ManagerRunsStringProof(TmpCase):
    def test_shell_string_proof(self):
        import manager
        rc, out = manager._run("exit 3", self.project)
        self.assertEqual(rc, 3)
        rc, out = manager._run([sys.executable, "-c", "print(1)"], self.project)
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
