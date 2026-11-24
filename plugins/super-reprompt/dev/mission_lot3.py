# -*- coding: utf-8 -*-
"""Mission reelle du lot 3 V3.1 : du cadrage a la cloture par la seule boucle manager (aucune etape manuelle cachee).
STATE + ORDRE -> mission.py ready (PLAN + SCELLE) -> next/done jusqu'a FIN, avec : une tache typee dont le plan du Relais
est produit automatiquement, un crash simule apres le recu puis reprise, un echec puis nouvelle tentative reussie,
jalons Vigie, brief archiviste par phase, brief synthese a la cloture. Usage : py -3 dev/mission_lot3.py -> 0 si tout passe."""
import json
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
PY = '"%s"' % sys.executable


def run(args, cwd, env, extra=None):
    e = dict(env, **(extra or {}))
    p = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True, env=e, timeout=300)
    print("$ %s -> code %d" % (" ".join(os.path.basename(a) if a.endswith(".py") else a for a in args[:3]), p.returncode))
    for ln in (p.stdout + p.stderr).strip().splitlines()[-6:]:
        print("    " + ln[:180])
    return p


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot3 é ")
    proj = os.path.join(tmp, "projet démo")
    slug = "faq-produit"
    md = os.path.join(proj, ".super-reprompt", slug)
    os.makedirs(os.path.join(proj, "site"))
    env = dict(os.environ, SR_VAULT_PATH="", CLAUDE_PLUGIN_OPTION_VAULT_PATH="", PYTHONUTF8="1", RELAIS_HOME=os.path.join(tmp, "relais-home"))
    env.pop("SR_TEST_CRASH_AT", None)
    try:
        subprocess.run(["git", "init", "-q", proj], check=True)
        exists = PY + ' -c "import os,sys;sys.exit(0 if os.path.isfile(\'%s\') else 1)"'
        st = C.read_json(os.path.join(ROOT, "schemas", "examples", "valid", "state-minimal.json"))
        st.update(slug=slug, status="framing", seal={"perimeter": ["site"], "color": "orange"},
                  requirements=[{"id": "R1", "text": "page FAQ", "kind": "unguessable"}, {"id": "R2", "text": "resume", "kind": "guessable"}],
                  verification={"commands": [{"id": "V1", "cmd": exists % "site/faq.html", "state": "pending", "reason": None, "plan_b": "a la main"},
                                             {"id": "V2", "cmd": exists % "site/resume.txt", "state": "pending", "reason": None, "plan_b": "a la main"}],
                                "criteria": [{"id": "C1", "text": "faq et resume presents", "source": "test", "proof": "V1 V2", "passes": False, "unsourced": False}]},
                  tasks=[{"id": "T1", "title": "Ecrire la FAQ", "covers": ["R1"], "files": ["site/*"], "mecanique": True, "preuve": "V1", "phase": "P1"},
                         {"id": "T2", "title": "Resumer la FAQ", "deps": ["T1"], "covers": ["R2"], "files": ["site/*"], "type": "resume",
                          "volume_tokens": 60000, "preuve": "V2", "phase": "P1"},
                         {"id": "T3", "title": "Controle final", "deps": ["T2"], "covers": ["C1"], "mecanique": True,
                          "preuve": exists % "site/faq.html" + " && " + exists % "site/resume.txt", "phase": "P2"}])
        C.atomic_write_json(os.path.join(md, "STATE.json"), st)
        C.atomic_write_text(os.path.join(md, "ORDRE.md"), "".join("## %d Section\ntexte\n" % i for i in range(1, 12)))
        rep = os.path.join(tmp, "r.txt")
        C.atomic_write_text(rep, "statut: OK\npreuve: commande\nfichiers: site/\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")
        M = os.path.join(S, "manager.py")
        base = ["--project", proj, "--slug", slug]

        r = run([os.path.join(S, "mission.py"), "ready", slug, "--project", proj], proj, env)
        check("cadrage -> ready : PLAN compile et scelle", r.returncode == 0 and os.path.isfile(os.path.join(md, "SCELLE.json")))

        r = run([M, "next"] + base, proj, env)
        check("next : T1 dispatchee (running)", r.returncode == 0 and C.read_json(os.path.join(md, "PLAN.json"))["tasks"][0]["status"] == "running")
        C.atomic_write_text(os.path.join(proj, "site", "faq.html"), "<h1>FAQ</h1>\n")
        r = run([M, "done", "T1", "--report", rep, "--tokens", "900"] + base, proj, env, {"SR_TEST_CRASH_AT": "after_receipt"})
        check("crash simule apres le recu (code 9)", r.returncode == 9)
        r = run([M, "status"] + base, proj, env)
        check("status explique la reprise", "reprise T1" in r.stdout)
        r = run([M, "done", "T1", "--report", rep, "--tokens", "900"] + base, proj, env)
        check("reprise : T1 done sans rejouer la preuve", r.returncode == 0 and "reprise" in r.stdout)

        r = run([M, "next"] + base, proj, env)
        check("next : plan du Relais produit et transmis automatiquement pour T2 (tache typee)",
              r.returncode == 0 and "plan du Relais produit automatiquement" in r.stdout and os.path.isfile(os.path.join(md, "relais.json")))
        r = run([M, "done", "T2", "--report", rep, "--tokens", "4000"] + base, proj, env)
        check("T2 echoue (resume absent) : failed", r.returncode == 1)
        r = run([M, "next"] + base, proj, env)
        check("next : nouvelle tentative bornee de T2", "nouvelle tentative 2/2" in r.stdout)
        C.atomic_write_text(os.path.join(proj, "site", "resume.txt"), "FAQ en une ligne.\n")
        r = run([M, "done", "T2", "--report", rep, "--tokens", "3000"] + base, proj, env)
        check("T2 reussit a la 2e tentative ; fin de phase P1 -> sr-archiviste", r.returncode == 0 and "sr-archiviste" in r.stdout)
        r = run([M, "next"] + base, proj, env)
        r = run([M, "done", "T3", "--report", rep, "--tokens", "200"] + base, proj, env)
        check("T3 done ; cloture -> sr-synthese", r.returncode == 0 and "sr-synthese" in r.stdout)
        r = run([M, "next"] + base, proj, env)
        check("FIN : plus rien a lancer", "FIN" in r.stdout)

        evs = C.read_events(md)
        ty = [e["event_type"] for e in evs]
        print("evenements :", ", ".join(ty))
        check("jalons Vigie 25/50/75/100 declenches (chacun une fois)",
              sorted(e["payload"]["milestone"] for e in evs if e["event_type"] == "vigie.milestone") == [25, 50, 75, 100])
        check("aucun doublon : 1 task.done par tache, depense une fois par run",
              ty.count("task.done") == 3 and len([l for l in open(os.path.join(md, "econ.ndjson"), encoding="utf-8") if l.strip()]) == 4)
        rc = sorted(os.path.relpath(os.path.join(dp, f), md).replace(os.sep, "/") for dp, _, fs in os.walk(os.path.join(md, "receipts")) for f in fs)
        print("recus :", rc)
        check("recus conserves, valides (dont l'echec T2-a1)", rc == ["receipts/T1/T1-a1.json", "receipts/T2/T2-a1.json", "receipts/T2/T2-a2.json", "receipts/T3/T3-a1.json"]
              and all(not C.validate("receipt", C.read_json(os.path.join(md, x))) for x in rc))
        check("memoire : 2 briefs archiviste (P1, P2) + 1 synthese", ty.count("memory.archive_requested") == 2 and ty.count("memory.synthesis_requested") == 1)
        check("tous les evenements valident le contrat", all(not C.validate("event", e) for e in evs))
        check("aucun artefact orphelin : tout recu reference par le plan",
              {t.get("receipt") for t in C.read_json(os.path.join(md, "PLAN.json"))["tasks"]} == {"T1-a1", "T2-a2", "T3-a1"})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
