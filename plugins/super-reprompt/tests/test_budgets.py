# -*- coding: utf-8 -*-
"""Size and content constraints of the instruction files (correction 1 and permanent constraints)."""
import os
import re
import subprocess
import sys
import unittest

from _t import ROOT

REFS = os.path.join(ROOT, "skills", "super-reprompt", "references")
SKILL = os.path.join(ROOT, "skills", "super-reprompt", "SKILL.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class Budgets(unittest.TestCase):
    def test_measure_script_check_passes(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "dev", "measure_loading.py"), "--check"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout.decode() + p.stderr.decode())

    def test_sizes(self):
        self.assertLessEqual(len(read(SKILL)) / 3.7, 4500)
        self.assertLessEqual(len(read(os.path.join(REFS, "quick.md"))) / 3.7, 1900)

    def test_quick_is_self_contained(self):
        q = read(os.path.join(REFS, "quick.md"))
        for name in ("phases.md", "interview.md", "order-template.md", "verification.md", "launch.md", "models.md",
                     "agents.md", "capabilities.md"):
            self.assertNotIn(name, q)
        for needle in ("mission.py", "validate_order.py", "launch.py", "AskUserQuestion", "--dry-run"):
            self.assertIn(needle, q)

    def test_skill_points_quick_to_quick_md(self):
        s = read(SKILL)
        self.assertIn("references/quick.md", s)
        self.assertIn("Read each reference once", s)

    def test_every_reference_has_sections_by_tier(self):
        for f in os.listdir(REFS):
            if f.endswith(".md") and f != "quick.md":
                self.assertRegex(read(os.path.join(REFS, f)), r"(?m)^Sections by tier — standard: ", f)

    def test_contents_line_matches_headings(self):
        for f in os.listdir(REFS):
            if not f.endswith(".md") or f == "quick.md":
                continue
            t = read(os.path.join(REFS, f))
            toc = re.search(r"(?m)^Contents: (.*)$", t)
            if not toc:
                continue
            names = re.findall(r"\[([^\]]+)\]\(#", toc.group(1))
            body = re.sub(r"```.*?```", "", t, flags=re.S)
            heads = [h.strip() for h in re.findall(r"(?m)^## (.+)$", body)]
            if f == "order-template.md":
                heads = [h for h in heads if not re.match(r"\d+\.", h)]
            self.assertEqual(names, heads, f)


class TextConstraints(unittest.TestCase):
    def files(self):
        out = [SKILL]
        for base in (REFS, os.path.join(ROOT, "agents")):
            for dp, _d, fs in os.walk(base):
                out += [os.path.join(dp, x) for x in fs if x.endswith(".md")]
        return out

    def test_no_think_hard(self):
        # personal data is covered by test_scan_launch_plugin
        bad = re.compile("think" + r"\s+" + "hard", re.I)
        for p in self.files():
            self.assertIsNone(bad.search(read(p)), p)

    def test_at_most_two_uppercase_lines(self):
        n = 0
        for p in self.files():
            t = re.sub(r"```.*?```", "", read(p), flags=re.S)
            for line in t.split("\n"):
                letters = [c for c in line if c.isalpha()]
                if len(letters) >= 12 and all(c.isupper() for c in letters):
                    n += 1
        self.assertLessEqual(n, 2)


if __name__ == "__main__":
    unittest.main()
