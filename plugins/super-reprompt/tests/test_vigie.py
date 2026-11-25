# -*- coding: utf-8 -*-
"""Lot 8 V3.1 : Vigie raccordee et graduee. `post` appele apres chaque execution, reponse info / avertissement / blocage,
budget gradue (80 / 100 / 150 %), un blocage ARRETE la tache et le dispatch, derogation explicite attribuee et journalisee,
fichier des derogations protege par le pare-feu."""
import json
import os
import subprocess
import sys
import unittest

from _t import SCRIPTS, TmpCase, valid_state

import contracts as C
import econ

GUARD = os.path.join(SCRIPTS, "guard.py")


class Vigie(TmpCase):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", self.project], check=True)
        os.makedirs(os.path.join(self.project, "site"))
        st = valid_state("demo-mission", status="framing", seal={"perimeter": ["site"], "budget": 10000},
                         tasks=[{"id": "T1", "covers": ["R1"], "files": ["site/*"], "mecanique": True, "preuve": "exit 0"},
                                {"id": "T2", "deps": ["T1"], "covers": ["C1"], "files": ["site/*"], "mecanique": True, "preuve": "exit 0"}])
        self.make_mission(state=st)
        self.assertEqual(self.run_script("mission.py", ["ready", "demo-mission", "--project", self.project])[0], 0)
        self.md = os.path.join(self.project, ".super-reprompt", "demo-mission")
        self.rep = os.path.join(self.tmp, "r.txt")
        with open(self.rep, "w", encoding="utf-8") as f:
            f.write("statut: OK\npreuve: x\nfichiers: site/\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")

    def guard(self, cmd):
        rc, out, err = self.run_script("guard.py", [cmd, "--project", self.project, "--slug", "demo-mission", "--json"])
        j = json.loads(out.strip().splitlines()[-1])
        return rc, j

    def mgr(self, *a):
        return self.run_script("manager.py", list(a) + ["--project", self.project, "--slug", "demo-mission"])

    def test_findings_are_graded(self):
        with open(os.path.join(self.project, "hors.txt"), "w") as f:
            f.write("x")
        rc, j = self.guard("post")
        g = {x["code"]: x["severite"] for x in j["graded"]}
        self.assertEqual(g.get("ECRITURE_HORS_PERIMETRE"), "blocage")
        self.assertTrue(j["bloquant"])
        self.assertIn("vigie.finding", [e["event_type"] for e in C.read_events(self.md)])

    def test_budget_is_graded(self):
        econ.spend(self.md, "P1", "session", 8500, label="actual", source="test")
        rc, j = self.guard("drift")
        g = {x["code"]: x["severite"] for x in j["graded"]}
        self.assertEqual(g.get("BUDGET_ALERTE"), "avertissement")
        self.assertFalse(j["bloquant"])
        econ.spend(self.md, "P1", "session", 7500, label="actual", source="test")
        rc, j = self.guard("drift")
        g = {x["code"]: x["severite"] for x in j["graded"]}
        self.assertEqual(g.get("BUDGET_ARRET"), "blocage")
        self.assertEqual(g.get("BUDGET_DEPASSE"), "avertissement")

    def test_block_stops_task_and_dispatch_until_derogation(self):
        self.assertEqual(self.mgr("next")[0], 0)
        with open(os.path.join(self.project, "hors.txt"), "w") as f:
            f.write("ecrit hors du perimetre")
        rc, out, err = self.mgr("done", "T1", "--report", self.rep, "--tokens", "100")
        self.assertEqual(rc, 5, out + err)
        self.assertIn("BLOCAGE", out)
        plan = C.read_json(os.path.join(self.md, "PLAN.json"))
        self.assertEqual(plan["tasks"][0]["status"], "blocked")
        rc, out, err = self.mgr("next")
        self.assertEqual(rc, 5, out + err)                              # nothing dispatched while it holds
        self.assertEqual(C.read_json(os.path.join(self.md, "PLAN.json"))["tasks"][1]["status"], "proposed")
        rc, out, err = self.run_script("guard.py", ["derogation", "--project", self.project, "--slug", "demo-mission",
                                                    "--code", "ECRITURE_HORS_PERIMETRE", "--by", "utilisateur", "--reason", "fichier de note voulu"])
        self.assertEqual(rc, 0, out + err)
        rc, out, err = self.mgr("next")
        self.assertEqual(rc, 0, out + err)
        rc, out, err = self.mgr("done", "T1", "--report", self.rep, "--tokens", "100")
        self.assertEqual(rc, 0, out + err)
        evs = C.read_events(self.md)
        d = [e for e in evs if e["event_type"] == "vigie.derogation"]
        self.assertEqual((len(d), d[0]["actor"], d[0]["payload"]["by"]), (1, "user", "utilisateur"))
        self.assertIn("vigie.block", [e["event_type"] for e in evs])

    def test_derogation_file_protected_from_tools(self):
        hook_in = json.dumps({"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.md, "derogations.json"), "content": "{}"},
                              "cwd": self.project})
        env = dict(self.env, TEMP=os.path.join(self.tmp, "t2"), TMP=os.path.join(self.tmp, "t2"), TMPDIR=os.path.join(self.tmp, "t2"))
        p = subprocess.run([sys.executable, GUARD], input=hook_in.encode("utf-8"), cwd=self.project, env=env, capture_output=True)
        self.assertEqual(p.returncode, 2, p.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
