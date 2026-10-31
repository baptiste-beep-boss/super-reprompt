# -*- coding: utf-8 -*-
"""v2.4: the two never-pass-through cases, the research agent, and an honest loading budget."""
import os
import subprocess
import sys
import unittest

import scan_capabilities as SC
from _t import ROOT

REFS = os.path.join(ROOT, "skills", "super-reprompt", "references")
SKILL = os.path.join(ROOT, "skills", "super-reprompt", "SKILL.md")


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


class NeverPassThrough(unittest.TestCase):
    """H6 (sourced research) and H3 (writing over shared or production data) were routed to pass-through in v2.3."""

    def setUp(self):
        self.s = read(SKILL)

    def test_the_rule_is_in_the_gate(self):
        i = self.s.index("## P0 — gate")
        j = self.s.index("## P1 to P7 in brief")
        self.assertIn("never pass-through", self.s[i:j].lower())

    def test_sourced_research_needs_dated_independent_sources(self):
        self.assertIn("two independent dated sources", self.s)
        self.assertIn("when sources disagree", self.s)

    def test_destructive_shared_or_production_write_needs_a_way_back(self):
        for needle in ("restorable backup", "rehearsal", "explicit yes"):
            self.assertIn(needle, self.s)

    def test_the_exception_is_bounded_so_local_edits_stay_pass_through(self):
        self.assertIn("a local file or a scratch copy is not that", self.s.lower())

    def test_the_exception_names_a_tier_instead_of_blocking(self):
        i = self.s.index("never pass-through")
        self.assertIn("quick", self.s[i - 200:i + 200])


class ResearchAgent(unittest.TestCase):
    def test_the_agent_is_declared_read_mostly_and_bounded(self):
        fm = SC.parse_frontmatter(read(os.path.join(ROOT, "agents", "reprompt-researcher.md")))
        self.assertEqual(fm["name"], "reprompt-researcher")
        self.assertEqual(fm["tools"], "Read, Glob, Grep, WebSearch, WebFetch, Write")
        self.assertNotIn("Bash", fm["tools"])          # no arbitrary command from a sub-agent
        self.assertEqual(fm["model"], "sonnet")
        self.assertEqual(fm["maxTurns"], "60")
        self.assertEqual(fm["omitClaudeMd"], "true")
        for banned in ("permissionMode", "hooks", "mcpServers", "initialPrompt"):
            self.assertNotIn(banned, fm)

    def test_the_agent_refuses_walled_and_private_access(self):
        t = read(os.path.join(ROOT, "agents", "reprompt-researcher.md")).lower()
        for needle in ("paywall", "captcha", "cookie", "data", "url and a date"):
            self.assertIn(needle, t)

    def test_the_agent_may_not_disguise_who_is_asking(self):
        # the first real run tried a forged user agent to fetch a blocked PDF; the rule was missing
        for p in (os.path.join(ROOT, "agents", "reprompt-researcher.md"), os.path.join(REFS, "research.md")):
            t = read(p).lower()
            self.assertIn("forged user agent", t)
            self.assertIn("403", t)

    def test_the_agent_inventories_the_existing_notes_first(self):
        t = read(os.path.join(ROOT, "agents", "reprompt-researcher.md"))
        self.assertIn("Inventory what exists first", t)
        self.assertLess(t.index("Inventory what exists first"), t.index("Search wide before deep"))

    def test_the_report_is_capped(self):
        t = read(os.path.join(ROOT, "agents", "reprompt-researcher.md"))
        self.assertIn("2000 tokens", t)

    def test_the_skill_offers_it_in_p2_with_no_as_the_default(self):
        s = read(SKILL)
        i = s.index("- **P2.**")
        j = s.index("- **P3.**")
        self.assertIn("research agent", s[i:j])
        self.assertIn("default no", s[i:j])
        self.assertIn("references/research.md", s[i:j])

    def test_the_reference_names_the_validator_and_the_caps(self):
        t = read(os.path.join(REFS, "research.md"))
        self.assertIn("validate_library.py", t)
        self.assertIn("--max-files 40", t)
        self.assertIn("link-only", t)
        self.assertIn("file,url,date,sha256,licence,vault_note", t)

    def test_the_toolbox_asks_for_no_account_and_no_key(self):
        t = read(os.path.join(REFS, "research.md"))
        i = t.index("## Free toolbox")
        j = t.index("## Public access rules")
        toolbox = t[i:j].lower()
        self.assertIn("need no account", toolbox)
        for banned in ("api key", "api_key", "token", "subscription", "sign in", "log in"):
            self.assertNotIn(banned, toolbox)        # no tool in the table may require one
        rules = t[j:].lower()
        for needle in ("no account", "no key", "no login", "no paid api", "paywall", "captcha"):
            self.assertIn(needle, rules)             # the prohibitions are stated, not implied


class LoadingBudgetIsHonest(unittest.TestCase):
    def test_research_is_reported_outside_the_standard_total(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "dev", "measure_loading.py")],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr.decode())
        out = p.stdout.decode()
        self.assertIn("standard+research", out)
        doc = read(os.path.join(ROOT, "dev", "CHARGEMENT-PAR-PALIER.md"))
        self.assertIn("research.md", doc)
        self.assertIn("outside the standard total", doc)
        self.assertIn("standard + research agent offered", doc)

    def test_the_conditional_load_is_small_enough_to_be_worth_a_question(self):
        doc = read(os.path.join(ROOT, "dev", "CHARGEMENT-PAR-PALIER.md"))
        self.assertIn("| `research.md`", doc)


if __name__ == "__main__":
    unittest.main()
