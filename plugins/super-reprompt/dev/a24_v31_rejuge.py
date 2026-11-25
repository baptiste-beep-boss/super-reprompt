# -*- coding: utf-8 -*-
"""Re-jugement final du banc du lot 10 : les tests de robustesse de la batterie etendue sont des tests de TEMPS,
sensibles a la charge de la machine (constate le 25/11/2026 : un meme livrable passe puis echoue pendant que le banc
tourne). Une fois le banc arrete, chaque livrable est re-juge 3 fois de suite et le verdict retenu par test est la
majorite (2 sur 3). Aucun modele, aucun token. Ecrit `juge_final` dans chaque ligne du journal (l'original est garde).
Usage : py -3 dev/a24_v31_rejuge.py <dossier du banc>"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import a24_v31 as B  # noqa: E402
import a24_run as R  # noqa: E402


def verdicts(work, projet, cible, test_files, src_dir):
    juge = work + "-rejuge"
    shutil.rmtree(juge, ignore_errors=True)
    shutil.copytree(work, juge, ignore=shutil.ignore_patterns(".git", "__pycache__", ".claude", ".super-reprompt"))
    for f in test_files:
        shutil.copy(os.path.join(src_dir, f), juge)
    p = subprocess.run([sys.executable, "-m", "unittest", "-v"] + [f[:-3] for f in test_files], cwd=juge,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
    out = p.stdout.decode("utf-8", "replace")
    shutil.rmtree(juge, ignore_errors=True)
    return {l.split(" ... ")[0].strip(): l.rstrip().endswith("ok") for l in out.splitlines() if " ... " in l}


def main(out_dir):
    path = os.path.join(out_dir, "journal.jsonl")
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    for r in rows:
        work = os.path.join(out_dir, "%s-%s-%d" % ("v3" if r["arm"] == "v31" else r["arm"], r["projet"], r["essai"]))
        caches = os.path.join(R.BANC, "projets", r["projet"], "caches")
        sets = [("caches", caches, [f for f in os.listdir(caches) if f.endswith(".py")])]
        if r["projet"] in B.ETENDUE:
            sets.append(("etendue", B.BATTERIE, [B.ETENDUE[r["projet"]]]))
        jf = {}
        for name, src, files in sets:
            runs = [verdicts(work, r["projet"], name, files, src) for _ in range(3)]
            names = sorted(set().union(*runs))
            maj = {n: sum(1 for x in runs if x.get(n)) >= 2 for n in names}
            unstable = [n for n in names if len({x.get(n) for x in runs}) > 1]
            if name == "caches":
                jf["tests_caches"] = "%d/%d" % (sum(maj.values()), len(maj))
            else:
                for cls in ("Spec", "Robustesse"):
                    ks = [n for n in names if (".%s." % cls) in n or ("(%s." % cls) in n or ("." + cls + ")") in n or (cls + ".") in n]
                    jf[cls.lower()] = "%d/%d" % (sum(1 for n in ks if maj[n]), len(ks))
            jf.setdefault("instables", []).extend(unstable)
        r["juge_final"] = jf
        print(r["arm"], r["projet"], r["essai"], jf)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
