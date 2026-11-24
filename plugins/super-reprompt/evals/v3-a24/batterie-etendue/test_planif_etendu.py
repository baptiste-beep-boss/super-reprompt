# -*- coding: utf-8 -*-
"""Batterie etendue A24 (v2 : noms de taches entiers, la v1 trouvait 'c' dans le mot 'cycle'), projet difficile. Ecrite et figee le 24/11/2026 AVANT tout essai de la methode testee.
Classe Spec : exigences de ENONCE.md. Classe Robustesse : performance, hors enonce strict (signalee a part)."""
import copy
import time
import unittest
from planif import planifier, CycleError


class Spec(unittest.TestCase):
    def test_egalite_alphabetique_et_plafond(self):
        self.assertEqual(planifier({"b": [], "a": [], "c": []}, 2), [["a", "b"], ["c"]])

    def test_vagues_triees(self):
        for v in planifier({"z": [], "y": [], "x": ["z"], "w": ["y"]}, 5):
            self.assertEqual(v, sorted(v))

    def test_chaque_tache_une_fois_apres_ses_dependances(self):
        t = {"a": [], "b": ["a"], "c": ["a"], "d": ["b", "c"], "e": [], "f": ["e", "d"]}
        vagues = planifier(t, 2)
        vu = {}
        for i, v in enumerate(vagues):
            self.assertLessEqual(len(v), 2)
            for x in v:
                self.assertNotIn(x, vu)
                vu[x] = i
        self.assertEqual(set(vu), set(t))
        for x, deps in t.items():
            for dep in deps:
                self.assertLess(vu[dep], vu[x])

    def test_cycle_non_simple_cite_toutes_ses_taches(self):
        with self.assertRaises(CycleError) as cm:
            planifier({"alpha": ["beta"], "beta": ["alpha", "gamma"], "gamma": ["beta"]}, 3)
        for n in ("alpha", "beta", "gamma"):
            self.assertIn(n, str(cm.exception))

    def test_auto_boucle(self):
        with self.assertRaises(CycleError) as cm:
            planifier({"solo": ["solo"], "libre": []}, 1)
        self.assertIn("solo", str(cm.exception))

    def test_cycle_avec_amont_et_aval(self):
        with self.assertRaises(CycleError) as cm:
            planifier({"amont": [], "pierre": ["amont", "quartz"], "quartz": ["pierre"], "aval": ["pierre"]}, 2)
        self.assertIn("pierre", str(cm.exception))
        self.assertIn("quartz", str(cm.exception))

    def test_cycle_est_une_valueerror(self):
        with self.assertRaises(ValueError):
            planifier({"a": ["b"], "b": ["a"]}, 1)

    def test_plafond_invalide_meme_sur_entree_vide(self):
        with self.assertRaises(ValueError):
            planifier({}, 0)

    def test_dependance_inconnue_profonde(self):
        with self.assertRaises(KeyError):
            planifier({"a": [], "b": ["a"], "c": ["b", "fantome"]}, 2)

    def test_entree_non_modifiee(self):
        t = {"a": [], "b": ["a"], "c": ["a", "b"]}
        avant = copy.deepcopy(t)
        planifier(t, 1)
        self.assertEqual(t, avant)


class Robustesse(unittest.TestCase):
    def test_longue_chaine(self):
        t = {"t%05d" % i: (["t%05d" % (i - 1)] if i else []) for i in range(3000)}
        d = time.perf_counter()
        self.assertEqual(len(planifier(t, 4)), 3000)
        self.assertLess(time.perf_counter() - d, 2.0)

    def test_beaucoup_de_taches_independantes(self):
        t = {"t%05d" % i: [] for i in range(3000)}
        d = time.perf_counter()
        self.assertEqual(len(planifier(t, 1)), 3000)
        self.assertLess(time.perf_counter() - d, 2.0)


if __name__ == "__main__":
    unittest.main()
