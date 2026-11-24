# -*- coding: utf-8 -*-
"""Lot 3 V3.1 : orchestration. Plan valide au chargement, statut running, done idempotent avec recu, retry borne,
Vigie aux jalons, archiviste en fin de phase, synthese a la cloture, plan du Relais produit et transmis
automatiquement, reprise apres crash sans doublon, `status` qui explique ce qui reste."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import SCRIPTS

import contracts as C

OKP = [sys.executable, "-c", "import sys; sys.exit(0)"]
KOP = [sys.executable, "-c", "import sys; sys.exit(1)"]


def task(tid, **kw):
    t = {"id": tid, "title": tid, "status": "ready" if not kw.get("deps") else "proposed", "deps": [], "covers": [], "files": [],
         "acceptance_criteria": ["code 0"], "preuve": OKP, "mecanique": True, "phase": "P1"}
    t.update(kw)
    return t


class Orchestration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sr-l3-")
        self.mdir = os.path.join(self.tmp, ".super-reprompt", "pilote")
        os.makedirs(self.mdir)
        self.env = dict(os.environ, SR_VAULT_PATH="", CLAUDE_PLUGIN_OPTION_VAULT_PATH="", PYTHONIOENCODING="utf-8")
        self.env.pop("SR_TEST_CRASH_AT", None)
        self.rep = os.path.join(self.tmp, "r.txt")
        with open(self.rep, "w", encoding="utf-8") as f:
            f.write("statut: OK\npreuve: commande\nfichiers: a.py\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, tasks, **extra):
        plan = {"schema": 2, "slug": "pilote", "phases": {"P1": {"budget_tokens": 10 ** 6}, "P2": {"budget_tokens": 10 ** 6}}, "tasks": tasks}
        plan.update(extra)
        C.atomic_write_json(os.path.join(self.mdir, "PLAN.json"), plan)

    def plan(self):
        return C.read_json(os.path.join(self.mdir, "PLAN.json"))

    def st(self):
        return {t["id"]: t["status"] for t in self.plan()["tasks"]}

    def mgr(self, *a, env=None):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "manager.py")] + list(a) + ["--project", self.tmp, "--slug", "pilote"],
                           capture_output=True, text=True, env=env or self.env, cwd=self.tmp, timeout=120)
        return p.returncode, p.stdout + p.stderr

    def types(self):
        return [e["event_type"] for e in C.read_events(self.mdir)]

    # ---------------------------------------------------------------- plan
    def test_invalid_plan_refused_at_load(self):
        self.write([task("T1", deps=["T2"]), task("T2", deps=["T1"])])
        rc, out = self.mgr("next")
        self.assertEqual(rc, 2)
        self.assertIn("cycle", out)

    def test_next_marks_dispatched_tasks_running_once(self):
        self.write([task("T1"), task("T2", deps=["T1"])])
        rc, out = self.mgr("next")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.st(), {"T1": "running", "T2": "proposed"})
        rc, out = self.mgr("next")
        self.assertIn("en cours", out)
        self.assertEqual(self.types().count("task.dispatched"), 1)

    # ---------------------------------------------------------------- done
    def test_done_writes_receipt_and_is_idempotent(self):
        self.write([task("T1"), task("T2", deps=["T1"])])
        self.mgr("next")
        rc, out = self.mgr("done", "T1", "--report", self.rep, "--tokens", "500")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.st()["T1"], "done")
        r = C.read_json(os.path.join(self.mdir, "receipts", "T1", "T1-a1.json"))
        self.assertEqual((r["status"], C.validate("receipt", r)), ("ok", []))
        rc, out = self.mgr("done", "T1", "--report", self.rep, "--tokens", "500")
        self.assertEqual(rc, 0, out)
        self.assertIn("deja", out)
        with open(os.path.join(self.mdir, "econ.ndjson"), encoding="utf-8") as f:
            self.assertEqual(len([l for l in f if l.strip()]), 1)
        self.assertEqual(self.types().count("task.done"), 1)

    def test_crash_after_receipt_then_resume_without_duplicates(self):
        self.write([task("T1"), task("T2", deps=["T1"])])
        self.mgr("next")
        rc, out = self.mgr("done", "T1", "--report", self.rep, "--tokens", "700", env=dict(self.env, SR_TEST_CRASH_AT="after_receipt"))
        self.assertEqual(rc, 9, out)                                   # simulated crash: receipt on disk, plan not saved
        self.assertEqual(self.st()["T1"], "running")
        rc, out = self.mgr("status")
        self.assertIn("T1", out)
        rc, out = self.mgr("done", "T1", "--report", self.rep, "--tokens", "700")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.st()["T1"], "done")
        with open(os.path.join(self.mdir, "econ.ndjson"), encoding="utf-8") as f:
            self.assertEqual(len([l for l in f if l.strip()]), 1)
        self.assertEqual(self.types().count("task.done"), 1)

    def test_failure_retry_is_bounded(self):
        self.write([task("T1", preuve=KOP)])
        self.mgr("next")
        rc, out = self.mgr("done", "T1", "--report", self.rep)
        self.assertEqual(rc, 1)
        self.assertEqual(self.st()["T1"], "failed")
        rc, out = self.mgr("next")                                     # attempt 2
        self.assertIn("nouvelle tentative", out)
        self.assertEqual(self.plan()["tasks"][0]["attempt"], 2)
        self.assertEqual(self.st()["T1"], "running")
        self.mgr("done", "T1", "--report", self.rep)
        rc, out = self.mgr("next")                                     # budget of attempts spent: blocked, question
        self.assertEqual(self.st()["T1"], "blocked")
        self.assertIn("QUESTION", out)
        self.assertTrue(os.path.isfile(os.path.join(self.mdir, "receipts", "T1", "T1-a2.json")))

    # ---------------------------------------------------------------- Vigie, memory
    def test_milestones_archivist_and_synthesis(self):
        self.write([task("T1"), task("T2"), task("T3", phase="P2"), task("T4", phase="P2")])
        outs = []
        for tid in ("T1", "T2", "T3", "T4"):
            self.mgr("next")
            rc, out = self.mgr("done", tid, "--report", self.rep, "--tokens", "100")
            self.assertEqual(rc, 0, out)
            outs.append(out)
        ty = self.types()
        self.assertEqual(sorted(e["payload"]["milestone"] for e in C.read_events(self.mdir) if e["event_type"] == "vigie.milestone"), [25, 50, 75, 100])
        self.assertIn("JALON 50", outs[1])
        self.assertEqual(ty.count("memory.archive_requested"), 2)        # once per finished phase, grouped
        self.assertEqual(ty.count("memory.synthesis_requested"), 1)
        self.assertIn("sr-archiviste", outs[1])
        self.assertIn("sr-synthese", outs[3])
        b = os.path.join(self.mdir, "briefs", "ARCHIVISTE-P1.md")
        with open(b, encoding="utf-8") as f:
            txt = f.read()
        self.assertIn("T1", txt)
        self.assertLess(len(txt) / 4, 3000)
        self.assertTrue(os.path.isfile(os.path.join(self.mdir, "briefs", "SYNTHESE.md")))
        # replaying done on a finished task does not re-request memory work
        self.mgr("done", "T4", "--report", self.rep, "--tokens", "100")
        self.assertEqual(self.types().count("memory.synthesis_requested"), 1)

    # ---------------------------------------------------------------- Relais
    def test_relais_plan_produced_and_passed_automatically(self):
        self.write([task("T1", mecanique=False, type="resume", volume_tokens=60000)])
        rc, out = self.mgr("next")
        self.assertEqual(rc, 0, out)
        rel = C.read_json(os.path.join(self.mdir, "relais.json"))
        self.assertIn(rel.get("T1"), ("delegue", "garde"))
        self.assertIn("relais.planned", self.types())
        self.assertIn("relais", out.lower())

    def test_status_explains_what_remains(self):
        self.write([task("T1"), task("T2", deps=["T1"])])
        rc, out = self.mgr("status")
        self.assertEqual(rc, 0)
        self.assertIn("0/2", out)
        self.assertIn("T1", out)


if __name__ == "__main__":
    unittest.main()
