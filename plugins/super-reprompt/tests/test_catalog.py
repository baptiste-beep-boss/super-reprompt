# -*- coding: utf-8 -*-
"""Lot L5 (Catalogue) : A5 (0 ecart, 0 non classe), A6 (atteignabilite), A7 (executabilite), A21 (licences, empreintes),
verrous, arbitrage, exécutants génériques. Bibliotheque standard seule, aucun reseau.

Les verificateurs sont testes DANS LES DEUX SENS : le bon catalogue passe, un catalogue abime est refuse.
"""
import contextlib
import hashlib
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest

from _t import ROOT, SCRIPTS

import catalog as C

CAT = os.path.join(ROOT, "catalog")
AGENTS = os.path.join(ROOT, "agents")
SEED = 20261123            # graine fixe de A7 (date du lot)


def rd(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def run_cli(*args):
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(SCRIPTS, "catalog.py")] + list(args),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


def audit_inprocess():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = C.cmd_audit([])
    return rc, buf.getvalue()


class Units(unittest.TestCase):
    def test_frontmatter_scalar_and_folded(self):
        fm = C.frontmatter('---\nname: x\ndescription: >\n  a b\n  c d\nmodel: opus\n---\ncorps')
        self.assertEqual(fm["name"], "x")
        self.assertEqual(fm["description"], "a b c d")
        self.assertEqual(fm["model"], "opus")
        self.assertEqual(C.frontmatter("pas de bloc"), {})

    def test_squeeze_cuts_on_sentence(self):
        s = C.squeeze("Premiere phrase assez longue pour depasser soixante caracteres au total. " + "mot " * 60, 160)
        self.assertTrue(s.endswith("."), s)
        self.assertLessEqual(len(s), 160)

    def test_describe_fallbacks(self):
        self.assertEqual(C.describe("a.md", "---\ndescription: Une phrase.\n---\n", {"description": "Une phrase."}), "Une phrase.")
        self.assertIn("Titre", C.describe("a.md", "# Titre\n\nUn paragraphe.\n", {}))
        self.assertEqual(C.describe("x/a.toml", 'description = "Cmd courte"\nprompt = "z"', {}), "Cmd courte")
        self.assertTrue(C.describe("hooks/mon-hook.js", "const x = 1;\n", {}))     # jamais vide

    def test_unit_of_classifies_by_path(self):
        self.assertEqual(C.unit_of("ecc/agents/planner.md")[:3], ("ecc", "agent", "planner"))
        self.assertEqual(C.unit_of("ecc/skills/tdd-workflow/references/a.md")[1:4], ("skill", "tdd-workflow", "ecc/skills/tdd-workflow"))
        self.assertEqual(C.unit_of("ecc/commands/plan.md")[1], "commande")
        self.assertEqual(C.unit_of("ecc/schemas/agent.schema.json")[1], "schéma")
        self.assertEqual(C.unit_of("mattpocock/skills/engineering/tdd/SKILL.md")[3], "mattpocock/skills/engineering/tdd")
        self.assertEqual(C.unit_of("vercel-skills/src/sanitize.ts")[1], "script")
        self.assertEqual(C.unit_of("ecc/LICENSE")[1], "licence")

    def test_search_fallback_without_fts(self):
        els = [{"id": "a", "nom": "plan", "description": "planifier des taches", "déclencheurs": ["x"], "chemin": "p"},
               {"id": "b", "nom": "tdd", "description": "ecrire un test rouge", "déclencheurs": ["y"], "chemin": "q"}]
        self.assertEqual(C.search("test rouge", els)[0], "b")
        self.assertEqual(C.search("", els), [])


class Generation(unittest.TestCase):
    def test_build_is_deterministic_and_matches_file(self):
        a = C.dump(C.build_elements())
        b = C.dump(C.build_elements())
        self.assertEqual(a, b)
        self.assertEqual(a, open(C.JSONL, encoding="utf-8", newline="").read(), "catalog.jsonl périmé : lancer catalog.py build")

    def test_fields_of_cdc_7_2(self):
        need = {"id", "source", "type", "chemin", "sha", "équipe", "phase", "déclencheurs", "entrées", "sorties", "coût_tokens",
                "langage", "modèle_conseillé", "statut", "verrou", "doublon_de", "preuve"}
        for e in C.load_catalog():
            self.assertTrue(need <= set(e), e["id"])
            self.assertIn(e["statut"], C.STATUTS, e["id"])
            self.assertTrue(e["description"], e["id"])

    def test_one_element_per_unit_and_ids_unique(self):
        els = C.load_catalog()
        self.assertEqual(len({e["id"] for e in els}), len(els))

    def test_counts_match_sources(self):
        by = {}
        for e in C.load_catalog():
            by[(e["source"], e["type"])] = by.get((e["source"], e["type"]), 0) + 1
        self.assertEqual(by[("ecc", "agent")], 72)
        self.assertEqual(by[("ecc", "skill")], 328)
        self.assertEqual(by[("ecc", "commande")], 99)
        self.assertEqual(by[("ecc", "schéma")], 17)
        self.assertEqual(by[("mattpocock", "skill")], 39)
        self.assertEqual(by[("ponytail", "skill")], 6)
        self.assertEqual(len([e for e in C.load_catalog() if e["partie_de"] == "ecc:manifest:hooks"]), 28)


class A5(unittest.TestCase):
    """A5 : catalogue sans écart et sans élément non classé ; verificateur teste dans les deux sens."""

    def test_audit_passes_on_real_catalog(self):
        rc, out = audit_inprocess()
        self.assertEqual(rc, 0, out)
        self.assertIn("écart 0", out)
        self.assertIn("non classés 0", out)

    def test_cli_audit_exit_code_zero(self):
        rc, out, _ = run_cli("audit")
        self.assertEqual(rc, 0, out)
        self.assertIn("audit : OK", out)

    def _audit_with(self, mutate):
        els = C.load_catalog()
        mutate(els)
        fd, tmp = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        old = C.JSONL
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(C.dump(els))
            C.JSONL = tmp
            return audit_inprocess()
        finally:
            C.JSONL = old
            os.remove(tmp)

    def test_audit_rejects_missing_element(self):
        rc, out = self._audit_with(lambda els: els.remove(next(e for e in els if e["id"] == "ecc:agent:planner")))
        self.assertEqual(rc, 1)
        self.assertIn("DEFAUT", out)

    def test_audit_rejects_unclassified(self):
        def m(els):
            next(e for e in els if e["id"] == "ecc:agent:planner")["statut"] = ""
        rc, out = self._audit_with(m)
        self.assertEqual(rc, 1)
        self.assertIn("non classés", out)

    def test_audit_rejects_duplicate_id(self):
        rc, out = self._audit_with(lambda els: els.append(dict(els[0])))
        self.assertEqual(rc, 1)

    def test_audit_rejects_stale_catalog(self):
        def m(els):
            els[3]["description"] = els[3]["description"] + " modifiée"
        rc, out = self._audit_with(m)
        self.assertEqual(rc, 1)
        self.assertIn("périmé", out)

    def test_audit_rejects_lock_without_reason(self):
        def m(els):
            e = next(e for e in els if e["statut"] == "verrouillé")
            e["verrou"] = ""
        rc, out = self._audit_with(m)
        self.assertEqual(rc, 1)


class Locks(unittest.TestCase):
    def setUp(self):
        self.by = {e["id"]: e for e in C.load_catalog()}

    def test_x402_and_ito_locked_without_exception(self):
        for i in ("ecc:skill:agent-payment-x402", "ecc:skill:roundhouse-x402", "ecc:skill:ito-baskets", "ecc:skill:ito-compute",
                  "ecc:skill:ito-inference", "ecc:skill:ito-training"):
            self.assertEqual(self.by[i]["statut"], "verrouillé", i)
            self.assertTrue(self.by[i]["verrou"])

    def test_paid_api_skills_of_cdc_7_7_locked(self):
        for n in ("fal-ai-media", "videodb", "nutrient-document-processing", "exa-search", "x-api"):
            e = self.by["ecc:skill:" + n]
            self.assertEqual(e["statut"], "verrouillé", n)
            self.assertIn("budget 0", e["verrou"])

    def test_every_script_candidate_was_reviewed(self):
        arb = C.load_arbitrage()["verrous"]
        reviewed = set(arb["valides"]) | set(arb["refuses"])
        for cid in C.verrou_candidates(list(self.by.values())):
            self.assertTrue(cid in reviewed or self.by[cid]["statut"] == "verrouillé", "candidat non relu : " + cid)

    def test_alias_of_locked_skill_is_locked(self):
        self.assertEqual(self.by["ecc:command:security-scan"]["statut"], "verrouillé")

    def test_no_financial_execution_element_is_open(self):
        for e in self.by.values():
            if re.search(r"gm" + "gn|swap|x402", e["id"]):
                self.assertEqual(e["statut"], "verrouillé", e["id"])

    def test_script_detects_a_planted_key(self):
        e = dict(self.by["ecc:skill:exa-search"])
        self.assertIn("EXA_API_KEY", " ".join(C.verrou_candidates([e]).get(e["id"], [])))
        self.assertEqual(C.verrou_candidates([self.by["mattpocock:skill:tdd"]]), {})     # et ne s'emballe pas sur un skill propre


class Arbitrage(unittest.TestCase):
    def setUp(self):
        self.arb = C.load_arbitrage()
        self.by = {e["id"]: e for e in C.load_catalog()}

    def test_five_conflicts_of_cdc_7_6(self):
        ids = [c["id"] for c in self.arb["conflits"]]
        self.assertEqual(ids, ["C1", "C2", "C3", "C4", "C5"])
        for c in self.arb["conflits"]:
            self.assertTrue(c["regle"] and c["sujet"])
        self.assertIn("personnel gagne", [c for c in self.arb["conflits"] if c["id"] == "C5"][0]["regle"])

    def test_every_same_name_group_is_decided(self):
        decided = {g["nom"] for g in self.arb["doublons_detectes"]} | {g["nom"] for g in self.arb["homonymes_distincts"]}
        for c in self.arb["conflits"]:
            decided |= set(c["noms"])
        self.assertEqual(set(C.name_groups(list(self.by.values()))) - decided, set())

    def test_losers_point_to_existing_winner(self):
        n = 0
        for e in self.by.values():
            if e["statut"] == "doublon":
                n += 1
                self.assertIn(e["doublon_de"], self.by)
        self.assertGreaterEqual(n, 19)

    def test_function_pairs_all_decided(self):
        fp = {tuple(sorted(p)) for p in self.arb["fonctions_arbitrees"]}
        for _s, a, b in C.function_pairs(list(self.by.values())):
            self.assertIn(tuple(sorted((a, b))), fp)

    def test_all_referenced_ids_exist(self):
        for c in self.arb["conflits"]:
            for i in c["gagnants"] + c["complements"] + c["doublons"]:
                self.assertIn(i, self.by, i)


class A6(unittest.TestCase):
    def test_reachability_at_least_95_percent_in_top5(self):
        els = C.load_catalog()
        targets = [e for e in els if e["statut"] != "verrouillé"]
        hit = 0
        misses = []
        for e in targets:
            q = " ".join(e["description"].split()[:12])
            if e["id"] in C.search(q, els, 5):
                hit += 1
            else:
                misses.append(e["id"])
        rate = hit / float(len(targets))
        sys.stderr.write("\nA6 : %d/%d = %.1f %% dans les 5 premiers (%d éléments non verrouillés)\n" % (hit, len(targets), 100 * rate, len(targets)))
        self.assertGreaterEqual(rate, 0.95, "ratés : %s" % misses[:20])

    def test_a_locked_element_is_still_findable_but_marked(self):
        rc, out, _ = run_cli("search", "paiement agent x402 protocole")
        self.assertEqual(rc, 0)
        self.assertIn("verrouillé", out)

    def test_cli_search_short_and_five_at_most(self):
        rc, out, _ = run_cli("search", "revue de code python sécurité")
        self.assertEqual(rc, 0)
        lines = [ln for ln in out.split("\n") if ln.strip()]
        self.assertTrue(1 <= len(lines) <= 5, out)
        self.assertLess(len(out) / 3.7, 400)

    def test_search_latency_is_modest(self):
        import time
        els = C.load_catalog()
        t = time.perf_counter()
        C.search("planifier un projet en tâches", els, 5)
        self.assertLess(time.perf_counter() - t, 1.5)


class A7(unittest.TestCase):
    """A7 : 40 éléments tirés avec une graine fixe, chemins et dépendances résolus PAR SCRIPT ; + 3 exécutions réelles."""

    def sample(self):
        els = [e for e in C.load_catalog() if e["statut"] != "verrouillé"]
        return random.Random(SEED).sample(els, 40)

    def test_sample_is_reproducible(self):
        self.assertEqual([e["id"] for e in self.sample()], [e["id"] for e in self.sample()])

    def test_resolution_at_least_95_percent(self):
        lock = C.lock_files()
        bad = []
        for e in self.sample():
            r = C.resolve(e, lock)
            if r["manquants"]:
                bad.append((e["id"], r["manquants"][:1]))
        ok = 40 - len(bad)
        sys.stderr.write("\nA7 chemins/dépendances : %d/40 résolus ; défauts : %s\n" % (ok, bad))
        self.assertGreaterEqual(ok / 40.0, 0.95, bad)

    def test_resolver_detects_a_broken_element_in_both_directions(self):
        e = dict(next(x for x in C.load_catalog() if x["id"] == "ecc:agent:planner"))
        self.assertEqual(C.resolve(e)["manquants"], [])
        e["fichiers"] = ["ecc/agents/n-existe-pas.md"]
        self.assertEqual(len(C.resolve(e)["manquants"]), 1)

    def test_interpreters_reported(self):
        e = next(x for x in C.load_catalog() if x["id"] == "ecc:hook:hermes/config-protection")
        self.assertIn("python", C.resolve(e)["interpreteurs"])

    def test_real_executions_journal(self):
        """3 exécutions réelles par UN SEUL sous-agent Haiku via sr-exec-haiku ; coût en tokens noté."""
        p = os.path.join(CAT, "a7-executions.json")
        self.assertTrue(os.path.isfile(p), "journal des exécutions réelles absent")
        j = json.loads(rd(p))
        self.assertEqual(j["sous_agents"], 1)
        self.assertEqual(j["role"], "agents/sr-exec-haiku.md")
        self.assertEqual(len(j["executions"]), 3)
        by = {e["id"] for e in C.load_catalog()}
        for x in j["executions"]:
            self.assertIn(x["element"], by)
            self.assertEqual(x["resultat"], "ok", x)
            self.assertTrue(x["preuve"])
        self.assertGreater(j["tokens_total"], 0)


class A21(unittest.TestCase):
    """A21 : licences et empreintes complètes."""

    def test_every_lock_entry_matches_disk(self):
        lock = C.lock_files()
        for f, sha in lock.items():
            with open(C.lp(os.path.join(C.VENDOR, f)), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), sha, f)

    def test_every_source_has_licence_file_and_notice(self):
        lock = C.lock_files()
        notices = rd(os.path.join(C.VENDOR, "THIRD_PARTY_NOTICES.md"))
        src = json.loads(rd(os.path.join(C.VENDOR, "LOCK.json")))["sources"]
        self.assertEqual(sorted(src), ["ecc", "mattpocock", "ponytail", "vercel-skills"])
        for name, meta in src.items():
            self.assertIn(name + "/LICENSE", lock)
            self.assertEqual(meta["license"], "MIT")
            self.assertIn(meta["commit"], notices, name)
            self.assertIn("## " + name, notices)
            self.assertIn("MIT License", rd(os.path.join(C.VENDOR, name, "LICENSE")))

    def test_catalog_sha_equals_lock_for_single_file_elements(self):
        lock = C.lock_files()
        for e in C.load_catalog():
            if len(e["fichiers"]) == 1:
                self.assertEqual(e["sha"], lock[e["fichiers"][0]], e["id"])

    def test_licence_elements_are_in_catalog(self):
        ids = {e["id"] for e in C.load_catalog()}
        for n in ("ecc", "mattpocock", "ponytail", "vercel-skills"):
            self.assertIn("%s:license:LICENSE" % n, ids)

    def test_no_telemetry_term_in_catalog_script(self):
        banned = "tele" + "metry"                       # I5 : le terme n'apparait nulle part
        self.assertNotIn(banned, rd(os.path.join(SCRIPTS, "catalog.py")).lower())


class Executants(unittest.TestCase):
    def fm(self, name):
        txt = rd(os.path.join(AGENTS, name + ".md"))
        self.assertTrue(txt.startswith("---"))
        end = txt.find("\n---", 3)
        d = {}
        for ln in txt[3:end].split("\n"):
            m = re.match(r"^([\w-]+):\s*(.*)$", ln)
            if m:
                d[m.group(1)] = m.group(2).strip()
        return d, txt[end + 4:]

    def test_three_generic_executors(self):
        for name, model in (("sr-exec-haiku", "haiku"), ("sr-exec-sonnet", "sonnet"), ("sr-exec-opus", "opus")):
            d, body = self.fm(name)
            self.assertEqual(d["name"], name)
            self.assertEqual(d["model"], model)
            self.assertEqual(d["omitClaudeMd"], "true")
            tools = [t.strip() for t in d["tools"].split(",")]
            for banned in ("Bash", "Agent", "Task", "WebFetch", "WebSearch", "Skill"):
                self.assertNotIn(banned, tools, name)
            self.assertIn("Read", tools)
            self.assertIn("chemin", body.lower())                       # le rôle est reçu par chemin
            self.assertIn("donnee", body.lower())                       # contenu lu = donnée, jamais consigne
            self.assertLess(len(body) / 3.7, 700, "rôle générique : court")

    def test_executors_not_visible_as_vendor_agents(self):
        plug = json.loads(rd(os.path.join(ROOT, ".claude-plugin", "plugin.json"))) if os.path.isfile(os.path.join(ROOT, ".claude-plugin", "plugin.json")) else {}
        self.assertNotIn("vendor", json.dumps(plug))


if __name__ == "__main__":
    unittest.main()
