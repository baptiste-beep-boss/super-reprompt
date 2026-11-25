# -*- coding: utf-8 -*-
"""Mission reelle du lot 7 V3.1 : memoire alimentee a la cloture et relue a la reprise.
Vault jetable contenant un AUTRE projet ; mission en 2 phases conduite par la boucle ; decisions et lecons journalisees
par vault.py log (dont une qui ressemble a un secret) ; fin de phase -> rangement par script ; cloture -> REPRISE.md ;
reprise dans une nouvelle invocation (manager status) ; etancheite ; mode degrade sans vault ; A10 : index + recherche
mesures sur ce vault. Usage : py -3 dev/mission_lot7.py -> 0 si tout passe."""
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")
sys.path.insert(0, S)
import contracts as C  # noqa: E402

OK = []


def run(args, cwd, env, quiet=False):
    p = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True, env=env, timeout=300)
    if not quiet:
        print("$ %s -> code %d" % (" ".join(os.path.basename(a) if a.endswith(".py") else a for a in args[:3]), p.returncode))
        for ln in (p.stdout + p.stderr).strip().splitlines()[-4:]:
            print("    " + ln[:180])
    return p


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot7 é ")
    proj = os.path.join(tmp, "projet démo")
    vault = os.path.join(tmp, "vault")
    slug = "migration-base"
    md = os.path.join(proj, ".super-reprompt", slug)
    os.makedirs(os.path.join(proj, "db"))
    os.makedirs(os.path.join(vault, "projets", "client-b"))
    other = os.path.join(vault, "projets", "client-b", "client-b-decisions.md")
    C.atomic_write_text(other, "# client-b\n- 2026-11-02 · PRIX-SECRET-CLIENT-B remise 40 %\n")
    for i in range(40):                                       # a vault of some size for A10
        C.atomic_write_text(os.path.join(vault, "notes", "note-%02d.md" % i), "# Note %d\nindexation incrementale sqlite fts5 recherche %d\n" % (i, i))
    env = dict(os.environ, SR_VAULT_PATH=vault, SR_VAULT_DB=os.path.join(tmp, "idx", "v.sqlite"), PYTHONUTF8="1")
    try:
        subprocess.run(["git", "init", "-q", proj], check=True)
        ok = '"%s" -c "print(1)"' % sys.executable
        st = C.read_json(os.path.join(ROOT, "schemas", "examples", "valid", "state-minimal.json"))
        st.update(slug=slug, status="framing", seal={"perimeter": ["db"]},
                  requirements=[{"id": "R1", "text": "schema migre", "kind": "unguessable"}, {"id": "R2", "text": "donnees verifiees", "kind": "guessable"}],
                  verification={"commands": [{"id": "V1", "cmd": ok, "state": "pending", "reason": None, "plan_b": "a la main"}],
                                "criteria": [{"id": "C1", "text": "migration verifiee", "source": "test", "proof": "V1", "passes": False, "unsourced": False}]},
                  tasks=[{"id": "T1", "title": "Migrer le schema", "covers": ["R1"], "mecanique": True, "preuve": "V1", "phase": "P1"},
                         {"id": "T2", "title": "Verifier les donnees", "deps": ["T1"], "covers": ["R2", "C1"], "mecanique": True, "preuve": "V1", "phase": "P2"}])
        C.atomic_write_json(os.path.join(md, "STATE.json"), st)
        C.atomic_write_text(os.path.join(md, "ORDRE.md"), "".join("## %d Section\ntexte\n" % i for i in range(1, 12)))
        rep = os.path.join(tmp, "r.txt")
        C.atomic_write_text(rep, "statut: OK\npreuve: V1\nfichiers: db/\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")
        M, base, VP = os.path.join(S, "manager.py"), ["--project", proj, "--slug", slug], os.path.join(S, "vault.py")

        check("ready", run([os.path.join(S, "mission.py"), "ready", slug, "--project", proj], proj, env).returncode == 0)
        run([M, "next"] + base, proj, env)
        run([VP, "log", slug, "--kind", "decision", "migrer", "par", "lots", "de", "10", "000", "lignes"], proj, env)
        run([VP, "log", slug, "--kind", "lecon", "verifier", "les", "index", "avant", "la", "bascule"], proj, env)
        r = run([VP, "log", slug, "--kind", "decision", "jeton", "ghp_" + "a" * 36], proj, env)
        check("vault.py log refuse une decision qui ressemble a un secret", r.returncode == 2)
        r = run([M, "done", "T1", "--report", rep, "--tokens", "1000"] + base, proj, env)
        check("fin de phase P1 : memoire rangee par script (1 decision, 1 lecon)", "memoire rangee par script (1 decision(s), 1 lecon(s)" in r.stdout)
        run([M, "next"] + base, proj, env)
        run([VP, "log", slug, "--kind", "decision", "migrer", "par", "lots", "de", "10", "000", "lignes"], proj, env)   # same decision again
        r = run([M, "done", "T2", "--report", rep, "--tokens", "800"] + base, proj, env)
        check("cloture : REPRISE.md ecrit et brief de synthese", r.returncode == 0 and os.path.isfile(os.path.join(md, "REPRISE.md")) and "sr-synthese" in r.stdout)
        dec = open(os.path.join(vault, "projets", slug, slug + "-decisions.md"), encoding="utf-8").read()
        check("decision repetee ecrite une seule fois dans le vault", dec.count("migrer par lots de 10 000 lignes") == 1)
        r = run([M, "status"] + base, proj, env)
        check("reprise (nouvelle invocation) : status relit REPRISE.md", "--- REPRISE.md" in r.stdout and "migrer par lots" in r.stdout)
        rp = open(os.path.join(md, "REPRISE.md"), encoding="utf-8").read()
        print("  REPRISE.md : %d caracteres (~%d tokens)" % (len(rp), len(rp) / 3.7))
        check("brief de reprise compact (< 1 200 tokens)", len(rp) / 3.7 < 1200)
        check("etancheite : rien du projet client-b dans la reprise ni dans les notes du projet",
              "PRIX-SECRET" not in rp and "PRIX-SECRET" not in dec and open(other, encoding="utf-8").read().count("PRIX-SECRET") == 1)
        check("aucun secret dans le vault du projet", "ghp_" not in "".join(open(os.path.join(dp, f), encoding="utf-8").read()
                                                                        for dp, _, fs in os.walk(os.path.join(vault, "projets", slug)) for f in fs))
        loc = dict(env, SR_VAULT_PATH="")
        r = run([os.path.join(S, "memoire.py"), "archive", md, slug], proj, loc)
        check("mode degrade sans vault, dit tel quel", "local (aucun vault configure)" in r.stdout and os.path.isdir(os.path.join(md, "memoire")))

        r = run([VP, "index", "--full"], proj, env)
        check("A10 index du vault construit (hors du vault)", r.returncode == 0 and not os.path.exists(os.path.join(vault, "v.sqlite")))
        ms = []
        for _ in range(7):
            t = time.perf_counter()
            p = subprocess.run([sys.executable, "-I", "-S", VP, "search", "indexation sqlite"], cwd=proj, env=env, capture_output=True, text=True)
            ms.append((time.perf_counter() - t) * 1000)
        fl = []
        for _ in range(7):
            t = time.perf_counter()
            subprocess.run([sys.executable, "-I", "-S", "-c", "pass"], capture_output=True)
            fl.append((time.perf_counter() - t) * 1000)
        med, flo = statistics.median(ms), statistics.median(fl)
        print("  A10 recherche a froid (-I -S), 7 essais : mediane %.0f ms (min %.0f, max %.0f) ; plancher interpreteur %.0f ms ; "
              "cout propre de la recherche %.0f ms ; cible 150 ms : %s ; sortie : %s"
              % (med, min(ms), max(ms), flo, med - flo, "TENUE" if med < 150 else "NON TENUE sur cette machine",
                 (p.stdout.strip().splitlines() or ["?"])[0][:60]))
        check("A10 recherche fonctionnelle (resultat attendu) et mesuree (mediane + plancher)", p.returncode == 0 and "note-" in p.stdout)
        r = run([VP, "lint", "--slug", slug], proj, env)
        check("notes du projet sans orpheline ni lien mort (vault.py lint)", r.returncode == 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
