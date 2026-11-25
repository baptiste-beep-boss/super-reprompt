# -*- coding: utf-8 -*-
"""Agrege le journal du banc du lot 10 (dev/a24_v31.py) en tableau Markdown reproductible : par tache et par bras,
nombre d'essais, tests caches, batterie etendue (spec, robustesse), tokens (mediane, min, max), duree, erreurs ;
puis l'ecart de tokens median de chaque bras a Claude nu, tache par tache. Aucun modele, aucun reseau.
Usage : py -3 dev/a24_v31_rapport.py <journal.jsonl>"""
import json
import statistics
import sys

ARMS = ("nu", "v25", "v31")
PROJETS = ("facile", "moyen", "difficile")


def frac(vals):
    ok = sum(int(v.split("/")[0]) for v in vals if v and "/" in v)
    tot = sum(int(v.split("/")[1]) for v in vals if v and "/" in v)
    return "%d/%d" % (ok, tot) if tot else "-"


def main(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    out = ["| Tache | Bras | Essais | Tests caches | Etendue spec | Etendue robustesse | Tokens median (min-max) | Duree mediane | Erreurs |",
           "|---|---|---|---|---|---|---|---|---|"]
    med = {}
    for p in PROJETS:
        for a in ARMS:
            rs = [r for r in rows if r["projet"] == p and r["arm"] == a]
            if not rs:
                continue
            toks = [r["tokens_total"] for r in rs]
            med[(p, a)] = statistics.median(toks)
            # final verdict (3 quiet passes, majority) when the re-judge ran; else the verdict taken during the bench
            be = [r.get("juge_final") or r.get("batterie_etendue") or {} for r in rs]
            out.append("| %s | %s | %d | %s | %s | %s | %d k (%d-%d k) | %d s | %d |" % (
                p, a, len(rs), frac([(r.get("juge_final") or {}).get("tests_caches") or r["tests_caches"] for r in rs]), frac([b.get("spec") for b in be]), frac([b.get("robustesse") for b in be]),
                med[(p, a)] / 1000, min(toks) / 1000, max(toks) / 1000, statistics.median(r["duree_s"] for r in rs), sum(1 for r in rs if r["erreur"])))
    out += ["", "| Tache | v25 vs nu (tokens medians) | v31 vs nu (tokens medians) |", "|---|---|---|"]
    for p in PROJETS:
        if (p, "nu") in med:
            cells = []
            for a in ("v25", "v31"):
                cells.append("%+.0f %%" % (100.0 * (med[(p, a)] - med[(p, "nu")]) / med[(p, "nu")]) if (p, a) in med else "-")
            out.append("| %s | %s | %s |" % (p, cells[0], cells[1]))
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
