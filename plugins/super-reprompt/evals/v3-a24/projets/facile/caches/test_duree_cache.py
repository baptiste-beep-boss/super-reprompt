import unittest
from duree import parse_duree


class T(unittest.TestCase):
    def test_valides(self):
        for s, v in (("1h30m", 5400), ("45s", 45), ("2h", 7200), ("1h5s", 3605), ("  10m ", 600), ("0s", 0)):
            self.assertEqual(parse_duree(s), v, s)

    def test_invalides(self):
        for s in ("", "abc", "1x", "30m1h", "-5s", "1h1h", "h", "1.5h"):
            with self.assertRaises(ValueError, msg=s):
                parse_duree(s)
