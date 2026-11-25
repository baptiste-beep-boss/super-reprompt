# -*- coding: utf-8 -*-
"""V3.1 lot 9 (trouve par `claude plugin validate`) : l'en-tete YAML de chaque fiche d'agent doit se lire. Une valeur non
citee qui contient « : » casse le YAML, et Claude Code charge alors l'agent SANS ses champs (model, tools, maxTurns) :
l'archiviste ne tournait plus sous Haiku. Bibliotheque standard : regle stricte sur les valeurs simples."""
import glob
import os
import unittest

from _t import ROOT


class AgentFrontmatter(unittest.TestCase):
    def test_every_value_that_needs_quotes_has_them(self):
        bad = []
        for p in sorted(glob.glob(os.path.join(ROOT, "agents", "*.md"))):
            with open(p, encoding="utf-8") as f:
                txt = f.read()
            self.assertTrue(txt.startswith("---\n"), p)
            head = txt.split("---", 2)[1]
            for ln in head.strip().splitlines():
                k, sep, v = ln.partition(":")
                v = v.strip()
                self.assertTrue(sep and k.strip(), "%s : ligne illisible %r" % (os.path.basename(p), ln))
                quoted = len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'"
                if not quoted and (": " in v or " #" in v or v[:1] in "[{&*!|>%@`\"'"):
                    bad.append("%s %s" % (os.path.basename(p), k.strip()))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
