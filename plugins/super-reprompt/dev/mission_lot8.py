# -*- coding: utf-8 -*-
"""Mission reelle du lot 8 V3.1 : la Vigie arrete vraiment. Cadrage scelle -> pare-feu (hook reel) refuse une ecriture
hors perimetre et une suppression recursive -> une ecriture hors perimetre passee par un autre chemin est detectee par
`post` apres l'execution -> la tache reste BLOQUEE et plus rien n'est dispatche -> derogation explicite de
l'utilisateur, journalisee -> reprise -> budget gradue. Usage : py -3 dev/mission_lot8.py -> 0 si tout passe."""
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
import econ  # noqa: E402

OK = []


def run(args, cwd, env, stdin=None):
    p = subprocess.run([sys.executable] + args, cwd=cwd, input=stdin, capture_output=True, text=True, env=env, timeout=300)
    print("$ %s -> code %d" % (" ".join(os.path.basename(a) if a.endswith(".py") else a for a in args[:3]), p.returncode))
    for ln in (p.stdout + p.stderr).strip().splitlines()[-4:]:
        print("    " + ln[:200])
    return p


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot8 é ")
    proj = os.path.join(tmp, "projet démo")
    slug = "page-tarifs"
    md = os.path.join(proj, ".super-reprompt", slug)
    os.makedirs(os.path.join(proj, "site"))
    env = dict(os.environ, SR_VAULT_PATH="", CLAUDE_PLUGIN_OPTION_VAULT_PATH="", PYTHONUTF8="1")
    henv = dict(env, TEMP=os.path.join(tmp, "t"), TMP=os.path.join(tmp, "t"), TMPDIR=os.path.join(tmp, "t"))
    try:
        subprocess.run(["git", "init", "-q", proj], check=True)
        st = C.read_json(os.path.join(ROOT, "schemas", "examples", "valid", "state-minimal.json"))
        st.update(slug=slug, status="framing", seal={"perimeter": ["site"], "budget": 50000},
                  tasks=[{"id": "T1", "title": "Page", "covers": ["R1"], "files": ["site/*"], "mecanique": True, "preuve": "exit 0"},
                         {"id": "T2", "title": "Controle", "deps": ["T1"], "covers": ["C1"], "files": ["site/*"], "mecanique": True, "preuve": "exit 0"}])
        C.atomic_write_json(os.path.join(md, "STATE.json"), st)
        C.atomic_write_text(os.path.join(md, "ORDRE.md"), "".join("## %d Section\ntexte\n" % i for i in range(1, 12)))
        rep = os.path.join(tmp, "r.txt")
        C.atomic_write_text(rep, "statut: OK\npreuve: x\nfichiers: site/\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")
        M, base = os.path.join(S, "manager.py"), ["--project", proj, "--slug", slug]
        G = os.path.join(S, "guard.py")

        check("ready (scelle, perimetre site/)", run([os.path.join(S, "mission.py"), "ready", slug, "--project", proj], proj, env).returncode == 0)
        w = json.dumps({"tool_name": "Write", "tool_input": {"file_path": os.path.join(proj, "config.ini"), "content": "x"}, "cwd": proj})
        check("A27 pare-feu : Write hors perimetre REFUSE avant l'action (code 2)", run([G], proj, henv, w).returncode == 2)
        b = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf ../"}, "cwd": proj})
        check("A27 pare-feu : suppression recursive REFUSEE (code 2)", run([G], proj, henv, b).returncode == 2)
        d = json.dumps({"tool_name": "Write", "tool_input": {"file_path": os.path.join(md, "derogations.json"), "content": "{}"}, "cwd": proj})
        check("le fichier des derogations est protege des outils (code 2)", run([G], proj, henv, d).returncode == 2)

        check("next : T1 dispatchee", run([M, "next"] + base, proj, env).returncode == 0)
        C.atomic_write_text(os.path.join(proj, "config.ini"), "ecrit par un script, hors du pare-feu\n")   # another path
        r = run([M, "done", "T1", "--report", rep, "--tokens", "2000"] + base, proj, env)
        check("post apres execution detecte l'ecriture hors perimetre : T1 BLOQUEE (code 5)",
              r.returncode == 5 and "BLOCAGE" in r.stdout and C.read_json(os.path.join(md, "PLAN.json"))["tasks"][0]["status"] == "blocked")
        r = run([M, "next"] + base, proj, env)
        check("plus aucun dispatch tant que le blocage tient (code 5)", r.returncode == 5)
        r = run([G, "derogation", "--code", "ECRITURE_HORS_PERIMETRE", "--msg", "config.ini", "--by", "utilisateur",
                 "--reason", "fichier de configuration demande en cours de mission"] + base, proj, env)
        check("derogation explicite, attribuee", r.returncode == 0)
        r = run([M, "next"] + base, proj, env)
        check("next : T1 debloquee puis redispatchee", r.returncode == 0 and "debloquee" in r.stdout)
        r = run([M, "done", "T1", "--report", rep, "--tokens", "2000"] + base, proj, env)
        check("T1 done apres derogation", r.returncode == 0)
        r = run([G, "post", "--json"] + base, proj, env)
        g = json.loads(r.stdout.strip().splitlines()[-1])["graded"]
        check("le constat reste visible, degrade en info avec sa derogation", any(x["code"] == "ECRITURE_HORS_PERIMETRE" and x["severite"] == "info" and x["derogation"] for x in g))

        econ.spend(md, "P1", "session", 40000, label="actual", source="mission lot 8")
        r = run([G, "drift", "--json"] + base, proj, env)
        g = {x["code"]: x["severite"] for x in json.loads(r.stdout.strip().splitlines()[-1])["graded"]}
        check("budget gradue : 84 % -> BUDGET_ALERTE avertissement, pas de blocage", g.get("BUDGET_ALERTE") == "avertissement" and "BUDGET_ARRET" not in g)
        econ.spend(md, "P1", "session", 40000, label="actual", source="mission lot 8")
        r = run([M, "next"] + base, proj, env)
        check("budget a 164 % : BUDGET_ARRET bloquant, dispatch arrete", r.returncode in (3, 5) and C.read_json(os.path.join(md, "PLAN.json"))["tasks"][1]["status"] != "running")
        evs = C.read_events(md)
        ty = [e["event_type"] for e in evs]
        print("evenements Vigie :", ", ".join(t for t in ty if t.startswith(("vigie.", "guard.", "budget."))))
        check("piste d'audit : guard.deny, vigie.finding, vigie.block, vigie.derogation (acteur user), vigie.unblock",
              all(x in ty for x in ("guard.deny", "vigie.finding", "vigie.block", "vigie.derogation", "vigie.unblock"))
              and next(e for e in evs if e["event_type"] == "vigie.derogation")["actor"] == "user")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
