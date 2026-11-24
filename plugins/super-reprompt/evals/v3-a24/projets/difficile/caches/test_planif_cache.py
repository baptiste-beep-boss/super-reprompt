import unittest
from planif import planifier, CycleError


class T(unittest.TestCase):
    def test_vagues_et_plafond(self):
        t = {"a": [], "b": [], "c": [], "d": ["a"], "e": ["a", "b"], "f": ["e"]}
        self.assertEqual(planifier(t, 2), [["a", "b"], ["c", "d"], ["e"], ["f"]])
        self.assertEqual(planifier(t, 3), [["a", "b", "c"], ["d", "e"], ["f"]])

    def test_vide(self):
        self.assertEqual(planifier({}, 2), [])

    def test_cycle(self):
        with self.assertRaises(CycleError) as cm:
            planifier({"x": ["z"], "y": ["x"], "z": ["y"], "w": []}, 2)
        for n in ("x", "y", "z"):
            self.assertIn(n, str(cm.exception))
        self.assertTrue(issubclass(CycleError, ValueError))

    def test_erreurs(self):
        with self.assertRaises(KeyError):
            planifier({"a": ["inconnue"]}, 1)
        with self.assertRaises(ValueError):
            planifier({"a": []}, 0)
