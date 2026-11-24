# -*- coding: utf-8 -*-
"""Lot 4 V3.1 : Eclaireur universel. Tous les types de capacites (pas seulement les skills), raisons de choix et
d'ecart, integrite verifiee contre l'empreinte du catalogue, pas de doublon, budget de contexte explicite et MESURE,
appel depuis le compilateur de plan."""
import copy
import os
import unittest

from _t import ROOT, TmpCase, valid_state

import catalog as CAT
import compile_plan as CP
import contracts as C
import eclaireur as E

ELS = CAT.load_catalog()


def tache(**cr):
    return {"id": "T1", "crochets": cr, "files": []}


class Universel(unittest.TestCase):
    def test_default_ranking_still_skills_only(self):                 # A19 unchanged
        r = E.scout(tache(domaine="accessibility", acte="audit"), ELS)
        self.assertTrue(r["classement"])
        self.assertTrue(all(x["id"].split(":")[1] == "skill" or x["cercle"] == 1 for x in r["classement"]))

    def test_other_types_are_selected(self):
        r = E.capacites(tache(domaine="accessibility", acte="review", livrable="ui"), ELS)
        types = {x["type"] for x in r["retenues"]}
        self.assertIn("skill", types)
        self.assertTrue(types - {"skill"}, r)                          # at least one non-skill capability
        for x in r["retenues"]:
            self.assertTrue(x["raison"])

    def test_every_selectable_type_reachable(self):
        cases = {"agent": tache(domaine="security", acte="review"), "commande": tache(langage="python", acte="review"),
                 "règle": tache(langage="python", livrable="patterns"), "hook": tache(domaine="mcp", livrable="server"),
                 "schéma": tache(livrable="schema", acte="create")}
        for ty, t in cases.items():
            r = E.capacites(t, ELS, types=(ty,), seuil=0.3)
            self.assertTrue(r["retenues"], "%s : %s" % (ty, r["ecartees"][:3]))
            self.assertEqual(r["retenues"][0]["type"], ty)

    def test_budget_is_explicit_and_measured(self):
        r = E.capacites(tache(domaine="security", acte="review", langage="python"), ELS, budget=2500)
        self.assertLessEqual(r["contexte_tokens"], 2500)
        self.assertEqual(r["budget"], 2500)
        self.assertTrue(any("budget" in x["raison"] for x in r["ecartees"]), r["ecartees"][:5])
        self.assertTrue(all(x["cout_source"] in ("mesure", "estime") for x in r["retenues"]))
        self.assertTrue(any(x["cout_source"] == "mesure" for x in r["retenues"]))

    def test_integrity_failure_excludes(self):
        els = copy.deepcopy(ELS)
        target = next(e for e in els if e["id"] == "ecc:agent:security-reviewer")
        target["sha"] = "0" * 64
        r = E.capacites(tache(domaine="security", acte="review"), els, types=("agent",), seuil=0.3)
        self.assertNotIn("ecc:agent:security-reviewer", [x["id"] for x in r["retenues"]])
        self.assertTrue(any(x["id"] == "ecc:agent:security-reviewer" and "integrite" in x["raison"] for x in r["ecartees"]))
        self.assertTrue(E.integrite(next(e for e in ELS if e["id"] == "ecc:agent:security-reviewer"))[0])

    def test_multi_file_skill_integrity_uses_composite_digest(self):
        ok, why = E.integrite(next(e for e in ELS if e["id"] == "ecc:skill:security-review"), ELS)
        self.assertTrue(ok, why)

    def test_whole_selectable_catalogue_passes_integrity(self):
        bad = []
        for e in ELS:
            if e["type"] in E.TOUS_TYPES and e["statut"] not in E.EXCLUS and not e.get("verrou") and not e.get("doublon_de"):
                ok, why = E.integrite(e, ELS)
                if not ok:
                    bad.append((e["id"], why))
        self.assertEqual(bad, [])

    def test_no_two_equivalent_capabilities(self):
        r = E.capacites(tache(domaine="security", acte="review"), ELS, par_type=3, seuil=0.3)
        noms = [E.nom_norm(x["nom"]) for x in r["retenues"]]
        self.assertEqual(len(noms), len(set(noms)))

    def test_catalogue_never_loaded_whole(self):
        r = E.capacites(tache(domaine="security", acte="review"), ELS)
        full = sum(e.get("coût_tokens") or 0 for e in ELS)
        self.assertLess(r["contexte_tokens"], full / 50)


class CompilerCallsScout(TmpCase):
    def test_plan_carries_capability_plan_and_budget(self):
        st = valid_state("demo-mission", tasks=[
            {"id": "T1", "title": "revue securite", "covers": ["R1", "C1"], "preuve": "V1",
             "crochets": {"domaine": "security", "acte": "review", "langage": "python"}}])
        self.make_mission(state=st)
        plan, _ = CP.compile_plan(self.project, "demo-mission")
        caps = plan["tasks"][0]["capabilities"]
        self.assertTrue(caps)
        self.assertTrue({c["type"] for c in caps} - {"skill"})
        cb = plan["context_budget"]
        self.assertLessEqual(cb["tokens"], cb["budget"])
        self.assertEqual(C.validate("plan", plan, strict=True), [])
        plan2, rep = CP.compile_plan(self.project, "demo-mission")
        self.assertEqual(rep["action"], "inchange")                    # deterministic: same capabilities, same hash
        import econ
        b = econ.brief(plan["tasks"][0], {"slug": "demo-mission"})
        for c in caps:
            self.assertIn(c["id"], b)                                  # the executor's brief carries the selection, nothing more


if __name__ == "__main__":
    unittest.main()
