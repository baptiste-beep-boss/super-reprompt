# -*- coding: utf-8 -*-
"""Lot L8, Equipe : econ.py (portes §9.3, budget par phase, brief §9.4, remontee) et la boucle du super-manager
(manager.py : frontiere -> econ -> brief -> preuve par script -> Vigie -> journal). Bibliotheque standard, sans reseau."""
import json
import os
import re
import subprocess
import sys
import tempfile
import shutil
import unittest

from _t import ROOT, SCRIPTS

import econ  # noqa: E402  (scripts/ is on sys.path through _t)

AGENTS = os.path.join(ROOT, "agents")


def task(tid, **kw):
    t = {"id": tid, "titre": "tache " + tid, "covers": ["R1"], "files": ["src/%s.py" % tid.lower()], "deps": [], "status": "todo",
         "volume_tokens": 10000, "domaine": "code", "preuve": [sys.executable, "-c", "print('ok')"]}
    t.update(kw)
    return t


class Models(unittest.TestCase):
    def test_ids_are_the_verified_ones(self):
        # verified with Skill(claude-api) on 2026-11-24: current generation, no date suffix
        self.assertEqual(econ.MODELS, {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"})

    def test_every_agent_card_names_its_model_and_never_inherits(self):
        allowed = set(econ.MODELS) | set(econ.MODELS.values())
        for fn in os.listdir(AGENTS):
            with open(os.path.join(AGENTS, fn), encoding="utf-8") as f:
                head = f.read().split("---", 2)[1]
            m = re.search(r"(?m)^model:\s*(\S+)", head)
            self.assertTrue(m, fn + " has no model")
            self.assertIn(m.group(1), allowed, fn)

    def test_team_cards_follow_cdc_9_1(self):
        want = {"sr-super-manager": ("claude-sonnet-5-5", "high"), "sr-conseil": ("claude-opus-5-5", "high"),
                "sr-sous-manager": ("claude-sonnet-5-5", "medium"), "sr-vigie": ("claude-haiku-5-5", "low")}
        for name, (model, effort) in want.items():
            with open(os.path.join(AGENTS, name + ".md"), encoding="utf-8") as f:
                head = f.read().split("---", 2)[1]
            fm = dict(l.split(":", 1) for l in head.strip().splitlines() if ":" in l)
            self.assertEqual(fm["model"].strip(), model, name)
            self.assertEqual(fm["effort"].strip(), effort, name)
            self.assertEqual(fm["omitClaudeMd"].strip(), "true", name)
            self.assertLessEqual(len(fm["description"]), 260, name)   # resting cost: descriptions stay short
        with open(os.path.join(AGENTS, "sr-conseil.md"), encoding="utf-8") as f:
            self.assertIn("25 lignes", f.read())
        with open(os.path.join(AGENTS, "sr-sous-manager.md"), encoding="utf-8") as f:
            body = f.read()
        self.assertIn("Agent", body.split("---", 2)[1])      # the only card below the super-manager that may launch agents


class Gates(unittest.TestCase):
    def test_order_script_relais_session_specialist(self):
        self.assertEqual(econ.decide(task("T1", mecanique=True, volume_tokens=900000))["level"], "script")
        self.assertEqual(econ.decide(task("T2", type="resume"), relais={"T2": "delegue"})["level"], "relais")
        self.assertEqual(econ.decide(task("T3", volume_tokens=29000))["level"], "session")
        self.assertEqual(econ.decide(task("T4", volume_tokens=45000))["level"], "session")        # grey zone 30-60 k: stay
        d = econ.decide(task("T5", volume_tokens=61000, model="haiku"))
        self.assertEqual((d["level"], d["model"]), ("specialiste", "claude-haiku-5-5"))
        self.assertEqual(econ.decide(task("T6", volume_tokens=500, isolement=True, model="sonnet"))["level"], "specialiste")
        self.assertEqual(econ.decide(task("T7", volume_tokens=500, regard_neuf=True, model="sonnet"))["level"], "specialiste")
        for t in (task("T8"), task("T9", volume_tokens=70000, model="sonnet")):
            self.assertTrue(econ.decide(t)["reason"])

    def test_relais_refusal_falls_through(self):
        self.assertEqual(econ.decide(task("T2", type="resume"), relais={"T2": "garde"})["level"], "session")

    def test_specialist_without_explicit_model_is_refused(self):
        with self.assertRaises(econ.EconError):
            econ.decide(task("T5", volume_tokens=90000))
        with self.assertRaises(econ.EconError):
            econ.decide(task("T5", volume_tokens=90000, model="gpt-x"))

    def test_sub_manager_gate(self):
        f = [task("A%d" % i, volume_tokens=90000, model="sonnet", domaine="back", files=["b%d.py" % i]) for i in range(3)] + \
            [task("B%d" % i, volume_tokens=90000, model="sonnet", domaine="front", files=["f%d.ts" % i]) for i in range(2)]
        g = econ.group(f)
        self.assertEqual(len(g["sous_managers"]), 2)
        for sm in g["sous_managers"]:
            self.assertLessEqual(len(sm["taches"]), 5)
        self.assertEqual(econ.group(f[:3])["sous_managers"], [])                       # one domain only
        overlap = f[:4] + [task("B9", volume_tokens=90000, model="sonnet", domaine="front", files=["b0.py"])]
        self.assertEqual(econ.group(overlap)["sous_managers"], [])                     # files not disjoint
        self.assertLessEqual(len(econ.group(f)["lancer"]), econ.MAX_PARALLEL)


class RelaisVerdict(unittest.TestCase):
    """econ reads the Relay's own verdict (`relais plan --json`) instead of recomputing its gates."""

    def test_relais_plan_json_feeds_econ(self):
        d = tempfile.mkdtemp(prefix="sr-l8-rel-")
        try:
            big = os.path.join(d, "journal.log")
            with open(big, "w", encoding="utf-8") as f:
                f.write("ligne de journal sans secret, service a repondu en 12 ms\n" * 200)
            plan = os.path.join(d, "PLAN.json")
            with open(plan, "w", encoding="utf-8") as f:
                json.dump({"tasks": [task("T1", type="resume", **{"in": big}), task("T2", type="resume", titre="revoir l'architecture", **{"in": big}),
                                     task("T3")]}, f)
            env = dict(os.environ, RELAIS_HOME=os.path.join(d, "home"), PYTHONIOENCODING="utf-8")
            p = subprocess.run([sys.executable, os.path.join(ROOT, "net", "relais.py"), "plan", plan, "--json", "--color", "orange"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=d, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr)
            v = json.loads(p.stdout.decode("utf-8"))
            self.assertEqual(v, {"T1": "delegue", "T2": "garde", "T3": "garde"})
            self.assertEqual(econ.decide(task("T1", type="resume"), v)["level"], "relais")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Frontier(unittest.TestCase):
    def test_ready_tasks_only(self):
        plan = {"tasks": [task("T1", status="done"), task("T2", deps=["T1"]), task("T3", deps=["T2"]), task("T4", status="echec")]}
        self.assertEqual([t["id"] for t in econ.frontier(plan)], ["T2"])


class Budget(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(econ.budget_status(79, 100), "ok")
        self.assertEqual(econ.budget_status(80, 100), "alerte")
        self.assertEqual(econ.budget_status(149, 100), "alerte")
        self.assertEqual(econ.budget_status(150, 100), "arret")

    def test_spend_and_bilan_by_phase_and_post(self):
        d = tempfile.mkdtemp()
        try:
            plan = {"phases": {"P1": {"budget_tokens": 1000}, "P2": {"budget_tokens": 1000}}}
            econ.spend(d, "P1", "specialiste", 600)
            econ.spend(d, "P1", "session", 250, estimated=True)
            econ.spend(d, "P2", "relais", 1600)
            b = econ.bilan(d, plan)
            self.assertEqual(b["P1"]["total"], 850)
            self.assertEqual(b["P1"]["statut"], "alerte")
            self.assertEqual(b["P2"]["statut"], "arret")
            self.assertEqual(b["P1"]["postes"], {"specialiste": 600, "session": 250})
            self.assertTrue(b["P1"]["estime"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Brief(unittest.TestCase):
    def test_brief_holds_every_field_under_600_tokens(self):
        t = task("T1", role="vendor/ecc/agents/tdd-guide.md", ecrit_code=True, model="haiku", volume_tokens=90000,
                 objectif="Ecrire slug.py qui transforme un titre en identifiant URL.")
        b = econ.brief(t, {"slug": "pilote", "interdits": ["reseau", "git push"]})
        self.assertLessEqual(econ.tokens(b), 600)
        for need in ("Objectif", "vendor/ecc/agents/tdd-guide.md", "src/t1.py", "R1", "relais plan", "ponytail", "reseau",
                     "statut", "preuve", "fichiers", "delegue/garde", "incertitudes", "suite", "1 500"):
            self.assertIn(need, b)

    def test_ponytail_only_for_code_writers(self):
        self.assertNotIn("ponytail", econ.brief(task("T2", ecrit_code=False), {"slug": "p"}).lower())

    def test_report_contract(self):
        good = "statut: OK\npreuve: py -3 -m unittest -> OK\nfichiers: src/t1.py\ndelegue/garde: garde (petit)\nincertitudes: aucune\nsuite: rien"
        self.assertEqual(econ.check_report(good), (True, []))
        ok, miss = econ.check_report("statut: OK\npreuve: x")
        self.assertFalse(ok)
        self.assertIn("suite", miss)
        self.assertFalse(econ.check_report(good + "\n" + "x" * 6000)[0])           # > 1 500 tokens


class Loop(unittest.TestCase):
    """manager.py next / done on a throwaway mission."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sr-l8-")
        self.mdir = os.path.join(self.tmp, ".super-reprompt", "pilote")
        os.makedirs(self.mdir)
        self.plan = {"slug": "pilote", "phases": {"P1": {"budget_tokens": 200000}},
                     "tasks": [task("T1", phase="P1", mecanique=True),
                               task("T2", phase="P1", deps=["T1"], volume_tokens=90000, model="haiku", ecrit_code=True,
                                    preuve=[sys.executable, "-c", "import sys; sys.exit(0)"]),
                               task("T3", phase="P1", deps=["T2"], preuve=[sys.executable, "-c", "import sys; sys.exit(1)"])]}
        self.write()
        self.env = dict(os.environ, SR_VAULT_PATH="", CLAUDE_PLUGIN_OPTION_VAULT_PATH="", PYTHONIOENCODING="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self):
        with open(os.path.join(self.mdir, "PLAN.json"), "w", encoding="utf-8") as f:
            json.dump(self.plan, f)

    def mgr(self, *a):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, "manager.py")] + list(a) + ["--project", self.tmp, "--slug", "pilote"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env, cwd=self.tmp, timeout=120)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")

    def plan_now(self):
        with open(os.path.join(self.mdir, "PLAN.json"), encoding="utf-8") as f:
            return json.load(f)

    def report(self, name):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write("statut: OK\npreuve: commande lancee\nfichiers: src/t.py\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")
        return p

    def test_full_loop(self):
        rc, so, se = self.mgr("next")
        self.assertEqual(rc, 0, so + se)
        self.assertIn("T1 script", so)
        rc, so, se = self.mgr("done", "T1", "--report", self.report("r1.txt"), "--tokens", "0")
        self.assertEqual(rc, 0, so + se)
        self.assertIn("preuve OK", so)
        rc, so, se = self.mgr("next")
        self.assertIn("T2 specialiste claude-haiku-5-5", so)
        brief = os.path.join(self.mdir, "briefs", "T2.md")
        self.assertTrue(os.path.isfile(brief))
        with open(brief, encoding="utf-8") as f:
            self.assertIn("ponytail", f.read())
        rc, so, se = self.mgr("done", "T2", "--report", self.report("r2.txt"), "--tokens", "40000")
        self.assertEqual(rc, 0, so + se)
        rc, so, se = self.mgr("done", "T3", "--report", self.report("r3.txt"), "--tokens", "1000")
        self.assertNotEqual(rc, 0)                                   # the proof command fails: the report is not believed
        self.assertIn("preuve ECHEC", so)
        st = {t["id"]: t["status"] for t in self.plan_now()["tasks"]}
        self.assertEqual(st, {"T1": "done", "T2": "done", "T3": "failed"})   # V3.1 lot 3 : statut canonique (contracts)
        with open(os.path.join(self.mdir, "events.ndjson"), encoding="utf-8") as f:
            kinds = [json.loads(l)["event_type"].split(".", 1)[1] for l in f if l.strip() and '"log.' in l]
        self.assertIn("vigie", kinds)
        self.assertGreaterEqual(kinds.count("tache"), 3)

    def test_bad_report_is_refused(self):
        bad = os.path.join(self.tmp, "bad.txt")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("tout va bien")
        rc, so, _se = self.mgr("done", "T1", "--report", bad)
        self.assertNotEqual(rc, 0)
        self.assertIn("remontee", so)
        self.assertEqual(self.plan_now()["tasks"][0]["status"], "todo")

    def test_budget_stop_blocks_next(self):
        self.plan["phases"]["P1"]["budget_tokens"] = 100
        self.write()
        self.mgr("done", "T1", "--report", self.report("r1.txt"), "--tokens", "200")
        rc, so, _se = self.mgr("next")
        self.assertNotEqual(rc, 0)
        self.assertIn("ARRET", so)


if __name__ == "__main__":
    unittest.main()
