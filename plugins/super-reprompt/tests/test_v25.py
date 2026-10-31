# -*- coding: utf-8 -*-
"""v2.5, one lever: a pass-through reply says nothing about the framing machinery."""
import os
import unittest

from _t import ROOT

SKILL = os.path.join(ROOT, "skills", "super-reprompt", "SKILL.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class SilentPassThrough(unittest.TestCase):
    """v2.4 answered H10 correctly but opened with "tier: none", which the frozen criterion fails."""

    def setUp(self):
        self.s = read(SKILL)
        i = self.s.index("## P0 — gate")
        self.gate = self.s[i:self.s.index("## P1 to P7 in brief")]

    def test_the_announcement_formula_is_gone(self):
        self.assertNotIn("No framing needed", self.s)

    def test_the_reply_must_read_as_if_the_skill_were_absent(self):
        self.assertIn("reads as if this skill were not installed", self.gate)

    def test_the_rule_is_positive_not_a_list_of_banned_words(self):
        # naming the machinery to forbid it is what made v2.4 say it; the sentence states what to do
        lever = self.gate[self.gate.index("do it or answer in at most 3 lines"):]
        lever = lever[:lever.index("Name any contradiction")]
        for primed in ("quick", "standard", "class", "pass-through"):
            self.assertNotIn(primed, lever.lower())

    def test_the_example_shows_a_bare_answer(self):
        i = self.s.index("## Canonical examples")
        example = self.s[i:i + 400]
        self.assertIn("I will make that rename now.", example)
        self.assertNotIn("framing needed", example)

    def test_the_two_never_pass_through_cases_survive_the_lever(self):
        self.assertIn("never pass-through", self.gate.lower())
        for needle in ("two independent dated sources", "restorable backup", "rehearsal"):
            self.assertIn(needle, self.s)


class HeldOutIsFrozen(unittest.TestCase):
    def test_the_new_case_set_is_in_the_repository(self):
        p = os.path.join(ROOT, "evals", "heldout-h13-h16.md")
        t = read(p)
        self.assertIn("Statut : **figé**", t)
        for case in ("H13", "H14", "H15", "H16"):
            self.assertIn(case, t)
        self.assertIn("2026-11-01", t)          # the run is dated, not open-ended

    def test_the_previous_set_is_kept_untouched(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "evals", "heldout-h7-h12.md")))


if __name__ == "__main__":
    unittest.main()
