# -*- coding: utf-8 -*-
"""Lot 7 V3.1 : memoire alimentee a la cloture (rangement deterministe des decisions, lecons et risques, dedupliques,
sans secret, dans le seul dossier du projet), brief de reprise compact relu a la reprise, etancheite entre projets,
mode degrade sans vault."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import SCRIPTS

import contracts as C
import memoire as MEM


class Memoire(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sr-l7-")
        self.proj = os.path.join(self.tmp, "proj")
        self.vault = os.path.join(self.tmp, "vault")
        self.md = os.path.join(self.proj, ".super-reprompt", "alpha")
        os.makedirs(self.md)
        os.makedirs(os.path.join(self.vault, "projets", "beta"))
        with open(os.path.join(self.vault, "projets", "beta", "beta-decisions.md"), "w", encoding="utf-8") as f:
            f.write("# beta\n- 2026-11-01 · CLIENT-BETA-CONFIDENTIEL tarif negocie\n")
        C.emit(self.md, "log.decision", "manager", {"kind": "decision", "text": "choisir SQLite plutot que Postgres"})
        C.emit(self.md, "log.lecon", "manager", {"kind": "lecon", "text": "toujours fixer la graine des tests"})
        C.emit(self.md, "log.decision", "manager", {"kind": "decision", "text": "choisir SQLite plutot que Postgres"})   # repeated
        C.emit(self.md, "log.decision", "manager", {"kind": "decision", "text": "cle sk-ant-api03-" + "A" * 40})
        r = C.make_receipt("T1", "T1-a1", "session", "ok", evidence=["e"], unresolved_risks=["migration non testee sous Linux"])
        C.save_receipt(self.md, r)
        C.atomic_write_json(os.path.join(self.md, "PLAN.json"), {"schema": 2, "slug": "alpha", "tasks": [
            {"id": "T1", "title": "base", "status": "done", "deps": [], "receipt": "T1-a1"},
            {"id": "T2", "title": "export", "status": "ready", "deps": ["T1"]}]})
        self.env = dict(os.environ, SR_VAULT_PATH=self.vault, SR_VAULT_DB=os.path.join(self.tmp, "i.sqlite"), PYTHONUTF8="1")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def notes(self, name):
        with open(os.path.join(self.vault, "projets", "alpha", "alpha-%s.md" % name), encoding="utf-8") as f:
            return f.read()

    def test_archive_ranges_dedups_and_refuses_secrets(self):
        rep = MEM.archive(self.md, "alpha", vault=self.vault)
        self.assertEqual((rep["decisions"], rep["lecons"], rep["risques"], rep["refuses"]), (1, 1, 1, 1))
        d = self.notes("decisions")
        self.assertEqual(d.count("choisir SQLite plutot que Postgres"), 1)
        self.assertNotIn("sk-ant", d)
        self.assertIn("toujours fixer la graine", self.notes("lecons"))
        self.assertIn("migration non testee", d + self.notes("lecons") + self.notes("journal"))
        rep2 = MEM.archive(self.md, "alpha", vault=self.vault)          # replay: nothing written twice
        self.assertEqual(rep2["decisions"] + rep2["lecons"] + rep2["risques"], 0)
        self.assertEqual(self.notes("decisions").count("choisir SQLite"), 1)
        self.assertIn("memory.archived", [e["event_type"] for e in C.read_events(self.md)])

    def test_writes_only_into_its_own_project(self):
        before = open(os.path.join(self.vault, "projets", "beta", "beta-decisions.md"), encoding="utf-8").read()
        MEM.archive(self.md, "alpha", vault=self.vault)
        MEM.reprise(self.md, "alpha", vault=self.vault)
        self.assertEqual(open(os.path.join(self.vault, "projets", "beta", "beta-decisions.md"), encoding="utf-8").read(), before)
        written = [os.path.relpath(os.path.join(dp, f), self.vault) for dp, _, fs in os.walk(self.vault) for f in fs]
        self.assertTrue(all(p.startswith(os.path.join("projets", "alpha")) or p.startswith(os.path.join("projets", "beta")) or
                            p.startswith("projets" + os.sep + "MOC") or p.endswith(".base") for p in written), written)

    def test_reprise_brief_is_compact_and_has_no_foreign_data(self):
        MEM.archive(self.md, "alpha", vault=self.vault)
        txt = MEM.reprise(self.md, "alpha", vault=self.vault)
        self.assertLess(len(txt) / 3.7, 1200)
        self.assertIn("T2", txt)                      # what remains
        self.assertIn("choisir SQLite", txt)          # decisions of this project
        self.assertIn("migration non testee", txt)    # open risks
        self.assertNotIn("CLIENT-BETA", txt)
        self.assertTrue(os.path.isfile(os.path.join(self.md, "REPRISE.md")))

    def test_degraded_mode_without_vault(self):
        rep = MEM.archive(self.md, "alpha", vault=None)
        self.assertEqual(rep["mode"], "local (aucun vault configure)")
        self.assertTrue(os.path.isfile(os.path.join(self.md, "memoire", "alpha-decisions.md")))

    def test_manager_status_reads_the_reprise_brief(self):
        MEM.reprise(self.md, "alpha", vault=self.vault)
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "manager.py"), "status", "--project", self.proj, "--slug", "alpha"],
                           capture_output=True, text=True, env=self.env, cwd=self.proj, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("REPRISE.md", p.stdout)
        self.assertIn("choisir SQLite", p.stdout)


if __name__ == "__main__":
    unittest.main()
