# -*- coding: utf-8 -*-
"""Lot 9 V3.1 : la barre est une PROJECTION de PLAN.json + events.ndjson (BAR.json), plus une liste separee.
Avancement pondere par le travail, sans progression artificielle ; ETA a partir des durees observees, en fourchette,
avec niveau de confiance ; temps actif (les pauses sont exclues selon une regle explicite) ; precision honnete ;
mise a jour par manager next / done ; le mod lit BAR.json."""
import os
import shutil
import tempfile
import unittest

from _t import ROOT

import contracts as C
import progress as P


def ts(minute):
    return "2026-11-25T10:%02d:00Z" % minute if minute < 60 else "2026-11-25T%02d:%02d:00Z" % (10 + minute // 60, minute % 60)


class Projection(unittest.TestCase):
    def setUp(self):
        self.m = tempfile.mkdtemp(prefix="sr-l9-")

    def tearDown(self):
        shutil.rmtree(self.m, ignore_errors=True)

    def plan(self, tasks):
        C.atomic_write_json(os.path.join(self.m, "PLAN.json"), {"schema": 2, "slug": "demo", "tasks": tasks})

    def ev(self, et, task, minute):
        C.emit(self.m, et, "manager", {"task": task, "run_id": task + "-a1"}, mission_id="demo", timestamp=ts(minute))

    def test_weighted_progress_counts_only_validated_work(self):
        self.plan([{"id": "T1", "status": "done", "estimated_duration": 30}, {"id": "T2", "status": "review", "estimated_duration": 60},
                   {"id": "T3", "status": "running", "estimated_duration": 10}])
        b = P.projection(self.m)
        self.assertEqual((b["done"], b["total"]), (1, 3))
        self.assertEqual(b["percent_tasks"], 33)
        self.assertEqual(b["percent_work"], 30)                 # 30 / 100 : review and running count for nothing
        self.assertEqual(b["display"]["percent"], 30)

    def test_eta_from_observed_durations_with_confidence(self):
        self.plan([{"id": "T%d" % i, "status": "done", "estimated_duration": 10} for i in range(1, 4)] +
                  [{"id": "T4", "status": "ready", "estimated_duration": 10}, {"id": "T5", "status": "proposed", "estimated_duration": 10}])
        for i, (a, b) in enumerate(((0, 20), (20, 40), (40, 60)), start=1):    # observed: each 10-min task took 20 min
            self.ev("task.dispatched", "T%d" % i, a)
            self.ev("task.done", "T%d" % i, b)
        e = P.projection(self.m)["eta"]
        self.assertEqual(e["observed_tasks"], 3)
        self.assertEqual(e["confidence"], "moyenne")
        self.assertAlmostEqual(e["ratio_median"], 2.0)
        self.assertLessEqual(e["remaining_min_low"], 40)
        self.assertGreaterEqual(e["remaining_min_high"], 40)
        self.assertIn("observ", e["basis"])

    def test_without_history_the_range_is_wide_and_says_so(self):
        self.plan([{"id": "T1", "status": "ready", "estimated_duration": 20}])
        e = P.projection(self.m)["eta"]
        self.assertEqual(e["confidence"], "faible (n = 0)")
        self.assertLess(e["remaining_min_low"], e["remaining_min_high"])
        self.assertNotIn(":", P.projection(self.m)["display"]["text"])   # never minute precision without data

    def test_idle_gaps_are_excluded_from_active_time(self):
        self.plan([{"id": "T1", "status": "done", "estimated_duration": 10}, {"id": "T2", "status": "ready", "estimated_duration": 10}])
        self.ev("task.dispatched", "T1", 0)
        C.emit(self.m, "log.note", "manager", {"text": "x"}, mission_id="demo", timestamp=ts(5))
        self.ev("task.done", "T1", 300)                                     # 4 h 55 later: a pause, not work
        b = P.projection(self.m)
        self.assertLessEqual(b["elapsed_active_min"], P.IDLE_GAP_MIN + 5)
        self.assertIn("pause", b["eta"]["rule_idle"])

    def test_bar_json_written_and_manager_refreshes_it(self):
        self.plan([{"id": "T1", "status": "ready", "deps": [], "estimated_duration": 5, "mecanique": True, "preuve": "exit 0"}])
        P.write(self.m)
        self.assertEqual(C.read_json(os.path.join(self.m, "BAR.json"))["source"], "PLAN.json + events.ndjson")

    def test_mod_reads_the_projection_not_a_separate_list(self):
        with open(os.path.join(ROOT, "hooks", "bar", "register.tsx"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("BAR.json", src)
        self.assertIn("$.fs.read", src)


if __name__ == "__main__":
    unittest.main()
