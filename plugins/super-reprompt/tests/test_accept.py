# -*- coding: utf-8 -*-
"""Lot L10 : dev/accept.py, the A1-A24 table. Rule under test: nothing is green without an execution."""
import importlib.util
import os
import unittest

from _t import ROOT


def load():
    spec = importlib.util.spec_from_file_location("accept", os.path.join(ROOT, "dev", "accept.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


A = load()


class Table(unittest.TestCase):
    def test_the_24_criteria_each_with_a_proof(self):
        ids = [c["id"] for c in A.CRITERIA]
        self.assertEqual(ids, ["A%d" % i for i in range(1, 25)])
        for c in A.CRITERIA:
            self.assertIn(c["kind"], ("suite", "tests", "cmd", "func", "none"), c["id"])
            self.assertTrue(c["preuve"], c["id"])
            if c["kind"] == "none":
                self.assertTrue(c.get("raison"), c["id"])

    def test_a24_is_never_launched_by_the_script(self):
        a24 = [c for c in A.CRITERIA if c["id"] == "A24"][0]
        self.assertEqual(a24["kind"], "none")
        self.assertIn("accord", a24["raison"])


class NoGreenWithoutExecution(unittest.TestCase):
    def results(self, **st):
        return {k.replace("__", "."): v for k, v in st.items()}

    def test_tests_criterion(self):
        c = {"id": "AX", "kind": "tests", "tests": ["test_relais.A13NoExfiltration"], "preuve": "x"}
        self.assertEqual(A.evaluate(c, {"test_relais.A13NoExfiltration.test_a13": "ok"}, run=None)["etat"], "vert")
        self.assertEqual(A.evaluate(c, {"test_relais.A13NoExfiltration.test_a13": "fail"}, run=None)["etat"], "rouge")
        # the suite did not run those tests: not measured, never green
        self.assertEqual(A.evaluate(c, {}, run=None)["etat"], "non mesure")
        self.assertEqual(A.evaluate(c, None, run=None)["etat"], "non mesure")

    def test_skipped_tests_do_not_count_as_green(self):
        c = {"id": "AX", "kind": "tests", "tests": ["test_x.K"], "preuve": "x"}
        self.assertEqual(A.evaluate(c, {"test_x.K.t1": "skip"}, run=None)["etat"], "non mesure")

    def test_cmd_criterion_uses_the_real_exit_code(self):
        c = {"id": "AX", "kind": "cmd", "cmd": ["x"], "preuve": "x"}
        self.assertEqual(A.evaluate(c, None, run=lambda cmd: (0, "ok"))["etat"], "vert")
        self.assertEqual(A.evaluate(c, None, run=lambda cmd: (1, "ko"))["etat"], "rouge")
        self.assertEqual(A.evaluate(c, None, run=lambda cmd: (127, "introuvable"))["etat"], "non mesure")

    def test_none_criterion_is_never_green(self):
        c = {"id": "AX", "kind": "none", "raison": "r", "preuve": "x"}
        self.assertEqual(A.evaluate(c, {"anything": "ok"}, run=lambda cmd: (0, ""))["etat"], "non mesure")

    def test_suite_criterion(self):
        c = {"id": "A1", "kind": "suite", "preuve": "x"}
        self.assertEqual(A.evaluate(c, {"a.b.c": "ok", "a.b.d": "ok"}, run=None)["etat"], "vert")
        r = A.evaluate(c, {"a.b.c": "ok", "a.b.d": "fail"}, run=None)
        self.assertEqual(r["etat"], "rouge")
        self.assertIn("a.b.d", r["detail"])

    def test_suite_runs_in_a_child_and_its_verbose_output_is_parsed(self):
        err = ("test_a (test_x.K.test_a) ... ok\n"
               "test_b (test_x.K.test_b) ... FAIL\n"
               "test_c (test_x.K.test_c) ... skipped 'Windows only'\n"
               "test_d (test_y.L.test_d) ... ERROR\n"
               "test_e (test_y.L.test_e)\nLong docstring line ... ok\n"
               "======\nFAIL: test_b (test_x.K.test_b)\n")
        self.assertEqual(A.parse_verbose(err), {"test_x.K.test_a": "ok", "test_x.K.test_b": "fail", "test_x.K.test_c": "skip",
                                                "test_y.L.test_d": "error", "test_y.L.test_e": "ok"})

    def test_a20_reads_the_bench_verdict_line(self):
        out = ("DIRECT interpreter floor (python.exe -I -S): median 223 ms\n"
               "hook inside a mission, 106-action mix:      median 231 ms  min 203\nA20 FAIL: median 231 ms (limit 120 ms)\n")
        self.assertEqual(A.f_a20(lambda c: (1, out))[0], "rouge")
        self.assertEqual(A.f_a20(lambda c: (0, out.replace("FAIL: median 231", "OK: median 90")))[0], "vert")
        self.assertEqual(A.f_a20(lambda c: (2, "Traceback"))[0], "non mesure")

    def test_a10_missing_index_is_not_measured(self):
        A.os.environ["SR_VAULT_DB"] = A.ROOT          # any existing path: the command decides
        try:
            self.assertEqual(A.f_a10(lambda c: (3, "index absent"))[0], "non mesure")
        finally:
            del A.os.environ["SR_VAULT_DB"]

    def test_render_has_one_row_per_criterion(self):
        rows = [{"id": "A%d" % i, "titre": "t", "etat": "vert", "detail": "d", "preuve": "p"} for i in range(1, 25)]
        out = A.render(rows)
        self.assertEqual(sum(1 for l in out.splitlines() if l.startswith("| A")), 24)
        self.assertIn("vert 24", out)


if __name__ == "__main__":
    unittest.main()
