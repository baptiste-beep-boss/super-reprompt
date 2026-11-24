# -*- coding: utf-8 -*-
"""Batterie etendue A24, projet moyen. Ecrite et figee le 24/11/2026 AVANT tout essai de la methode testee.
Classe Spec : exigences tirees mot pour mot de ENONCE.md. Classe Robustesse : hors enonce strict (signalee a part)."""
import csv
import os
import shutil
import tempfile
import unittest
from dedup import dedup, dedup_csv


def ecrire(chemin, entetes, lignes, bom=False):
    with open(chemin, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(entetes)
        w.writerows(lignes)


def lire(chemin):
    with open(chemin, encoding="utf-8", newline="") as f:
        return list(csv.reader(f))


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def p(self, n):
        return os.path.join(self.d, n)


class Spec(Base):
    def test_liste_vide(self):
        self.assertEqual(dedup([], ["a"]), ([], {"lus": 0, "gardes": 0, "doublons": {}}))

    def test_cle_absente_sur_une_ligne_ulterieure(self):
        with self.assertRaises(KeyError):
            dedup([{"a": "1"}, {"b": "2"}], ["a"])

    def test_cle_composee_normalisee_dans_le_rapport(self):
        g, r = dedup([{"a": " X ", "b": "y"}, {"a": "x", "b": "Y "}, {"a": "x", "b": "z"}], ["a", "b"])
        self.assertEqual(len(g), 2)
        self.assertEqual(r["doublons"], {("x", "y"): 1})

    def test_rapport_sans_entree_a_zero(self):
        _g, r = dedup([{"a": "1"}, {"a": "2"}], ["a"])
        self.assertEqual(r["doublons"], {})

    def test_valeurs_gardees_intactes_et_ordre(self):
        L = [{"m": "B "}, {"m": "a"}, {"m": "b"}, {"m": " A"}]
        g, r = dedup(L, ["m"])
        self.assertEqual(g, [{"m": "B "}, {"m": "a"}])
        self.assertEqual(r, {"lus": 4, "gardes": 2, "doublons": {("b",): 1, ("a",): 1}})

    def test_csv_entete_seule(self):
        ecrire(self.p("e.csv"), ["id", "m"], [])
        r = dedup_csv(self.p("e.csv"), self.p("s.csv"), ["m"])
        self.assertEqual(lire(self.p("s.csv")), [["id", "m"]])
        self.assertEqual((r["lus"], r["gardes"]), (0, 0))

    def test_csv_guillemets_virgule_saut_de_ligne_et_accents(self):
        rows = [["1", "é@x.fr", "Dupont, \"Jean\"\nligne 2"], ["2", " É@X.FR", "x"], ["3", "b@x.fr", "y"]]
        ecrire(self.p("e.csv"), ["id", "m", "note"], rows)
        r = dedup_csv(self.p("e.csv"), self.p("s.csv"), ["m"])
        out = lire(self.p("s.csv"))
        self.assertEqual(out[0], ["id", "m", "note"])
        self.assertEqual(out[1], rows[0])
        self.assertEqual([x[0] for x in out[1:]], ["1", "3"])
        self.assertEqual(r["gardes"], 2)

    def test_csv_colonne_de_cle_absente(self):
        ecrire(self.p("e.csv"), ["id"], [["1"]])
        with self.assertRaises(KeyError):
            dedup_csv(self.p("e.csv"), self.p("s.csv"), ["m"])


class Robustesse(Base):
    def test_csv_avec_bom(self):
        ecrire(self.p("e.csv"), ["m", "id"], [["a", "1"], ["A", "2"]], bom=True)   # le BOM colle a la 1re colonne
        r = dedup_csv(self.p("e.csv"), self.p("s.csv"), ["m"])
        self.assertEqual(r["gardes"], 1)

    def test_gros_volume(self):
        import time
        L = [{"m": str(i % 5000)} for i in range(100000)]
        t = time.perf_counter()
        _g, r = dedup(L, ["m"])
        self.assertLess(time.perf_counter() - t, 3.0)
        self.assertEqual(r["gardes"], 5000)


if __name__ == "__main__":
    unittest.main()
