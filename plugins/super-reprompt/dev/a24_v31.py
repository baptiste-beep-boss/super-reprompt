# -*- coding: utf-8 -*-
"""Banc du lot 10 V3.1 : 3 taches (facile, moyen, difficile) x 3 bras (nu, v25, v31) x n repetitions, en sessions
`claude -p` isolees (dev/a24_run.py : configuration dediee, dossier vierge, meme invite, meme modele, meme effort).
Juge OBJECTIF et aveugle (aucun modele) : tests caches + batterie etendue figee (batterie-etendue/, empreintes
verifiees), executes sur une copie du livrable hors du depot ; le juge ne voit ni le bras ni le journal.
Tokens : usage reel de la sortie JSON de `claude -p`. Chaque essai est ecrit dans journal.jsonl des qu'il finit
(reprise : un essai deja present n'est pas relance).

Usage : py -3 dev/a24_v31.py --config-dir D --out O --v25 P25 [--claude C] [--n 3] [--only arm:projet:k]
Bibliotheque standard seulement ; le reseau est celui de `claude -p`, rien d'autre."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import a24_run as R  # noqa: E402

BATTERIE = os.path.join(R.BANC, "batterie-etendue")
ETENDUE = {"moyen": "test_dedup_etendu.py", "difficile": "test_planif_etendu.py"}
ARMS = ("nu", "v25", "v31")
PROJETS = ("facile", "moyen", "difficile")


def battery_ok():
    with open(os.path.join(BATTERIE, "EMPREINTES.sha256"), encoding="utf-8") as f:
        for ln in f:
            if not ln.strip():
                continue
            h, name = ln.split()[0], ln.split()[-1].lstrip("*")
            with open(os.path.join(BATTERIE, os.path.basename(name)), "rb") as g:
                if hashlib.sha256(g.read()).hexdigest() != h:
                    return False
    return True


def extended(work, projet):
    """-> {spec: 'ok/total', robustesse: 'ok/total'} on a copy of the deliverable, or None when the task has none."""
    t = ETENDUE.get(projet)
    if not t:
        return None
    juge = work + "-etendu"
    shutil.rmtree(juge, ignore_errors=True)
    shutil.copytree(work, juge, ignore=shutil.ignore_patterns(".git", "__pycache__", ".claude", ".super-reprompt"))
    shutil.copy(os.path.join(BATTERIE, t), juge)
    p = subprocess.run([sys.executable, "-m", "unittest", "-v", t[:-3]], cwd=juge, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    out = p.stdout.decode("utf-8", "replace")
    res = {}
    for cls in ("Spec", "Robustesse"):
        lines = [l for l in out.splitlines() if " ... " in l and ("." + cls + ".") in l]
        res[cls.lower()] = "%d/%d" % (sum(1 for l in lines if l.rstrip().endswith("ok")), len(lines))
    if not any(int(v.split("/")[1]) for v in res.values()):
        res["erreur"] = out[-400:]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--v25", required=True)
    ap.add_argument("--claude", default="claude")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--only", help="arm:projet:k (mesure du cout d'un essai)")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--timeout", type=int, default=2400)
    a = ap.parse_args()
    a.claude = shutil.which(a.claude) or a.claude
    a.v3, a.dry_run = R.PLUGIN, False
    chk = subprocess.run([sys.executable, os.path.join(HERE, "a24_manifest.py"), "--check"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if chk.returncode != 0 or not battery_ok():
        sys.exit("empreintes du banc ou de la batterie etendue invalides : comparaison refusee")
    os.makedirs(a.out, exist_ok=True)
    journal = os.path.join(a.out, "journal.jsonl")
    done = set()
    if os.path.isfile(journal):
        with open(journal, encoding="utf-8") as f:
            for ln in f:
                if ln.strip():
                    r = json.loads(ln)
                    done.add((r["arm"], r["projet"], r["essai"]))
    plan = [(arm, p, k) for k in range(1, a.n + 1) for p in PROJETS for arm in ARMS]
    if a.only:
        arm, p, k = a.only.split(":")
        plan = [(arm, p, int(k))]
    for arm, p, k in plan:
        if (arm, p, k) in done:
            continue
        r = R.run_trial(a, "v3" if arm == "v31" else arm, p, k)
        r["arm"] = arm
        work = os.path.join(a.out, "%s-%s-%d" % ("v3" if arm == "v31" else arm, p, k))
        r["batterie_etendue"] = extended(work, p)
        with open(journal, "a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(json.dumps(r, ensure_ascii=False)[:500], flush=True)


if __name__ == "__main__":
    main()
