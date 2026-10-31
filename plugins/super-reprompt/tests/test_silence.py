# -*- coding: utf-8 -*-
"""check_silence.py: the negative-control criterion, checked by a script instead of a judge.

Two blind judges applied the same binary criterion in opposite ways on H13 and H14 (2026-10-30).
A binary criterion belongs in a script: same reading for every output, for free.
"""
import os
import subprocess
import sys
import unittest

from _t import ROOT

CHECK = os.path.join(ROOT, "dev", "check_silence.py")


def run(text, args=()):
    p = subprocess.run([sys.executable, CHECK] + list(args), input=text.encode("utf-8"),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


class Silent(unittest.TestCase):
    def test_a_bare_answer_passes(self):
        code, out, err = run("Je fais ce remplacement maintenant.\nJ'ajoute l'import `timezone` s'il manque.\n")
        self.assertEqual(code, 0, out + err)
        self.assertIn("silent", out.lower())

    def test_an_answer_about_an_index_passes(self):
        code, out, _e = run("Parce que le planificateur compare les couts : un index peu selectif coute plus "
                            "cher qu'un Seq Scan.\n")
        self.assertEqual(code, 0, out)


class NotSilent(unittest.TestCase):
    def test_the_word_framing_in_french_fails(self):
        code, out, _e = run("Pas besoin de cadrage : je remplace la ligne 14.\n")
        self.assertEqual(code, 1)
        self.assertIn("cadrage", out)

    def test_the_other_french_formula_fails(self):
        code, out, _e = run("Aucun cadrage necessaire : je remplace la ligne 14.\n")
        self.assertEqual(code, 1)

    def test_an_announced_tier_fails(self):
        code, out, _e = run("Palier retenu : aucun. Je remplace la ligne 14.\n")
        self.assertEqual(code, 1)
        self.assertIn("palier", out)

    def test_the_english_words_fail(self):
        for text in ("No framing needed: I will do it.", "This is a pass-through, I will do it.",
                     "No framing required here."):
            code, out, _e = run(text)
            self.assertEqual(code, 1, text)

    def test_a_token_cost_announcement_fails(self):
        code, out, _e = run("Cadre: environ 8 k tokens. Je remplace la ligne 14.\n")
        self.assertEqual(code, 1)

    def test_the_skill_name_fails(self):
        code, out, _e = run("super-reprompt ne s'applique pas ici, je remplace la ligne 14.\n")
        self.assertEqual(code, 1)

    def test_a_mission_order_mention_fails(self):
        code, out, _e = run("Je n'ecris pas d'ordre de mission pour ca, je remplace la ligne 14.\n")
        self.assertEqual(code, 1)

    def test_accents_and_case_do_not_hide_a_hit(self):
        # upper case, and an accent inside the word (cadrage written cadr<A-circumflex>ge)
        code, out, _e = run("PAS BESOIN DE CADRÂGE : je remplace.\n")
        self.assertEqual(code, 1, out)
        code, out, _e = run("Pas besoin de CADRAGE : je remplace.\n")
        self.assertEqual(code, 1, out)

    def test_every_hit_is_named_with_its_line(self):
        code, out, _e = run("ligne une\nPas besoin de cadrage ici\nligne trois\n")
        self.assertEqual(code, 1)
        self.assertIn("2", out)          # the line number, so a human can check the call


class NoFalsePositives(unittest.TestCase):
    """A criterion that fires on an innocent word is worse than no criterion."""

    def test_words_that_merely_contain_a_banned_substring_pass(self):
        for text in ("Il faut un entier, pas un flottant.", "La permission d'ecrire manque.",
                     "C'est un recadrage de l'image.", "Le cadre de la photo est casse.",
                     "La bibliotheque standard suffit.", "Le classeur est ouvert."):
            code, out, _e = run(text)
            self.assertEqual(code, 0, "%s -> %s" % (text, out))

    def test_a_technical_answer_mentioning_a_quick_sort_passes(self):
        code, out, _e = run("Un quicksort suffit ici.\n")
        self.assertEqual(code, 0, out)


class LengthIsAlsoMechanical(unittest.TestCase):
    def test_too_many_lines_fails_when_a_cap_is_given(self):
        code, out, _e = run("une\ndeux\ntrois\nquatre\n", ["--max-lines", "3"])
        self.assertEqual(code, 1)
        self.assertIn("lines", out.lower())

    def test_blank_lines_do_not_count_against_the_cap(self):
        code, out, _e = run("une\n\ndeux\n\ntrois\n", ["--max-lines", "3"])
        self.assertEqual(code, 0, out)

    def test_without_a_cap_length_is_not_judged(self):
        code, out, _e = run("une\ndeux\ntrois\nquatre\ncinq\n")
        self.assertEqual(code, 0, out)


class Usage(unittest.TestCase):
    def test_a_file_argument_works_like_stdin(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="sr-sil-")
        p = os.path.join(d, "out.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write("Pas besoin de cadrage.\n")
        pr = subprocess.run([sys.executable, CHECK, p], stdout=subprocess.PIPE, timeout=30)
        self.assertEqual(pr.returncode, 1)

    def test_a_missing_file_is_a_usage_error(self):
        pr = subprocess.run([sys.executable, CHECK, os.path.join(ROOT, "nope-h17.txt")],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(pr.returncode, 2)

    def test_the_pattern_list_is_printable_so_a_case_can_quote_it(self):
        pr = subprocess.run([sys.executable, CHECK, "--list"], stdout=subprocess.PIPE, timeout=30)
        self.assertEqual(pr.returncode, 0)
        out = pr.stdout.decode("utf-8", "replace")
        for needle in ("cadrage", "palier", "pass-through", "framing"):
            self.assertIn(needle, out)


if __name__ == "__main__":
    unittest.main()
