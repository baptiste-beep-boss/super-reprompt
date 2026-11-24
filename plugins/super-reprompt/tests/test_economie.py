# -*- coding: utf-8 -*-
"""Lot 6 V3.1 : comptabilite etiquetee (actual / estimated / projected / unavailable), un seul budget (econ.ndjson ->
PROGRESS.json, budget mission du scelle, mission.py spent), decision de routage comparative tracee, rapport reproductible."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import SCRIPTS, TmpCase, valid_state

import contracts as C
import econ


class Ledger(unittest.TestCase):
    def setUp(self):
        self.m = tempfile.mkdtemp(prefix="sr-l6-")

    def tearDown(self):
        shutil.rmtree(self.m, ignore_errors=True)

    def test_labels_and_provenance(self):
        econ.spend(self.m, "P1", "specialiste", 1000, label="actual", source="compteur de l'agent", model="claude-sonnet-5-5")
        econ.spend(self.m, "P1", "session", 400, estimated=True)
        econ.spend(self.m, "P1", "relais", None, label="unavailable", source="fournisseur sans compteur")
        rows = econ.ledger(self.m)
        self.assertEqual([r["label"] for r in rows], ["actual", "estimated", "unavailable"])
        self.assertEqual(rows[0]["source"], "compteur de l'agent")
        self.assertIsNone(rows[2]["tokens"])
        with self.assertRaises(econ.EconError):
            econ.spend(self.m, "P1", "session", 10, label="devine")

    def test_legacy_rows_are_read_with_their_label(self):
        with open(os.path.join(self.m, "econ.ndjson"), "w", encoding="utf-8") as f:
            f.write('{"ts": 1, "phase": "P1", "poste": "session", "tokens": 50, "estime": true}\n')
            f.write('{"ts": 2, "phase": "P1", "poste": "session", "tokens": 70, "estime": false}\n')
        self.assertEqual([r["label"] for r in econ.ledger(self.m)], ["estimated", "actual"])

    def test_report_never_mixes_labels(self):
        C.atomic_write_json(os.path.join(self.m, "PLAN.json"), {"tasks": [{"id": "T1", "status": "done", "volume_tokens": 1000},
                                                                         {"id": "T2", "status": "ready", "volume_tokens": 5000}]})
        econ.spend(self.m, "P1", "specialiste", 1000, label="actual")
        econ.spend(self.m, "P1", "session", 400, estimated=True)
        plan = {"tasks": [{"id": "T1", "status": "done", "volume_tokens": 1000}, {"id": "T2", "status": "ready", "volume_tokens": 5000}]}
        r = econ.rapport(self.m, plan, {"budget": {"max_tokens": 10000}})
        self.assertEqual((r["actual"], r["estimated"], r["projected"]), (1000, 400, 5000))
        self.assertEqual(r["mission"]["consomme"], {"actual": 1000, "estimated": 400})
        self.assertIn("actual + estimated", r["mission"]["note"])
        self.assertEqual(r["mission"]["statut"], "ok")
        p = C.read_json(os.path.join(self.m, "PROGRESS.json"))
        self.assertEqual(p["tokens_used"], 1400)
        self.assertEqual(p["detail"], {"actual": 1000, "estimated": 400, "projected": 5000, "unavailable": 0})


class Routing(unittest.TestCase):
    def test_decision_compares_four_ways_with_confidence(self):
        d = econ.decide({"id": "T1", "volume_tokens": 90000, "type": "resume", "model": "sonnet"}, {"T1": "garde"})
        opts = {o["level"]: o for o in d["alternatives"]}
        self.assertEqual(set(opts), {"session", "specialiste", "sous-manager", "relais"})
        for o in opts.values():
            self.assertIn(o["label"], ("estimated",))
            self.assertTrue(o["confiance"])
            self.assertTrue(o["source"])
        self.assertFalse(opts["relais"]["possible"])
        self.assertEqual(d["level"], "specialiste")
        self.assertLess(opts["specialiste"]["tokens_contexte_principal"], opts["session"]["tokens_contexte_principal"])


class SingleBudget(TmpCase):
    def mdir(self):
        return os.path.join(self.project, ".super-reprompt", "demo-mission")

    def test_mission_spent_goes_to_the_single_ledger(self):
        self.make_mission()
        rc, out, err = self.run_script("mission.py", ["spent", "demo-mission", "12", "--project", self.project])
        self.assertEqual(rc, 0, out + err)
        rows = econ.ledger(self.mdir())
        self.assertEqual((rows[-1]["tokens"], rows[-1]["label"], rows[-1]["source"]), (12000, "estimated", "mission.py spent"))
        self.assertEqual(C.read_json(os.path.join(self.mdir(), "PROGRESS.json"))["tokens_used"], 12000)

    def test_mission_budget_of_the_seal_stops_next_and_feeds_the_watch(self):
        st = valid_state("demo-mission", status="framing", seal={"budget": 1000})
        self.make_mission(state=st)
        self.assertEqual(self.run_script("mission.py", ["ready", "demo-mission", "--project", self.project])[0], 0)
        econ.spend(self.mdir(), "P1", "session", 1600, label="actual", source="test")
        rc, out, err = self.run_script("manager.py", ["next", "--project", self.project, "--slug", "demo-mission"])
        self.assertEqual(rc, 3, out + err)
        self.assertIn("mission", out)
        rc, out, err = self.run_script("guard.py", ["drift", "--project", self.project, "--slug", "demo-mission"])
        self.assertIn("BUDGET_DEPASSE", out)

    def test_routing_decision_is_traced(self):
        st = valid_state("demo-mission", status="framing", tasks=[{"id": "T1", "covers": ["R1", "C1"], "preuve": "V1", "volume_tokens": 90000, "model": "sonnet"}])
        self.make_mission(state=st)
        self.assertEqual(self.run_script("mission.py", ["ready", "demo-mission", "--project", self.project])[0], 0)
        rc, out, err = self.run_script("manager.py", ["next", "--project", self.project, "--slug", "demo-mission"])
        self.assertEqual(rc, 0, out + err)
        evs = [e for e in C.read_events(self.mdir()) if e["event_type"] == "routing.decision"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(len(evs[0]["payload"]["alternatives"]), 4)
        self.assertEqual(evs[0]["payload"]["choix"], "specialiste")

    def test_report_cli_is_reproducible(self):
        self.make_mission()
        econ.spend(self.mdir(), "P1", "session", 300, label="actual", source="test")
        a = self.run_script("econ.py", ["rapport", self.mdir(), "--json"])
        b = self.run_script("econ.py", ["rapport", self.mdir(), "--json"])
        self.assertEqual(a[0], 0, a[1] + a[2])
        ja, jb = json.loads(a[1]), json.loads(b[1])
        ja.pop("genere_le", None), jb.pop("genere_le", None)
        self.assertEqual(ja, jb)
        self.assertEqual(ja["actual"], 300)


if __name__ == "__main__":
    unittest.main()
