import csv
import os
import tempfile
import unittest
from dedup import dedup, dedup_csv

L = [{"id": "1", "mail": "A@x.fr ", "nom": "a"}, {"id": "2", "mail": "a@X.fr", "nom": "b"}, {"id": "3", "mail": "c@x.fr", "nom": "c"}, {"id": "4", "mail": " a@x.fr", "nom": "d"}]


class T(unittest.TestCase):
    def test_premiere_occurrence_et_rapport(self):
        g, r = dedup(L, ["mail"])
        self.assertEqual([x["id"] for x in g], ["1", "3"])
        self.assertEqual(r, {"lus": 4, "gardes": 2, "doublons": {("a@x.fr",): 2}})

    def test_cle_composee_et_absente(self):
        g, _r = dedup(L, ["mail", "nom"])
        self.assertEqual(len(g), 4)
        with self.assertRaises(KeyError):
            dedup(L, ["tel"])

    def test_csv(self):
        d = tempfile.mkdtemp()
        e, s = os.path.join(d, "e.csv"), os.path.join(d, "s.csv")
        with open(e, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["nom", "mail", "id"])
            w.writeheader()
            w.writerows(L)
        r = dedup_csv(e, s, ["mail"])
        with open(s, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["nom", "mail", "id"])
        self.assertEqual([x[2] for x in rows[1:]], ["1", "3"])
        self.assertEqual(r["gardes"], 2)
