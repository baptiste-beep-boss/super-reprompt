# -*- coding: utf-8 -*-
"""a24_manifest.py : freeze (or check) the SHA-256 of every A24 bench project file. Standard library only.

  py -3 dev/a24_manifest.py           writes evals/v3-a24/MANIFEST.json (only before the first run)
  py -3 dev/a24_manifest.py --check   exit 1 if any frozen file changed, appeared or vanished
"""
import hashlib
import json
import os
import sys
import time

BENCH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "evals", "v3-a24")


def current():
    out = {}
    for dp, _d, fs in os.walk(os.path.join(BENCH, "projets")):
        if "__pycache__" in dp:
            continue
        for fn in sorted(fs):
            p = os.path.join(dp, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, BENCH).replace("\\", "/")] = hashlib.sha256(f.read()).hexdigest()
    return dict(sorted(out.items()))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    path = os.path.join(BENCH, "MANIFEST.json")
    if "--check" in argv:
        with open(path, encoding="utf-8") as f:
            man = json.load(f)
        cur = current()
        diff = sorted(set(cur.items()) ^ set(man["fichiers"].items()))
        print("empreintes conformes (%d fichiers, figes le %s)" % (len(cur), man["fige_le"]) if not diff else
              "ECART : %s" % ", ".join(sorted({k for k, _v in diff})))
        return 0 if not diff else 1
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"fige_le": time.strftime("%Y-%m-%d"), "fichiers": current()}, f, indent=1)
        f.write("\n")
    print("MANIFEST.json ecrit (%d fichiers)" % len(current()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
