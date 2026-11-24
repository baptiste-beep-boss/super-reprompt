# -*- coding: utf-8 -*-
"""A12 (lot L6): the 18 task types of net/tasks.json, each verifier tested BOTH WAYS:
it accepts a good output and rejects a bad one. Standard library only, no network."""
import json
import os
import shutil
import sys
import tempfile
import unittest

from _t import ROOT

sys.path.insert(0, os.path.join(ROOT, "net"))
import verify  # noqa: E402

from bench import cases  # noqa: E402  (frozen bench set, shared with relais bench)

PY = sys.executable


def J(o):
    return json.dumps(o, ensure_ascii=False)


class A12Verifiers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tempfile.mkdtemp(prefix="sr-relais-")
        cls.cases = cases(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def test_tasks_json_declares_18_types_each_with_its_verifier(self):
        with open(os.path.join(ROOT, "net", "tasks.json"), encoding="utf-8") as f:
            t = json.load(f)
        types = t["types"]
        self.assertEqual(len(types), 18)
        self.assertEqual(sorted(types), sorted(c[0] for c in self.cases))
        for k, v in types.items():
            self.assertIn(v["verifier"], verify.VERIFIERS, k)
            self.assertTrue(v["prompt"] and v["label"], k)
        self.assertGreaterEqual(len(t["never"]), 10)

    def test_each_verifier_accepts_the_good_output(self):
        for typ, src, good, _bad, spec in self.cases:
            with self.subTest(typ=typ):
                ok, detail = verify.check(typ, src, good, spec)
                self.assertTrue(ok, "%s rejected the good output: %s" % (typ, detail))

    def test_each_verifier_rejects_the_bad_output(self):
        for typ, src, _good, bad, spec in self.cases:
            with self.subTest(typ=typ):
                ok, detail = verify.check(typ, src, bad, spec)
                self.assertFalse(ok, "%s accepted the bad output" % typ)
                self.assertTrue(detail)

    def test_empty_output_always_fails(self):
        for typ, src, _g, _b, spec in self.cases:
            with self.subTest(typ=typ):
                self.assertFalse(verify.check(typ, src, "", spec)[0])

    def test_sql_kind_is_read_only(self):
        spec = {"kind": "sql", "setup": "create table t(a int); insert into t values (1),(2);", "expected": [[2]]}
        self.assertTrue(verify.check("regex_sql_script", "", "select count(*) from t", spec)[0])
        self.assertFalse(verify.check("regex_sql_script", "", "delete from t", spec)[0])
        self.assertFalse(verify.check("regex_sql_script", "", "select 1", spec)[0])

    def test_script_kind_runs_isolated_and_compares_stdout(self):
        spec = {"kind": "script", "stdin": "3\n", "stdout": "6\n"}
        self.assertTrue(verify.check("regex_sql_script", "", "print(int(input())*2)", spec)[0])
        self.assertFalse(verify.check("regex_sql_script", "", "print(7)", spec)[0])

    def test_double_pass_on_classification(self):
        items = ["i%d" % i for i in range(30)]
        sample = verify.double_pass_sample(items)
        self.assertEqual(len(sample), 3)              # 10 %
        self.assertEqual(sample, verify.double_pass_sample(items))   # deterministic
        self.assertTrue(verify.double_pass_agree({"a": "bug"}, {"a": "bug"}))
        self.assertFalse(verify.double_pass_agree({"a": "bug"}, {"a": "feature"}))

    def test_build_command_must_come_from_the_log(self):
        out = J({"command": [PY, "-c", "import os"], "error_line": "x", "explanation": "y"})
        ok, d = verify.check("erreur_build", "", out, {"allowed_commands": []})
        self.assertFalse(ok)
        self.assertIn("non autoris", d)


if __name__ == "__main__":
    unittest.main()
