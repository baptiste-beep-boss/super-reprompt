# -*- coding: utf-8 -*-
"""Tests for corrections 3 (escalation) and 4 (class DATA)."""
import unittest

from _t import TmpCase, valid_state


class Escalation(TmpCase):
    def validate(self, st):
        self.make_mission(state=st)
        return self.run_script("validate_order.py", ["demo-mission", "--project", self.project])

    def state(self, **esc):
        st = valid_state()
        e = {"enabled": True, "from": "low", "to": "medium", "max_relaunches": 1}
        e.update(esc)
        st["launch"]["escalation"] = e
        return st

    def test_valid_escalation(self):
        rc, out, err = self.validate(self.state())
        self.assertEqual(rc, 0, err)
        rc, out, err = self.validate(self.state(max_relaunches=2))
        self.assertEqual(rc, 0, err)

    def test_state_without_escalation_still_valid(self):
        rc, _o, err = self.validate(valid_state())
        self.assertEqual(rc, 0, err)

    def test_disabled_escalation_needs_no_command(self):
        st = self.state(enabled=False, max_relaunches=0)
        st["class"] = "DOCUMENT"
        st["verification"]["commands"] = []
        rc, _o, err = self.validate(st)
        self.assertEqual(rc, 0, err)

    def test_enabled_without_command_names_both_fields(self):
        st = self.state()
        st["class"] = "DOCUMENT"
        st["verification"]["commands"] = []
        rc, _o, err = self.validate(st)
        self.assertEqual(rc, 2)
        self.assertIn("launch.escalation.enabled", err)
        self.assertIn("verification.commands", err)

    def test_max_relaunches_out_of_range_lists_valid_values(self):
        for bad in (5, 0, -1, True, "2"):
            rc, _o, err = self.validate(self.state(max_relaunches=bad))
            self.assertEqual(rc, 2, bad)
            self.assertIn("max_relaunches", err)
            self.assertIn("1 or 2", err)

    def test_efforts_must_be_valid_and_increasing(self):
        rc, _o, err = self.validate(self.state(to="turbo"))
        self.assertEqual(rc, 2)
        self.assertIn("launch.escalation.to", err)
        self.assertIn("medium", err)
        rc, _o, err = self.validate(self.state(**{"from": "high", "to": "low"}))
        self.assertEqual(rc, 2)
        self.assertIn("higher effort", err)

    def test_malformed_escalation(self):
        st = valid_state()
        st["launch"]["escalation"] = "yes"
        rc, _o, err = self.validate(st)
        self.assertEqual(rc, 2)
        self.assertIn("launch.escalation", err)
        st["launch"]["escalation"] = {"enabled": "yes"}
        rc, _o, err = self.validate(st)
        self.assertEqual(rc, 2)
        self.assertIn("enabled", err)


class ClassData(TmpCase):
    def test_validate_accepts_data(self):
        st = valid_state(**{"class": "DATA"})
        self.make_mission(state=st)
        rc, out, err = self.run_script("validate_order.py", ["demo-mission", "--project", self.project])
        self.assertEqual(rc, 0, err)

    def test_data_mission_may_have_no_command(self):
        st = valid_state(**{"class": "DATA"})
        st["verification"]["commands"] = []
        self.make_mission(state=st)
        rc, _o, err = self.run_script("validate_order.py", ["demo-mission", "--project", self.project])
        self.assertEqual(rc, 0, err)

    def test_mission_init_data(self):
        rc, out, err = self.run_script("mission.py", ["--project", self.project, "init", "sheet-audit", "--class", "DATA",
                                                      "--tier", "quick", "--lang", "en"])
        self.assertEqual(rc, 0, err)
        st = self.read_state("sheet-audit")
        self.assertEqual(st["class"], "DATA")

    def test_unknown_class_lists_data_among_valid_values(self):
        rc, _o, err = self.run_script("mission.py", ["--project", self.project, "init", "x-1", "--class", "SPREADSHEET",
                                                     "--tier", "quick", "--lang", "en"])
        self.assertEqual(rc, 2)
        self.assertIn("DATA", err)
        for c in ("CODE", "DOCUMENT", "RESEARCH", "DECISION", "INFRA", "OTHER"):
            self.assertIn(c, err)
        st = valid_state(**{"class": "SPREADSHEET"})
        self.make_mission(state=st)
        rc, _o, err = self.run_script("validate_order.py", ["demo-mission", "--project", self.project])
        self.assertEqual(rc, 2)
        self.assertIn("DATA", err)


if __name__ == "__main__":
    unittest.main()
