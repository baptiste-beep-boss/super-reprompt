# -*- coding: utf-8 -*-
"""Mission reelle du lot 6 V3.1 : un seul budget, des couts etiquetes. Cadrage avec budget mission scelle -> taches
executees par la boucle (une avec compteur reel, une sans) -> depense de cadrage par mission.py spent -> rapport
reproductible -> decisions de routage comparatives tracees -> alerte puis arret a 150 % -> la Vigie lit le meme budget.
Usage : py -3 dev/mission_lot6.py -> 0 si tout passe."""
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


def run(args, cwd, env):
    p = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True, env=env, timeout=300)
    print("$ %s -> code %d" % (" ".join(os.path.basename(a) if a.endswith(".py") else a for a in args[:3]), p.returncode))
    for ln in (p.stdout + p.stderr).strip().splitlines()[-8:]:
        print("    " + ln[:180])
    return p


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot6 é ")
    proj = os.path.join(tmp, "projet démo")
    slug = "rapport-ventes"
    md = os.path.join(proj, ".super-reprompt", slug)
    os.makedirs(os.path.join(proj, "out"))
    env = dict(os.environ, SR_VAULT_PATH="", CLAUDE_PLUGIN_OPTION_VAULT_PATH="", PYTHONUTF8="1")
    try:
        subprocess.run(["git", "init", "-q", proj], check=True)
        ok = '"%s" -c "print(1)"' % sys.executable
        st = C.read_json(os.path.join(ROOT, "schemas", "examples", "valid", "state-minimal.json"))
        st.update(slug=slug, status="framing", seal={"perimeter": ["out"], "budget": 100000},
                  requirements=[{"id": "R1", "text": "extraction", "kind": "guessable"}, {"id": "R2", "text": "analyse", "kind": "unguessable"}],
                  verification={"commands": [{"id": "V1", "cmd": ok, "state": "pending", "reason": None, "plan_b": "a la main"}],
                                "criteria": [{"id": "C1", "text": "rapport ecrit", "source": "test", "proof": "V1", "passes": False, "unsourced": False}]},
                  tasks=[{"id": "T1", "title": "Extraire", "covers": ["R1"], "mecanique": True, "preuve": "V1", "volume_tokens": 5000},
                         {"id": "T2", "title": "Analyser", "deps": ["T1"], "covers": ["R2"], "model": "sonnet", "volume_tokens": 90000, "preuve": "V1"},
                         {"id": "T3", "title": "Rediger", "deps": ["T2"], "covers": ["C1"], "volume_tokens": 20000, "preuve": "V1"}])
        C.atomic_write_json(os.path.join(md, "STATE.json"), st)
        C.atomic_write_text(os.path.join(md, "ORDRE.md"), "".join("## %d Section\ntexte\n" % i for i in range(1, 12)))
        rep = os.path.join(tmp, "r.txt")
        C.atomic_write_text(rep, "statut: OK\npreuve: V1\nfichiers: out/\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")
        M, base = os.path.join(S, "manager.py"), ["--project", proj, "--slug", slug]

        check("ready (budget mission 100 000 scelle)", run([os.path.join(S, "mission.py"), "ready", slug, "--project", proj], proj, env).returncode == 0
              and C.read_json(os.path.join(md, "SCELLE.json"))["budget"]["max_tokens"] == 100000)
        check("cadrage compte dans le meme journal (mission.py spent 30 k, estimated)",
              run([os.path.join(S, "mission.py"), "spent", slug, "30", "--project", proj], proj, env).returncode == 0)
        run([M, "next"] + base, proj, env)
        check("T1 done sans compteur -> unavailable (jamais invente)", run([M, "done", "T1", "--report", rep] + base, proj, env).returncode == 0)
        r = run([M, "next"] + base, proj, env)
        check("T2 specialiste ; next trace la decision", "T2 specialiste" in r.stdout)
        check("T2 done avec compteur reel 52 000 -> actual", run([M, "done", "T2", "--report", rep, "--tokens", "52000"] + base, proj, env).returncode == 0)
        r = run([M, "next"] + base, proj, env)
        check("alerte budget mission a 80 % (82 000 / 100 000)", "ALERTE budget mission" in r.stdout)
        r = run([os.path.join(S, "econ.py"), "rapport", md], proj, env)
        check("rapport : actual et estimated separes, jamais additionnes sans le dire",
              "actual 52000 | estimated 30000" in r.stdout and "deux grandeurs de nature differente" in r.stdout)
        j1 = json.loads(run([os.path.join(S, "econ.py"), "rapport", md, "--json"], proj, env).stdout)
        j2 = json.loads(run([os.path.join(S, "econ.py"), "rapport", md, "--json"], proj, env).stdout)
        j1.pop("genere_le"), j2.pop("genere_le")
        check("rapport reproductible (deux passages identiques)", j1 == j2 and j1["unavailable"] == 1 and j1["projected"] == 20000)
        evs = [e for e in C.read_events(md) if e["event_type"] == "routing.decision"]
        for e in evs:
            print("  routage %s -> %s : %s" % (e["payload"]["task"], e["payload"]["choix"],
                                              "; ".join("%s %s/%s" % (o["level"], o["tokens_contexte_principal"], o["tokens_total"]) for o in e["payload"]["alternatives"])))
        check("3 decisions de routage, 4 options chacune, estimees avec confiance et source",
              len(evs) == 3 and all(len(e["payload"]["alternatives"]) == 4 and all(o["label"] == "estimated" and o["confiance"] for o in e["payload"]["alternatives"]) for e in evs))
        rows = [json.loads(l) for l in open(os.path.join(md, "econ.ndjson"), encoding="utf-8") if l.strip()]
        check("journal econ etiquete : estimated, unavailable, actual", [r["label"] for r in rows] == ["estimated", "unavailable", "actual"])
        run([M, "done", "T3", "--report", rep, "--tokens", "70000"] + base, proj, env)
        r = run([M, "next"] + base, proj, env)
        check("arret a 150 % (152 000 / 100 000) : code 3 et question", r.returncode == 3 and "ARRET budget mission" in r.stdout)
        r = run([os.path.join(S, "guard.py"), "drift"] + base, proj, env)
        check("la Vigie lit le meme budget (PROGRESS.json projete) : BUDGET_DEPASSE", "BUDGET_DEPASSE 152000 > 100000" in r.stdout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
