# -*- coding: utf-8 -*-
"""Lot L3 (Memoire) : tests de scripts/vault.py sur un VAULT FACTICE en dossier temporaire.

Jamais le vrai vault. Bibliotheque standard seule, aucun reseau.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import ROOT, SCRIPTS

VAULT_PY = os.path.join(SCRIPTS, "vault.py")
AGENTS = os.path.join(ROOT, "agents")


def rd(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def hashtree(root):
    out = {}
    for r, _d, fs in os.walk(root):
        for f in fs:
            p = os.path.join(r, f)
            st = os.stat(p)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = (st.st_mtime_ns, st.st_size, hash(fh.read()))
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="srvault-")
        self.vault = os.path.join(self.tmp, "vault")
        self.cwd = os.path.join(self.tmp, "proj")
        self.db = os.path.join(self.tmp, "idx", "v.sqlite")
        for d in (self.vault, self.cwd):
            os.makedirs(d)
        self.env = dict(os.environ, SR_VAULT_PATH=self.vault, SR_VAULT_DB=self.db, PYTHONUTF8="1",
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.env.pop("CLAUDE_PLUGIN_OPTION_VAULT_PATH", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_v(self, *args, env=None, cwd=None):
        return subprocess.run([sys.executable, VAULT_PY] + list(args), capture_output=True, text=True,
                              encoding="utf-8", env=env or self.env, cwd=cwd or self.cwd, timeout=60)

    def note(self, rel, text):
        p = os.path.join(self.vault, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return p


class TestIndexSearch(Base):
    def seed(self):
        self.note("a/alpha.md", "# Alpha volatilite\nLe skew de volatilite implicite et la VRP. [[beta]] [[MOC-x]]\n")
        self.note("a/beta.md", "# Beta\nRug pull sur Solana, honeypot, liquidite retiree. [[alpha]] [[MOC-x]]\n")
        self.note("MOC-x.md", "# MOC x\n[[alpha]] [[beta]]\n")
        self.note("a/gamma.md", "# Gamma\nDecision d'allocation: rien de special ici. [[alpha]] [[MOC-x]]\n")

    def test_index_incremental(self):
        self.seed()
        r = self.run_v("index")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("4 indexees", r.stdout)
        r = self.run_v("index")
        self.assertIn("0 indexees", r.stdout)
        self.note("a/beta.md", "# Beta\nTexte modifie avec le mot unique zorglub. [[alpha]] [[MOC-x]]\n")
        r = self.run_v("index")
        self.assertIn("1 indexees", r.stdout)
        r = self.run_v("search", "zorglub")
        self.assertIn("a/beta.md", r.stdout)
        os.remove(os.path.join(self.vault, "a", "gamma.md"))
        r = self.run_v("index")
        self.assertIn("1 retirees", r.stdout)

    def test_touch_without_change_is_not_reindexed(self):
        self.seed()
        self.run_v("index")
        p = os.path.join(self.vault, "a", "beta.md")
        os.utime(p, (1_900_000_000, 1_900_000_000))
        r = self.run_v("index")
        self.assertIn("0 indexees", r.stdout)   # meme empreinte : seule la date est mise a jour

    def test_index_never_writes_in_the_vault(self):
        self.seed()
        before = hashtree(self.vault)
        self.run_v("index")
        self.run_v("search", "volatilite")
        self.assertEqual(before, hashtree(self.vault))
        self.assertTrue(os.path.exists(self.db))
        self.assertFalse(self.db.startswith(self.vault))

    def test_search_and_then_or_fallback(self):
        self.seed()
        self.run_v("index")
        r = self.run_v("search", "volatilite skew")
        self.assertEqual(r.stdout.strip().splitlines()[0].split(" | ")[0], "a/alpha.md")
        # un mot absent des notes : le repli « un des mots » doit quand meme trouver la bonne note
        r = self.run_v("search", "honeypot Solana inexistantmot")
        self.assertIn("a/beta.md", r.stdout)

    def test_accent_and_case_insensitive(self):
        self.note("x.md", "# Volatilité\nLe Skew de volatilité. [[y]] [[MOC-a]]\n")
        self.run_v("index")
        self.assertIn("x.md", self.run_v("search", "VOLATILITE").stdout)

    def test_eight_lines_and_400_tokens(self):
        for i in range(30):
            self.note("n/n%02d.md" % i, "# Note %d %s\n%s\n" % (i, "titre " * 30, "motcommun " + "remplissage " * 200))
        self.run_v("index")
        r = self.run_v("search", "motcommun")
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        self.assertEqual(len(lines), 8)
        self.assertLess(len(r.stdout) / 3.7, 400)

    def test_empty_query_and_missing_index(self):
        r = self.run_v("search", "   ")
        self.assertEqual(r.returncode, 2)
        r = self.run_v("search", "rien")
        self.assertEqual(r.returncode, 3)
        self.assertIn("index", r.stderr)

    def test_operators_are_neutralised(self):
        self.seed()
        self.run_v("index")
        r = self.run_v("search", 'alpha" OR NOT * (')
        self.assertEqual(r.returncode, 0, r.stderr)


class TestLogInitBrief(Base):
    def test_init_creates_linked_notes(self):
        r = self.run_v("init", "demo-x")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = os.path.join(self.vault, "projets", "demo-x")
        names = sorted(os.listdir(d))
        self.assertEqual(names, ["demo-x-00-tableau.md", "demo-x-decisions.md", "demo-x-journal.md", "demo-x-lecons.md"])
        for n in names:
            txt = rd(os.path.join(d, n))
            self.assertGreaterEqual(len(re.findall(r"\[\[[^\]]+\]\]", txt)), 2, n)
        self.assertTrue(os.path.exists(os.path.join(self.vault, "projets", "MOC-projets.md")))
        self.assertTrue(os.path.exists(os.path.join(self.vault, "projets", "Projets.base")))
        moc = rd(os.path.join(self.vault, "projets", "MOC-projets.md"))
        self.assertIn("[[demo-x-00-tableau]]", moc)
        self.run_v("init", "demo-x")   # idempotent
        moc2 = rd(os.path.join(self.vault, "projets", "MOC-projets.md"))
        self.assertEqual(moc2.count("[[demo-x-00-tableau]]"), 1)

    def test_bad_slug(self):
        self.assertEqual(self.run_v("init", "../evil").returncode, 2)
        self.assertEqual(self.run_v("log", "Bad Slug", "x").returncode, 2)

    def test_log_appends_ndjson_and_markdown(self):
        r = self.run_v("log", "demo-x", "--kind", "decision", "choix", "de", "FTS5")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.run_v("log", "demo-x", "deuxieme ligne")
        nd = os.path.join(self.cwd, ".super-reprompt", "demo-x", "journal.ndjson")
        rows = [json.loads(l) for l in rd(nd).splitlines()]
        self.assertEqual([x["kind"] for x in rows], ["decision", "note"])
        self.assertRegex(rows[0]["ts"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        md = rd(os.path.join(self.vault, "projets", "demo-x", "demo-x-journal.md"))
        self.assertIn("choix de FTS5", md)
        self.assertIn("deuxieme ligne", md)

    def test_log_refuses_secrets(self):
        r = self.run_v("log", "demo-x", "cle", "sk-ant-api03-" + "A" * 40)
        self.assertEqual(r.returncode, 2)
        nd = os.path.join(self.cwd, ".super-reprompt", "demo-x", "journal.ndjson")
        self.assertFalse(os.path.exists(nd))

    def test_log_is_fast(self):
        self.run_v("init", "demo-x")
        import time
        t = time.perf_counter()
        self.run_v("log", "demo-x", "x")
        self.assertLess(time.perf_counter() - t, 2.0)   # plafond large : la cible de 100 ms se mesure a part

    def test_concurrent_logs_lose_nothing(self):
        self.run_v("init", "demo-x")
        procs = [subprocess.Popen([sys.executable, VAULT_PY, "log", "demo-x", "p%d-%d" % (i, j)], env=self.env,
                                  cwd=self.cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for i in range(6) for j in range(5)]
        for p in procs:
            p.wait(timeout=120)
        nd = os.path.join(self.cwd, ".super-reprompt", "demo-x", "journal.ndjson")
        rows = [json.loads(l) for l in rd(nd).splitlines()]
        self.assertEqual(len(rows), 30)
        md = rd(os.path.join(self.vault, "projets", "demo-x", "demo-x-journal.md"))
        self.assertEqual(len([l for l in md.splitlines() if l.startswith("- 20")]), 30)

    def test_no_vault_falls_back_to_mission_memory(self):
        env = dict(self.env)
        env.pop("SR_VAULT_PATH")
        r = self.run_v("log", "demo-x", "sans vault", env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = os.path.join(self.cwd, ".super-reprompt", "demo-x", "memoire")
        self.assertTrue(os.path.exists(os.path.join(d, "demo-x-journal.md")))
        self.assertTrue(os.path.exists(os.path.join(d, "demo-x-00-tableau.md")))
        self.assertFalse(os.path.exists(os.path.join(self.cwd, "projets")))
        self.assertEqual(self.run_v("index", env=env).returncode, 0)
        self.assertIn("demo-x-journal.md", self.run_v("search", "vault", env=env).stdout)

    def test_missing_vault_path_is_an_error(self):
        env = dict(self.env, SR_VAULT_PATH=os.path.join(self.tmp, "nope"))
        self.assertEqual(self.run_v("log", "demo-x", "x", env=env).returncode, 2)

    def test_brief_is_short_and_useful(self):
        self.run_v("init", "demo-x")
        d = os.path.join(self.vault, "projets", "demo-x")
        tab = rd(os.path.join(d, "demo-x-00-tableau.md"))
        tab = tab.replace("statut: en cours", "statut: en cours\n").replace("avancement: 0", "avancement: 42")
        tab += "\n" + ("bavardage " * 2000) + "\n"
        open(os.path.join(d, "demo-x-00-tableau.md"), "w", encoding="utf-8").write(tab)
        with open(os.path.join(d, "demo-x-decisions.md"), "a", encoding="utf-8") as fh:
            for i in range(40):
                fh.write("- 2026-11-%02d · choix %d — raison %s\n" % (i % 28 + 1, i, "longue " * 80))
        for i in range(40):
            self.run_v("log", "demo-x", "ligne %d %s" % (i, "texte " * 40))
        r = self.run_v("brief", "demo-x")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertLess(len(r.stdout) / 3.7, 800)
        self.assertIn("avancement: 42", r.stdout)
        self.assertIn("choix 39", r.stdout)
        self.assertIn("ligne 39", r.stdout)
        self.assertNotIn("bavardage", r.stdout)

    def test_brief_unknown_project(self):
        self.assertEqual(self.run_v("brief", "inconnu").returncode, 3)


class TestLint(Base):
    def test_defects_and_exit_code(self):
        self.note("MOC-a.md", "# MOC\n[[bien-lie]] [[mort]]\n")
        self.note("n/bien-lie.md", "# Bien lie\nlien vers [[MOC-a]] et [[autre]]\n")
        self.note("n/autre.md", "# Autre\nlien vers [[bien-lie]] et [[MOC-a]]\n")
        self.note("n/orpheline.md", "# Orpheline\nrien ne pointe vers moi, je vois [[bien-lie]] [[MOC-a]]\n")
        self.note("n/isolee1.md", "# Isolee\n[[autre]] [[bien-lie]]\n")
        self.note("n/dup1.md", "# Doublon\nmeme contenu exactement ici, assez long pour compter [[bien-lie]] [[MOC-a]]\n")
        self.note("m/dup2.md", "# Doublon\nmeme contenu exactement ici, assez long pour compter [[bien-lie]] [[MOC-a]]\n")
        self.note("code.md", "# Code\n```\n[[dans-un-bloc]]\n```\n`[[inline]]` [[MOC-a]] [[bien-lie]]\n")
        r = self.run_v("lint")
        self.assertEqual(r.returncode, 1)
        out = r.stdout
        self.assertRegex(out, r"orpheline \| n/orpheline.md")
        self.assertRegex(out, r"lien-mort \| MOC-a.md .*mort")
        self.assertNotIn("dans-un-bloc", out)
        self.assertNotIn("inline", out)
        self.assertRegex(out, r"sans-moc \| n/isolee1.md")
        self.assertRegex(out, r"doublon-contenu")

    def test_clean_vault_exit_zero(self):
        self.note("MOC-a.md", "# MOC\n[[a]] [[b]]\n")
        self.note("a.md", "# A\n[[b]] [[MOC-a]]\n")
        self.note("b.md", "# B\n[[a]] [[MOC-a]]\n")
        r = self.run_v("lint")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_scope_and_min_links(self):
        self.note("MOC-a.md", "# MOC\n[[a]] [[b]] [[mauvais]]\n")
        self.note("a.md", "# A\n[[b]] [[MOC-a]]\n")
        self.note("b.md", "# B\n[[a]] [[MOC-a]]\n")
        self.note("projets/p/p-00-tableau.md", "# P\n[[a]]\n")     # un seul lien, orpheline
        r = self.run_v("lint", "--slug", "p")
        self.assertEqual(r.returncode, 1)
        self.assertIn("liens<2", r.stdout)
        self.assertNotIn("mauvais", r.stdout)   # defaut hors perimetre

    def test_lot_created_notes_produce_zero_orphans(self):
        self.run_v("init", "demo-x")
        self.run_v("log", "demo-x", "une ligne")
        r = self.run_v("lint", "--slug", "demo-x")
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_lint_does_not_write(self):
        self.note("a.md", "# A\n[[b]]\n")
        before = hashtree(self.vault)
        self.run_v("lint")
        self.assertEqual(before, hashtree(self.vault))


class TestCommit(Base):
    def git(self, *a):
        return subprocess.run(["git", "-C", self.vault] + list(a), capture_output=True, text=True, encoding="utf-8", env=self.env)

    def test_commits_only_project_paths(self):
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.note("autre/travail.md", "# autre modif en cours\n")
        self.git("add", "autre/travail.md")      # deja indexe par quelqu'un d'autre
        self.note("autre/non-suivi.md", "# non suivi\n")
        self.run_v("init", "demo-x")
        self.run_v("log", "demo-x", "ligne")
        r = self.run_v("commit", "demo-x", "-m", "test")
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        files = self.git("show", "--name-only", "--pretty=format:", "HEAD").stdout.split()
        self.assertTrue(files and all(f.startswith("projets/demo-x/") for f in files), files)
        st = self.git("status", "--porcelain").stdout
        self.assertIn("autre/travail.md", st)
        self.assertIn("autre/non-suivi.md", st)
        # rien a committer la deuxieme fois
        r = self.run_v("commit", "demo-x")
        self.assertEqual(r.returncode, 0)
        self.assertIn("rien", r.stdout)

    def test_not_a_git_repo_and_no_vault(self):
        self.run_v("init", "demo-x")
        self.assertEqual(self.run_v("commit", "demo-x").returncode, 1)
        env = dict(self.env)
        env.pop("SR_VAULT_PATH")
        r = self.run_v("commit", "demo-x", env=env)
        self.assertEqual(r.returncode, 0)
        self.assertIn("pas de vault", r.stdout)

    def test_never_git_add_all(self):
        src = rd(VAULT_PY)
        self.assertNotRegex(src, r"""["']-A["']|--all|add["'],\s*["']\.["']""")
        self.assertNotIn('"push"', src)
        self.assertNotIn("'push'", src)


class TestSourceAndAgents(unittest.TestCase):
    def test_stdlib_only_no_network_no_personal_path(self):
        src = rd(VAULT_PY)
        self.assertNotRegex(src, r"(?m)^\s*(?:import|from)\s+(socket|urllib|http|requests|ssl|asyncio)\b")
        self.assertNotRegex(src, r"(?i)c:\\users|c:/users|" + "de" + "sag|claude-" + "memory")

    def fm(self, name):
        txt = rd(os.path.join(AGENTS, name))
        m = re.match(r"---\n(.*?)\n---\n", txt, re.S)
        self.assertTrue(m, name)
        return dict(l.split(":", 1) for l in m.group(1).splitlines() if ":" in l), txt

    def test_agent_cards(self):
        for name, model in (("sr-archiviste.md", "haiku"), ("sr-synthese.md", "sonnet")):
            fm, txt = self.fm(name)
            self.assertEqual(fm["model"].strip(), model)
            self.assertEqual(fm["omitClaudeMd"].strip(), "true")
            self.assertEqual([t.strip() for t in fm["tools"].split(",")], ["Read", "Write", "Edit", "Grep"])
            self.assertNotIn("Bash", fm["tools"])
            self.assertNotIn("Agent", fm["tools"])
            self.assertIn("rouge", txt.lower())
            self.assertIn("[[", txt)


if __name__ == "__main__":
    unittest.main()
