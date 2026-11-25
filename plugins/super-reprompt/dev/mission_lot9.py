# -*- coding: utf-8 -*-
"""Mission reelle du lot 9 V3.1 : la barre suit le plan. Cadrage (3 taches avec durees estimees) -> mission.py ready ->
boucle manager next / done : apres chaque commande, BAR.json (projection de PLAN.json + events.ndjson) est reecrit ;
l'avancement pondere ne bouge que sur une tache validee (jamais sur running ni sur un echec), l'ETA est revise a
partir des durees observees et sa confiance est dite. Usage : py -3 dev/mission_lot9.py -> 0 si tout passe."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")
sys.path.insert(0, S)
import contracts as C  # noqa: E402

OK = []


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot9 é ")
    proj = os.path.join(tmp, "projet démo")
    slug = "faq"
    md = os.path.join(proj, ".super-reprompt", slug)
    os.makedirs(os.path.join(proj, "site"))
    env = dict(os.environ, SR_VAULT_PATH="", CLAUDE_PLUGIN_OPTION_VAULT_PATH="", PYTHONUTF8="1")

    def run(*a):
        return subprocess.run([sys.executable] + list(a), cwd=proj, capture_output=True, text=True, env=env, timeout=300)

    def bar():
        b = C.read_json(os.path.join(md, "BAR.json"))
        print("  BAR.json : %3d %% travail (%d %% taches), %d/%d, eta %s, confiance %s" % (
            b["percent_work"], b["percent_tasks"], b["done"], b["total"], b["display"]["text"], b["eta"]["confidence"]))
        return b
    try:
        subprocess.run(["git", "init", "-q", proj], check=True)
        st = C.read_json(os.path.join(ROOT, "schemas", "examples", "valid", "state-minimal.json"))
        st.update(slug=slug, status="framing", seal={"perimeter": ["site"]},
                  requirements=[{"id": "R1", "text": "faq", "kind": "guessable"}, {"id": "R2", "text": "liens", "kind": "guessable"}],
                  tasks=[{"id": "T1", "title": "Ecrire", "covers": ["R1"], "files": ["site/*"], "mecanique": True, "preuve": "exit 0", "estimated_duration": 30},
                         {"id": "T2", "title": "Lier", "deps": ["T1"], "covers": ["R2"], "files": ["site/*"], "mecanique": True, "preuve": "exit 1", "estimated_duration": 10},
                         {"id": "T3", "title": "Verifier", "deps": ["T2"], "covers": ["C1"], "files": ["site/*"], "mecanique": True, "preuve": "exit 0", "estimated_duration": 20}])
        C.atomic_write_json(os.path.join(md, "STATE.json"), st)
        C.atomic_write_text(os.path.join(md, "ORDRE.md"), "".join("## %d Section\ntexte\n" % i for i in range(1, 12)))
        rep = os.path.join(tmp, "r.txt")
        C.atomic_write_text(rep, "statut: OK\npreuve: x\nfichiers: site/\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")
        M, base = os.path.join(S, "manager.py"), ["--project", proj, "--slug", slug]
        check("ready", run(os.path.join(S, "mission.py"), "ready", slug, "--project", proj).returncode == 0)

        run(M, "next", *base)
        b0 = bar()
        check("T1 en cours : 0 % (running ne compte pas), ETA sans historique dite faible (n = 0)",
              b0["percent_work"] == 0 and b0["running"] == ["T1"] and b0["eta"]["confidence"] == "faible (n = 0)")
        run(M, "done", "T1", "--report", rep, "--tokens", "100", *base)
        b1 = bar()
        check("T1 validee : 50 % du travail (30 sur 60 min estimees), 33 % des taches", (b1["percent_work"], b1["percent_tasks"]) == (50, 33))
        check("ETA revise a partir d'une duree observee", b1["eta"]["observed_tasks"] == 1 and "observee" in b1["eta"]["basis"])
        run(M, "next", *base)
        r = run(M, "done", "T2", "--report", rep, "--tokens", "100", *base)
        b2 = bar()
        check("T2 en echec : l'avancement ne bouge pas (pas de progression artificielle)", r.returncode == 1 and b2["percent_work"] == 50)
        C.read_json(os.path.join(md, "PLAN.json"))
        plan = C.read_json(os.path.join(md, "PLAN.json"))
        for t in plan["tasks"]:
            if t["id"] == "T2":
                t["preuve"] = "exit 0"
        C.atomic_write_json(os.path.join(md, "PLAN.json"), plan)                # correction of the proof (structure change, said)
        run(os.path.join(S, "guard.py"), "derogation", "--code", "PLAN_MODIFIE", "--by", "mission lot 9", "--reason", "preuve de T2 corrigee", *base)
        run(M, "next", *base)
        run(M, "done", "T2", "--report", rep, "--tokens", "100", *base)
        run(M, "next", *base)
        run(M, "done", "T3", "--report", rep, "--tokens", "100", *base)
        b3 = bar()
        check("fin : 100 %, 3/3, barre « termine »", b3["percent_work"] == 100 and b3["done"] == 3 and b3["display"]["text"] == "termine")
        check("precision honnete : jamais de minute exacte affichee", all(":" not in x["display"]["text"] for x in (b0, b1, b2, b3)))
        check("source canonique dite (PLAN.json + events.ndjson)", b3["source"] == "PLAN.json + events.ndjson")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
