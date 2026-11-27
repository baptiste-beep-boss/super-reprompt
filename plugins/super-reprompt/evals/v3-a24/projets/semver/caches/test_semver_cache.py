# -*- coding: utf-8 -*-
"""Batterie cachee du projet semver. Chaque test decoule d'une phrase de ENONCE.md ; chaque methode regroupe ses cas
et rapporte TOUS les ecarts (un test = un verdict)."""
import unittest
from semver import satisfies, max_satisfying, RangeError


def collect(cases):
    """cases: (version, plage, attendu) -> liste des ecarts."""
    bad = []
    for v, r, exp in cases:
        try:
            got = satisfies(v, r)
        except Exception as e:      # noqa: BLE001
            got = "%s:%s" % (type(e).__name__, e)
        if got is not exp:
            bad.append((v, r, exp, got))
    return bad


def order_max(a, b, rng):
    return max_satisfying([a, b], rng)


class T(unittest.TestCase):
    # ---- versions
    def test_version_valide_formes_tolerees(self):
        cases = [("v1.2.3", "1.2.3", True), ("  1.2.3  ", "1.2.3", True), ("1.2.3+build.5", "1.2.3", True),
                 ("1.2.3+other", "=1.2.3+zzz", True), ("1.0.0-0a", "1.0.0-0a", True), ("1.0.0-01a", "1.0.0-01a", True),
                 ("1.0.0--", "1.0.0--", True), ("1.0.0-a-b.c-d+x", "1.0.0-a-b.c-d", True)]
        self.assertEqual(collect(cases), [])

    def test_version_invalide_leve_valueerror_pas_rangeerror(self):
        bad = []
        for v in ["1.2", "01.2.3", "1.02.3", "1.2.03", "1.2.3.4", "a.b.c", "", "1.2.3-", "1.2.3-01", "1.2.3-a..b", "1.2.3-.a",
                  "1.2.3+", "1.2.3+a..b", "1.2.3-00", "1.2.3-a.00", "1.2.3 4"]:
            try:
                satisfies(v, "*")
                bad.append((v, "aucune erreur"))
            except RangeError:
                bad.append((v, "RangeError"))
            except ValueError:
                pass
        self.assertEqual(bad, [])

    # ---- precedence
    def test_precedence_numerique_et_prerelease_inferieure_a_la_release(self):
        rng = ">=1.0.0-0 <=1.0.0"
        chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        bad = []
        for i in range(len(chain) - 1):
            lo, hi = chain[i], chain[i + 1]
            for a, b in ((lo, hi), (hi, lo)):
                if order_max(a, b, rng) != hi:
                    bad.append((lo, hi, a, b))
        self.assertEqual(bad, [])

    def test_identifiants_numeriques_contre_alphanumeriques(self):
        rng = ">=1.0.0-0 <=1.0.0"
        pairs = [("1.0.0-1", "1.0.0-0a"), ("1.0.0-9", "1.0.0-10"), ("1.0.0-a0", "1.0.0-a10"), ("1.0.0-B", "1.0.0-a"), ("1.0.0-a-", "1.0.0-a0"),
                 ("1.0.0-0", "1.0.0-1"), ("1.0.0-1.2", "1.0.0-1.2.0")]
        bad = [(lo, hi) for lo, hi in pairs if order_max(lo, hi, rng) != hi or order_max(hi, lo, rng) != hi]
        self.assertEqual(bad, [])

    def test_tuple_comparee_numeriquement(self):
        vs = ["1.9.0", "1.10.0", "1.2.10", "1.2.9", "0.99.99", "10.0.0", "2.0.0"]
        self.assertEqual(max_satisfying(vs, ">=0.0.0"), "10.0.0")
        self.assertEqual(max_satisfying(vs, "^1.0.0"), "1.10.0")
        self.assertEqual(max_satisfying(vs, "~1.2"), "1.2.10")

    # ---- operateurs et partielles
    def test_operateurs_simples_et_espaces(self):
        cases = [("1.2.3", ">=1.2.3", True), ("1.2.2", ">=1.2.3", False), ("1.2.3", ">1.2.3", False), ("1.2.4", ">1.2.3", True),
                 ("1.2.3", "<=1.2.3", True), ("1.2.3", "<1.2.3", False), ("1.2.2", "<1.2.3", True), ("1.2.3", "=1.2.3", True),
                 ("1.2.3", "= 1.2.3", True), ("1.2.3", ">= 1.2.3 <   2.0.0", True), ("2.0.0", ">= 1.2.3 < 2.0.0", False),
                 ("1.2.3", "  >=1.2.3   <1.2.4  ", True), ("1.2.4", ">=1.2.3 <1.2.4", False)]
        self.assertEqual(collect(cases), [])

    def test_partielles_sans_operateur(self):
        cases = [("1.0.0", "1", True), ("1.9.9", "1", True), ("2.0.0", "1", False), ("0.9.9", "1", False),
                 ("1.2.0", "1.2", True), ("1.2.9", "1.2", True), ("1.3.0", "1.2", False), ("1.1.9", "1.2", False),
                 ("1.2.5", "1.2.x", True), ("1.3.0", "1.2.X", False), ("1.2.5", "1.2.*", True), ("1.9.9", "1.x", True),
                 ("2.0.0", "1.X", False), ("1.5.5", "1.x.x", True), ("5.5.5", "x", True), ("5.5.5", "*", True), ("0.0.0", "=1.x", False),
                 ("1.4.0", "=1.4", True), ("1.5.0", "=1.4", False)]
        self.assertEqual(collect(cases), [])

    def test_partielles_avec_operateur(self):
        cases = [("1.2.9", ">1.2", False), ("1.3.0", ">1.2", True), ("1.2.0", ">=1.2", True), ("1.1.9", ">=1.2", False),
                 ("1.1.9", "<1.2", True), ("1.2.0", "<1.2", False), ("1.2.9", "<=1.2", True), ("1.3.0", "<=1.2", False),
                 ("1.9.9", ">1", False), ("2.0.0", ">1", True), ("1.9.9", "<=1", True), ("2.0.0", "<=1", False),
                 ("0.9.9", "<1", True), ("1.0.0", "<1", False), ("1.0.0", ">=1", True), ("1.2.0", ">=1.2.x", True), ("1.1.0", ">=1.2.x", False)]
        self.assertEqual(collect(cases), [])

    def test_joker_universel_et_blocs_vides(self):
        cases = [("1.2.3", "", True), ("0.0.0", "*", True), ("1.2.3", "||", True), ("1.2.3", "1.x ||", True), ("1.2.3", "   ", True),
                 ("1.2.3", ">=0.0.0", True), ("1.2.3", "x", True)]
        self.assertEqual(collect(cases), [])

    # ---- caret, tilde, tiret
    def test_caret(self):
        cases = [("1.2.3", "^1.2.3", True), ("1.9.9", "^1.2.3", True), ("2.0.0", "^1.2.3", False), ("1.2.2", "^1.2.3", False),
                 ("0.2.9", "^0.2.3", True), ("0.3.0", "^0.2.3", False), ("0.2.2", "^0.2.3", False),
                 ("0.0.3", "^0.0.3", True), ("0.0.4", "^0.0.3", False), ("0.0.2", "^0.0.3", False),
                 ("1.9.0", "^1.2", True), ("2.0.0", "^1.2", False), ("1.1.9", "^1.2", False),
                 ("0.0.9", "^0.0", True), ("0.1.0", "^0.0", False), ("0.9.9", "^0", True), ("1.0.0", "^0", False),
                 ("1.2.3", "^ 1.2.3", True)]
        self.assertEqual(collect(cases), [])

    def test_tilde(self):
        cases = [("1.2.3", "~1.2.3", True), ("1.2.9", "~1.2.3", True), ("1.3.0", "~1.2.3", False), ("1.2.2", "~1.2.3", False),
                 ("1.2.0", "~1.2", True), ("1.3.0", "~1.2", False), ("1.9.9", "~1", True), ("2.0.0", "~1", False), ("0.9.9", "~1", False),
                 ("0.2.9", "~0.2.3", True), ("0.3.0", "~0.2.3", False)]
        self.assertEqual(collect(cases), [])

    def test_tiret(self):
        cases = [("1.2.3", "1.2.3 - 2.3.4", True), ("2.3.4", "1.2.3 - 2.3.4", True), ("2.3.5", "1.2.3 - 2.3.4", False), ("1.2.2", "1.2.3 - 2.3.4", False),
                 ("2.3.9", "1.2.3 - 2.3", True), ("2.4.0", "1.2.3 - 2.3", False), ("2.9.9", "1.2.3 - 2", True), ("3.0.0", "1.2.3 - 2", False),
                 ("1.2.0", "1.2 - 2.3.4", True), ("1.1.9", "1.2 - 2.3.4", False), ("1.0.0", "1 - 2", True), ("2.9.9", "1 - 2", True),
                 ("3.0.0", "1 - 2", False), ("0.9.9", "1 - 2", False), ("1.5.0", "  1.2.3  -  2.0.0  ", True)]
        self.assertEqual(collect(cases), [])

    def test_union_de_blocs(self):
        cases = [("1.5.0", "^1.0.0 || ^3.0.0", True), ("2.5.0", "^1.0.0 || ^3.0.0", False), ("3.1.0", "^1.0.0 || ^3.0.0", True),
                 ("0.5.0", "<0.9.0 || >2.0.0", True), ("1.0.0", "<0.9.0 || >2.0.0", False), ("2.0.1", "<0.9.0 || >2.0.0", True),
                 ("1.2.3", ">=1.2.3 <1.2.4 || 9.9.9", True), ("9.9.9", ">=1.2.3 <1.2.4||9.9.9", True)]
        self.assertEqual(collect(cases), [])

    # ---- prereleases
    def test_prerelease_exclue_sauf_meme_triplette_avec_prerelease(self):
        cases = [("1.2.4-alpha", "^1.2.3", False), ("1.2.3-alpha", "^1.2.3", False), ("1.5.0-rc.1", "1.x", False), ("1.0.0-a", "*", False),
                 ("1.0.0-a", ">=0.0.0", False), ("2.0.0-alpha", "<2.0.0", False), ("1.9.9-x", "<2.0.0", False),
                 ("2.0.0-alpha", "<2.0.0-beta", True), ("2.0.0-gamma", "<2.0.0-beta", False),
                 ("1.2.3-beta.4", "^1.2.3-beta.2", True), ("1.2.3-beta.1", "^1.2.3-beta.2", False), ("1.2.3", "^1.2.3-beta.2", True),
                 ("1.2.4-alpha", "^1.2.3-beta.2", False), ("1.3.0-alpha", "^1.2.3-beta.2", False), ("1.9.0", "^1.2.3-beta.2", True),
                 ("1.0.0-beta", "1.0.0-beta", True), ("1.0.0-beta", "1.0.0", False), ("1.0.0-beta", "=1.0.0-beta+x", True),
                 ("1.0.0-beta.2", ">1.0.0-beta.1 <1.0.0", True), ("1.0.0-beta.1", ">1.0.0-beta.1 <1.0.0", False)]
        self.assertEqual(collect(cases), [])

    def test_regle_des_prereleases_appliquee_bloc_par_bloc(self):
        cases = [("1.2.3-beta.4", ">=1.2.3-beta.2 <2.0.0 || >=1.5.0", True), ("1.6.0-x", ">=1.2.3-beta.2 <2.0.0 || >=1.5.0", False),
                 ("2.0.0-beta", ">=1.0.0-alpha || 3.0.0-rc.1", False), ("1.0.0-beta", ">=1.0.0-alpha <1.0.1 || >=2.0.0", True),
                 ("2.0.0-beta", ">=1.0.0-alpha <1.0.1 || >=2.0.0", False), ("3.0.0-rc.1", ">=1.0.0-alpha || 3.0.0-rc.1", True),
                 ("1.0.0-beta", "1.0.0-beta || ^1.0.0-0", True), ("1.0.1-beta", ">=1.0.0-alpha <1.0.0 || >=1.0.1-0", True)]
        self.assertEqual(collect(cases), [])

    def test_prerelease_dans_tiret_et_borne_haute(self):
        cases = [("1.2.3-beta.3", "1.2.3-beta.2 - 2.0.0", True), ("1.2.3-beta.1", "1.2.3-beta.2 - 2.0.0", False), ("1.5.0", "1.2.3-beta.2 - 2.0.0", True),
                 ("2.0.0-beta", "1.2.3 - 2.0.0-rc.1", True), ("2.0.0", "1.2.3 - 2.0.0-rc.1", False), ("1.5.0", "1.2.3 - 2.0.0-rc.1", True)]
        self.assertEqual(collect(cases), [])

    # ---- max_satisfying
    def test_max_satisfying_plus_haute_precedence(self):
        vs = ["1.2.3", "1.10.0", "1.9.9", "2.0.0", "0.9.0"]
        self.assertEqual(max_satisfying(vs, "^1.0.0"), "1.10.0")
        self.assertEqual(max_satisfying(vs, ">=0.0.0"), "2.0.0")
        self.assertEqual(max_satisfying(vs, "<1.0.0"), "0.9.0")
        self.assertIsNone(max_satisfying(vs, "^3.0.0"))
        self.assertIsNone(max_satisfying([], "*"))

    def test_max_satisfying_rend_la_chaine_telle_qu_ecrite_et_la_premiere_a_egalite(self):
        self.assertEqual(max_satisfying(["1.0.0+b", "1.0.0+a"], "*"), "1.0.0+b")
        self.assertEqual(max_satisfying(["1.0.0", "1.0.0+a"], "*"), "1.0.0")
        self.assertEqual(max_satisfying(["v1.2.3", " 1.2.4 ", "1.2.4+z"], "^1.0.0"), " 1.2.4 ")
        self.assertEqual(max_satisfying(["v1.2.3"], "1.2.3"), "v1.2.3")

    def test_max_satisfying_avec_prereleases(self):
        vs = ["1.2.3-beta.2", "1.2.3-beta.11", "1.2.3-rc.1", "1.2.4-alpha", "1.2.2"]
        self.assertEqual(max_satisfying(vs, "^1.2.3-beta.2"), "1.2.3-rc.1")
        self.assertEqual(max_satisfying(vs, "^1.2.0"), "1.2.2")
        self.assertEqual(max_satisfying(["1.2.3-rc.1", "1.2.3-beta.11"], ">=1.2.3-beta.2"), "1.2.3-rc.1")

    def test_max_satisfying_version_invalide_dans_la_liste(self):
        for lst in (["1.2.3", "oops"], ["oops", "1.2.3"], ["1.2.3", "1.2", "1.3.0"], ["01.2.3"]):
            with self.assertRaises(ValueError) as cm:
                max_satisfying(lst, "^1.0.0")
            self.assertNotIsInstance(cm.exception, RangeError, lst)

    # ---- erreurs de plage
    def test_plages_invalides(self):
        bad = []
        for r in ["1.2.3.4", "foo", ">>1.0.0", "^", "~", ">=", "1.2.3 -", "- 1.2.3", "1.2.3 foo", "01.2.3", "1.2.3-01", "1.2.3-a..b",
                  "^^1.2.3", "1.2.3 - ", "=<1.2.3", "1.2.3 - 2.3.4 - 5.0.0", ">= >=1.2.3"]:
            try:
                satisfies("1.2.3", r)
                bad.append((r, "aucune erreur"))
            except RangeError:
                pass
            except Exception as e:  # noqa: BLE001
                bad.append((r, type(e).__name__))
        self.assertEqual(bad, [])

    def test_rangeerror_est_une_valueerror(self):
        self.assertTrue(issubclass(RangeError, ValueError))
        with self.assertRaises(RangeError):
            max_satisfying(["1.2.3"], "wat")


if __name__ == "__main__":
    unittest.main()
