# -*- coding: utf-8 -*-
"""Lot L9 : migration du skill v1 (budget, bibliotheque de gabarits, routage) vers le plugin (code generique) et un profil prive
HORS depot ; mesure A4 (cout au repos <= 1 500 tokens). Bibliotheque standard, aucun reseau, aucun fichier reel de l'utilisateur :
tout se passe dans des dossiers temporaires et sur un faux skill v1."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import ROOT, SCRIPTS

import budget as B
import library as L

sys.path.insert(0, os.path.join(ROOT, "dev"))
import measure_idle as MI  # noqa: E402
import migrate_v1 as M  # noqa: E402


def usage(p5=54, wk=8, ctx=100, r5="2026-11-23T23:49:59.505Z", rw="2026-11-29T20:59:59.505Z", status="ok"):
    return {"plan": {"status": status, "windows": [{"label": "5-hour limit", "percentUsed": p5, "resetsAt": r5},
                                                    {"label": "Weekly · all models", "percentUsed": wk, "resetsAt": rw},
                                                    {"label": "Weekly · Sonnet only", "percentUsed": 99, "resetsAt": rw}]},
            "context": {"status": "ok", "tokensUsed": ctx}}


def wr(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    return path


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srl9_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        old = os.environ.get("SUPER_REPROMPT_HOME")
        os.environ["SUPER_REPROMPT_HOME"] = self.home          # jamais le vrai profil de l'utilisateur
        self.addCleanup(lambda: os.environ.__setitem__("SUPER_REPROMPT_HOME", old) if old is not None else os.environ.pop("SUPER_REPROMPT_HOME", None))
        self.ledger = os.path.join(self.home, "budget-journal.json")


class Budget(Env):
    def u(self, name, **kw):
        return wr(os.path.join(self.tmp, name + ".json"), usage(**kw))

    def test_start_pose_la_reference(self):
        code, out = B.run(["start", "m1", "--usage", self.u("s"), "--estime", "6"], ledger=self.ledger)
        self.assertEqual(code, 0)
        e = json.load(open(self.ledger, encoding="utf-8"))["m1"]
        self.assertEqual((e["start_5h"], e["start_hebdo"], e["estime"]), (54, 8, 6))
        self.assertIn("54", out)

    def test_fenetre_hebdo_choisie_sans_les_fenetres_par_modele(self):
        code, _ = B.run(["start", "m1", "--usage", self.u("s", wk=8)], ledger=self.ledger)
        self.assertEqual(json.load(open(self.ledger, encoding="utf-8"))["m1"]["start_hebdo"], 8)

    def test_end_calcule_les_deltas(self):
        B.run(["start", "m1", "--usage", self.u("s"), "--estime", "8"], ledger=self.ledger)
        code, out = B.run(["end", "m1", "--usage", self.u("e", p5=84, wk=12)], ledger=self.ledger)
        self.assertEqual(code, 0)
        e = json.load(open(self.ledger, encoding="utf-8"))["m1"]
        self.assertEqual((e["reel_hebdo"], e["reel_5h"]), (4, 30))
        self.assertIn("x0,50", out)

    def test_gigue_de_quelques_ms_n_est_pas_une_reinitialisation(self):
        B.run(["start", "m1", "--usage", self.u("s", r5="2026-11-23T23:50:00.014Z")], ledger=self.ledger)
        B.run(["end", "m1", "--usage", self.u("e", p5=60, r5="2026-11-23T23:49:59.979Z")], ledger=self.ledger)
        self.assertEqual(json.load(open(self.ledger, encoding="utf-8"))["m1"]["reel_5h"], 6)

    def test_reinitialisation_rend_le_delta_inexploitable_et_code_3_si_les_deux(self):
        B.run(["start", "m1", "--usage", self.u("s")], ledger=self.ledger)
        code, out = B.run(["end", "m1", "--usage", self.u("e", p5=3, wk=1, r5="2026-11-24T04:50:00Z", rw="2026-12-06T20:59:59Z")], ledger=self.ledger)
        self.assertEqual(code, 3)
        e = json.load(open(self.ledger, encoding="utf-8"))["m1"]
        self.assertIsNone(e["reel_hebdo"])
        self.assertIsNone(e["reel_5h"])

    def test_fin_sans_debut_est_gardee_comme_ancrage_et_exclue_du_facteur(self):
        code, out = B.run(["end", "orph", "--usage", self.u("e")], ledger=self.ledger)
        self.assertEqual(code, 2)
        e = json.load(open(self.ledger, encoding="utf-8"))["orph"]
        self.assertEqual(e["mesure"], "sans_reference")
        self.assertIsNone(e["reel_hebdo"])

    def test_limites_de_plan_illisibles_refusees(self):
        code, out = B.run(["start", "m1", "--usage", self.u("s", status="unavailable")], ledger=self.ledger)
        self.assertEqual(code, 2)
        self.assertFalse(os.path.exists(self.ledger))

    def test_calibration_exige_3_missions_completes(self):
        for i, (est, reel) in enumerate([(8, 4), (6, 3)]):
            B.run(["start", "m%d" % i, "--usage", self.u("s%d" % i, wk=10), "--estime", str(est)], ledger=self.ledger)
            B.run(["end", "m%d" % i, "--usage", self.u("e%d" % i, wk=10 + reel)], ledger=self.ledger)
        code, out = B.run(["calibrate"], ledger=self.ledger)
        self.assertEqual(code, 0)
        self.assertIn("AUCUN facteur", out)

    def test_calibration_mediane_et_verdict(self):
        for i, (est, reel) in enumerate([(10, 20), (10, 25), (10, 30)]):
            B.run(["start", "m%d" % i, "--usage", self.u("s%d" % i, wk=10), "--estime", str(est)], ledger=self.ledger)
            B.run(["end", "m%d" % i, "--usage", self.u("e%d" % i, wk=10 + reel)], ledger=self.ledger)
        code, out = B.run(["calibrate"], ledger=self.ledger)
        self.assertIn("2,50", out)
        self.assertIn("SOUS-ESTIME", out)

    def test_partielle_exclue_de_la_calibration(self):
        for i in range(3):
            B.run(["start", "m%d" % i, "--usage", self.u("s%d" % i, wk=10), "--estime", "10", "--mesure", "partielle"], ledger=self.ledger)
            B.run(["end", "m%d" % i, "--usage", self.u("e%d" % i, wk=20)], ledger=self.ledger)
        self.assertIn("AUCUN facteur", B.run(["calibrate"], ledger=self.ledger)[1])

    def test_journal_liste_les_entrees(self):
        B.run(["start", "m1", "--usage", self.u("s"), "--estime", "6"], ledger=self.ledger)
        code, out = B.run(["journal"], ledger=self.ledger)
        self.assertIn("m1", out)
        self.assertIn("en cours", out)

    def test_cli_respecte_SUPER_REPROMPT_HOME_et_n_ecrit_pas_ailleurs(self):
        env = dict(os.environ, SUPER_REPROMPT_HOME=self.home, PYTHONUTF8="1")
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "budget.py"), "start", "cli", "--usage", self.u("s"), "--estime", "3"],
                           env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(os.path.isfile(self.ledger))

    def test_report_dans_la_note_de_bibliotheque_si_elle_existe(self):
        lib = os.path.join(self.tmp, "lib")
        os.makedirs(lib)
        open(os.path.join(lib, "om-m1.md"), "w", encoding="utf-8").write("---\ntitre: t\ncout_reel_hebdo:\ncout_reel_5h:\n---\nbody\n")
        B.run(["start", "m1", "--usage", self.u("s"), "--estime", "8"], ledger=self.ledger)
        B.run(["end", "m1", "--usage", self.u("e", p5=84, wk=12), "--library", lib], ledger=self.ledger)
        t = open(os.path.join(lib, "om-m1.md"), encoding="utf-8").read()
        self.assertIn("cout_reel_hebdo: 4", t)
        self.assertIn("cout_reel_5h: 30", t)
        self.assertIn("body", t)


GABARIT = """## Demande d'origine
x
## Ce qui a ete livre
x
## Squelette reutilisable
1. cadrer
## Reutiliser ce gabarit quand
la demande ressemble a ceci
## Ce qui a marche
x
## Ce qui a rate
x
"""


class Library(Env):
    def setUp(self):
        super().setUp()
        self.lib = os.path.join(self.tmp, "lib")
        os.makedirs(self.lib)
        open(os.path.join(self.lib, "INDEX.md"), "w", encoding="utf-8").write("# Hub\n\nprose a la main\n")
        self.body = os.path.join(self.tmp, "corps.md")
        open(self.body, "w", encoding="utf-8").write(GABARIT)

    def add(self, slug="alloc-secteur", croch="etf,allocation,portefeuille", verdict="reussi", **kw):
        args = ["add", slug, "--titre", "Allocation", "--classe", "ANALYSE", "--crochets", croch, "--verdict", verdict, "--corps", self.body, "--dir", self.lib]
        for k, v in kw.items():
            args += ["--" + k.replace("_", "-")] + ([] if k == "force" else [v])
        return L.run(args)

    def test_add_ecrit_la_note_et_regenere_le_tableau(self):
        code, out = self.add()
        self.assertEqual(code, 0, out)
        note = open(os.path.join(self.lib, "om-alloc-secteur.md"), encoding="utf-8").read()
        self.assertIn("crochets: [etf, allocation, portefeuille]", note)
        self.assertIn("reutilisations: 0", note)
        self.assertIn("[[INDEX]]", note)                      # rattachement : pas d'orpheline
        idx = open(os.path.join(self.lib, "INDEX.md"), encoding="utf-8").read()
        self.assertIn("prose a la main", idx)
        self.assertIn("[[om-alloc-secteur]]", idx)

    def test_validations(self):
        self.assertEqual(self.add(slug="Mauvais Slug")[0], 2)
        self.assertEqual(self.add(croch="a,b")[0], 2)                       # < 3 crochets
        self.assertEqual(self.add(croch="étf,allocation,portefeuille")[0], 2)  # accents
        open(self.body, "w", encoding="utf-8").write("## Demande d'origine\nx\n")
        self.assertEqual(self.add()[0], 2)                                  # sections eliminatoires absentes
        open(self.body, "w", encoding="utf-8").write(GABARIT)
        self.assertEqual(self.add()[0], 0)
        self.assertEqual(self.add()[0], 2)                                  # existe deja
        self.assertEqual(self.add(force="1")[0], 0)

    def test_search_classe_par_score_et_correspondance_partielle(self):
        self.add("alloc", "etf,allocation,portefeuille")
        self.add("code-hook", "hook,settings,python")
        code, out = L.run(["search", "--crochets", "etfs,portefeuilles", "--dir", self.lib])
        self.assertEqual(code, 0)
        self.assertIn("alloc", out)
        self.assertNotIn("code-hook", out)

    def test_search_aucun_candidat_code_3(self):
        self.add()
        self.assertEqual(L.run(["search", "--crochets", "zzz", "--dir", self.lib])[0], 3)

    def test_bibliotheque_vide_code_3(self):
        self.assertEqual(L.run(["search", "--crochets", "etf", "--dir", self.lib])[0], 3)

    def test_antigabarit_signale(self):
        self.add("rate", "etf,allocation,portefeuille", verdict="echec")
        self.assertIn("ANTI-GABARIT", L.run(["search", "--crochets", "etf", "--dir", self.lib])[1])

    def test_mark_used_incremente_et_regenere(self):
        self.add()
        self.assertEqual(L.run(["mark-used", "alloc-secteur", "--dir", self.lib])[0], 0)
        self.assertIn("reutilisations: 1", open(os.path.join(self.lib, "om-alloc-secteur.md"), encoding="utf-8").read())
        self.assertEqual(L.run(["mark-used", "inconnu", "--dir", self.lib])[0], 2)

    def test_dossier_de_bibliotheque_via_profil_prive(self):
        prof = os.path.join(self.home, "profile.md")
        open(prof, "w", encoding="utf-8").write("---\nlang: fr\nlibrary_dir: %s\n---\n" % self.lib.replace("\\", "/"))
        self.add()
        env = dict(os.environ, SUPER_REPROMPT_HOME=self.home, PYTHONUTF8="1")
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "library.py"), "search", "--crochets", "etf"], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("alloc-secteur", p.stdout)

    def test_sans_dossier_configure_refus_clair(self):
        env = {k: v for k, v in os.environ.items() if k != "SUPER_REPROMPT_LIBRARY"}
        env.update(SUPER_REPROMPT_HOME=self.home, PYTHONUTF8="1")
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "library.py"), "search", "--crochets", "etf"], env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 2)


V1_ROUTAGE = """# Routage

## Declencheurs metier

| Si la mission touche... | Invoquer | Phase |
|---|---|---|
| ISIN, ticker, ETF | `/skill-finance` | analyse |
| graphique, courbe | `/skill-dataviz` **avant la 1re ligne** | production |

## Declencheurs techniques

| Si la mission touche... | Invoquer | Phase |
|---|---|---|
| PDF en entree | `outil-pdf` | lecture |
"""


class Migration(Env):
    def setUp(self):
        super().setUp()
        self.v1 = os.path.join(self.tmp, "v1")
        os.makedirs(os.path.join(self.v1, "base"))
        os.makedirs(os.path.join(self.v1, "scripts"))
        open(os.path.join(self.v1, "base", "routage.md"), "w", encoding="utf-8").write(V1_ROUTAGE)
        wr(os.path.join(self.v1, "base", "journal-budgets.json"), {"old": {"slug": "old", "estime": 4, "mesure": "complete", "reel_hebdo": 3, "reel_5h": 9}})
        open(os.path.join(self.v1, "scripts", "budget.ps1"), "w", encoding="utf-8").write("# v1\n")
        self.out = os.path.join(self.tmp, "prive")

    def hashes(self):
        h = {}
        for dp, _dn, fn in os.walk(self.v1):
            for f in fn:
                p = os.path.join(dp, f)
                h[p] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        return h

    def test_copie_sans_toucher_au_v1(self):
        before = self.hashes()
        M.migrate(self.v1, self.out, lang="fr", forbid=["skill-x"], library_dir="/lib/prive")
        self.assertEqual(before, self.hashes())

    def test_produit_profil_routage_et_journal(self):
        rep = M.migrate(self.v1, self.out, lang="fr", forbid=["skill-x"], library_dir="/lib/prive")
        prof = open(os.path.join(self.out, "profile.md"), encoding="utf-8").read()
        self.assertIn("lang: fr", prof)
        self.assertIn("library_dir: /lib/prive", prof)
        self.assertIn("forbidden_capabilities", prof)
        self.assertIn("skill-x", prof)
        self.assertIn("/skill-finance", prof)                       # triplets de routage dans le profil
        self.assertTrue(os.path.isfile(os.path.join(self.out, "routing.md")))
        self.assertEqual(json.load(open(os.path.join(self.out, "budget-journal.json"), encoding="utf-8"))["old"]["reel_hebdo"], 3)
        self.assertEqual(rep["triplets"], 3)

    def test_marques_de_gras_retirees_des_triplets(self):
        open(os.path.join(self.v1, "base", "routage.md"), "w", encoding="utf-8").write("| Si | Invoquer | Phase |\n|---|---|---|\n| t | `/c` **avant** tout | **avant** toute regle |\n")
        M.migrate(self.v1, self.out, lang="fr")
        self.assertNotIn("**", open(os.path.join(self.out, "profile.md"), encoding="utf-8").read())
        self.assertNotIn("avant**", open(os.path.join(self.out, "profile.md"), encoding="utf-8").read())

    def test_hub_de_bibliotheque_ecrit_dans_le_profil(self):
        M.migrate(self.v1, self.out, lang="fr", library_dir="/lib/prive", library_hub="00-MOC-x.md")
        self.assertIn("library_hub: 00-MOC-x.md", open(os.path.join(self.out, "profile.md"), encoding="utf-8").read())

    def test_profil_sous_le_plafond_de_1000_tokens_meme_avec_beaucoup_de_routage(self):
        rows = "\n".join("| trigger %d with some words | `/cap-%d` | analyse |" % (i, i) for i in range(200))
        open(os.path.join(self.v1, "base", "routage.md"), "w", encoding="utf-8").write("| Si | Invoquer | Phase |\n|---|---|---|\n" + rows + "\n")
        rep = M.migrate(self.v1, self.out, lang="fr")
        prof = open(os.path.join(self.out, "profile.md"), encoding="utf-8").read()
        self.assertLessEqual(len(prof) / 3.7, 1000)
        self.assertEqual(rep["triplets"], 200)
        self.assertIn("routing.md", prof)                           # le reste reste lisible a la demande
        self.assertEqual(len(re.findall(r"cap-", open(os.path.join(self.out, "routing.md"), encoding="utf-8").read())), 200)

    def test_ne_remplace_jamais_un_profil_existant(self):
        os.makedirs(self.out)
        open(os.path.join(self.out, "profile.md"), "w", encoding="utf-8").write("mon profil\n")
        with self.assertRaises(FileExistsError):
            M.migrate(self.v1, self.out, lang="fr")
        self.assertEqual(open(os.path.join(self.out, "profile.md"), encoding="utf-8").read(), "mon profil\n")

    def test_refuse_une_sortie_dans_un_depot_git(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(repo, ".git"))
        with self.assertRaises(ValueError):
            M.migrate(self.v1, os.path.join(repo, "profil"), lang="fr")

    def test_v1_absent(self):
        with self.assertRaises(FileNotFoundError):
            M.migrate(os.path.join(self.tmp, "nope"), self.out, lang="fr")


class RienDePersonnelDansLeDepot(unittest.TestCase):
    """La preuve : aucun fichier suivi par git (hors vendor/, copies tierces figees) ne contient de donnee personnelle."""
    FORBIDDEN = ["".join(parts) for parts in (          # assembles par morceaux : ce fichier ne se declenche pas lui-meme
        ("de", "sag"), ("claude-", "mem", "ory"), ("ordres-", "mis", "sion"), ("gestion-", "pri", "vee"), ("bour", "se-dd"), ("tok", "en-dd"),
        ("sizing-", "allo", "cation"), ("fonds-", "hed", "ge"), ("C:\\\\Users\\\\", "d"), ("Bap", "tiste"))]
    HANDLE = re.compile(r"baptiste-beep-boss", re.I)

    def test_aucune_donnee_personnelle_suivie_par_git(self):
        top = subprocess.run(["git", "-C", ROOT, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=30).stdout.strip()
        files = subprocess.run(["git", "-C", top, "ls-files", "-z"], capture_output=True, timeout=60).stdout.decode("utf-8", "replace").split("\0")
        hits = []
        rx = [re.compile(re.escape(f), re.I) for f in self.FORBIDDEN]
        n = 0
        for rel in files:
            if not rel or "/vendor/" in "/" + rel or rel.endswith((".png", ".svg")) or rel.endswith("catalog/catalog.jsonl"):
                continue
            p = os.path.join(top, rel)
            if not os.path.isfile(p):
                continue
            n += 1
            text = self.HANDLE.sub("<handle>", open(p, "rb").read().decode("utf-8", "replace"))
            for r in rx:
                if r.search(text):
                    hits.append((rel, r.pattern))
        self.assertGreater(n, 100)
        # ce fichier-ci cite les motifs par concatenation : il ne doit pas se declencher lui-meme
        self.assertEqual(hits, [])

    def test_le_detecteur_detecte(self):
        rx = [re.compile(re.escape(f), re.I) for f in self.FORBIDDEN]
        for bad in ("C:\\Users\\" + "de" + "sag" + "\\x", "mon vault claude-" + "mem" + "ory", "Bap" + "tiste D."):
            self.assertTrue(any(r.search(self.HANDLE.sub("<handle>", bad)) for r in rx), bad)
        self.assertFalse(any(r.search(self.HANDLE.sub("<handle>", "https://github.com/" + "baptiste-beep-boss" + "/super-reprompt")) for r in rx))


class A4CoutAuRepos(unittest.TestCase):
    def test_cout_au_repos_du_plugin_sous_1500_tokens(self):
        r = MI.idle()
        self.assertLessEqual(r["total"], 1500, r)
        names = {x["name"] for x in r["items"]}
        self.assertIn("super-reprompt", names)
        self.assertGreaterEqual(len(r["items"]), 10)              # skill + tous les agents sont comptes

    def test_aucun_hook_n_ajoute_de_tokens_au_repos(self):
        self.assertEqual(MI.idle()["hooks_at_rest_tokens"], 0)

    def test_check_code_de_sortie(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "dev", "measure_idle.py"), "--check"], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("A4", p.stdout)

    def test_le_plafond_est_reellement_applique(self):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        os.makedirs(os.path.join(d, "agents"))
        os.makedirs(os.path.join(d, "skills", "x"))
        open(os.path.join(d, "skills", "x", "SKILL.md"), "w", encoding="utf-8").write("---\nname: x\ndescription: " + "mot " * 2000 + "\n---\n")
        self.assertGreater(MI.idle(d)["total"], 1500)


if __name__ == "__main__":
    unittest.main()
