# -*- coding: utf-8 -*-
"""Lot 11 : declenchement automatique du protocole de contre-epreuve sur une tache de code non triviale.
Constat du banc V3.1 : sur « Realise le projet decrit dans ENONCE.md. » le cycle ne se declenchait jamais (invite
de 40 caracteres, sous le seuil MIN_LEN). Le declencheur est une fonction pure testee ici, plus le hook de bout en bout."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from _t import ROOT, SCRIPTS

import hook_suggest as HS  # noqa: E402

HOOK = os.path.join(SCRIPTS, "hook_suggest.py")

SHOULD_ENGAGE = [
    "Réalise le projet décrit dans ENONCE.md.",
    "Implémente le module décrit dans SPEC.md et ses tests.",
    "Build the project described in README.md.",
    "Développe une bibliothèque de parsing et son API publique, avec des tests.",
    "Please implement everything in the spec file SPEC.md, standard library only.",
    "Construis le projet décrit dans le cahier des charges CDC.md",
    "Écris le module décrit dans ENONCE.md",
]
SHOULD_STAY_SILENT = [
    "Écris une fonction qui additionne deux nombres.",
    "Corrige le bug dans foo.py ligne 12.",
    "Pourquoi ce module plante-t-il au démarrage ?",
    "/review",
    "go direct : réalise le projet décrit dans ENONCE.md.",
    "Réalise le projet décrit dans ENONCE.md, sans contre-épreuve.",
    "Réalise le projet décrit dans ENONCE.md. Pas de contre-épreuve, c'est un essai rapide.",
    "bonjour",
    "merci, c'est parfait",
    "Explique-moi ce que fait ENONCE.md",
    "Renomme la variable x en total dans calc.py",
    "Lis ENONCE.md et résume-le",
    "How do I build the project described in README.md?",
]


class EngageDetector(unittest.TestCase):
    def test_taches_de_code_non_triviales_declenchent(self):
        ratees = [p for p in SHOULD_ENGAGE if not HS.is_code_task(p)]
        self.assertEqual(ratees, [])

    def test_demandes_triviales_ou_exclues_restent_silencieuses(self):
        fausses = [p for p in SHOULD_STAY_SILENT if HS.is_code_task(p)]
        self.assertEqual(fausses, [])

    def test_fonction_pure_sur_entrees_etranges(self):
        for p in (None, 42, "", "   ", "\n"):
            self.assertFalse(HS.is_code_task(p))

    def test_la_ligne_decrit_le_protocole_court_et_nomme_l_agent(self):
        for lang in ("fr", "en"):
            line = HS.engage_line(lang)
            self.assertLess(len(line), 1100)
            self.assertNotIn("\n\n", line)
            for need in ("sr-testeur", "Agent", "énoncé" if lang == "fr" else "spec"):
                self.assertIn(need, line)
            self.assertIn("un seul passage" if lang == "fr" else "one pass", line.lower())


class EngageHookEndToEnd(unittest.TestCase):
    def run_hook(self, prompt, sid="s-engage-1", home=None, extra_env=None):
        env = dict(os.environ, SUPER_REPROMPT_HOME=home or self.home)
        env.pop("SUPER_REPROMPT_HOOKS", None)
        env.update(extra_env or {})
        data = {"session_id": sid, "cwd": self.cwd, "prompt": prompt}
        p = subprocess.run([sys.executable, "-I", HOOK], input=json.dumps(data).encode("utf-8"), env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        return p.returncode, p.stdout.decode("utf-8", "replace")

    def setUp(self):
        self.home = tempfile.mkdtemp(prefix="srhome-")
        self.cwd = tempfile.mkdtemp(prefix="srcwd-")

    def test_invite_courte_de_code_emet_le_protocole(self):
        rc, out = self.run_hook("Réalise le projet décrit dans ENONCE.md.")
        self.assertEqual(rc, 0)
        self.assertIn("[super-reprompt]", out)
        self.assertIn("sr-testeur", out)

    def test_une_seule_fois_par_session_puis_silence(self):
        _rc, first = self.run_hook("Réalise le projet décrit dans ENONCE.md.", sid="s-2")
        _rc, second = self.run_hook("Réalise aussi le projet décrit dans AUTRE.md.", sid="s-2")
        self.assertIn("sr-testeur", first)
        self.assertEqual(second.strip(), "")

    def test_hooks_coupes_silence_total(self):
        rc, out = self.run_hook("Réalise le projet décrit dans ENONCE.md.", extra_env={"SUPER_REPROMPT_HOOKS": "0"})
        self.assertEqual((rc, out.strip()), (0, ""))

    def test_demande_triviale_aucune_sortie(self):
        rc, out = self.run_hook("Écris une fonction qui additionne deux nombres.")
        self.assertEqual((rc, out.strip()), (0, ""))

    def test_la_suggestion_de_cadrage_existante_reste_inchangee(self):
        long_ask = ("Je veux un audit complet et approfondi de notre architecture, avec un rapport détaillé des risques, "
                    "une analyse de la dette technique et un plan d'action chiffré sur trois mois.")
        _rc, out = self.run_hook(long_ask, sid="s-3")
        self.assertIn("mission", out.lower())
        self.assertNotIn("sr-testeur", out)


class TesteurAgentCard(unittest.TestCase):
    def test_fiche_agent_valide_et_boite_noire(self):
        path = os.path.join(ROOT, "agents", "sr-testeur.md")
        self.assertTrue(os.path.isfile(path), "agents/sr-testeur.md manquant")
        with open(path, encoding="utf-8") as f:
            txt = f.read()
        head, _sep, body = txt.partition("\n---\n")
        self.assertTrue(head.startswith("---"))
        fm = dict(ln.split(":", 1) for ln in head.splitlines()[1:] if ":" in ln)
        fm = {k.strip(): v.strip() for k, v in fm.items()}
        self.assertEqual(fm.get("name"), "sr-testeur")
        self.assertEqual(fm.get("model"), "sonnet")                 # modele toujours explicite
        for outil in ("Read", "Write", "Bash"):
            self.assertIn(outil, fm.get("tools", ""))
        self.assertNotIn("Edit", fm.get("tools", ""))                # il n'edite jamais le module
        self.assertIn("boîte noire", body.lower().replace("boite noire", "boîte noire"))
        self.assertIn("test_adverse.py", body)
        self.assertLess(len(body), 3500)                              # fiche courte


if __name__ == "__main__":
    unittest.main()
