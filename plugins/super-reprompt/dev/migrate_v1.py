# -*- coding: utf-8 -*-
"""migrate_v1.py : copie ce que le skill v1 apporte (routage, journal des budgets) vers un PROFIL PRIVE hors depot (lot L9).

Run:  py -3 dev/migrate_v1.py --v1 <dossier du skill v1> --out <dossier prive> [--lang fr] [--level pro] [--tier standard]
                              [--forbid cap1,cap2] [--library-dir D] [--library-hub FICHIER.md]

Produit dans --out (jamais dans un depot git : refuse) :
  profile.md          cles lues par le plugin (lang, level, default_tier, forbidden_capabilities, library_dir, routing, doctrines) ; <= 1000 tokens
  routing.md          copie INTEGRALE de base/routage.md du v1 (lue a la demande, jamais chargee d'office)
  budget-journal.json copie du journal des budgets du v1 (base/journal-budgets.json)

Le v1 n'est JAMAIS modifie ni archive : copie seule. Un fichier deja present dans --out n'est jamais remplace (FileExistsError).
Ce script ne contient aucune donnee personnelle : tout ce qui est personnel arrive par les arguments ou par les fichiers du v1.
"""
import argparse
import json
import os
import re
import shutil
import sys

DIV = 3.7
PROFILE_CAP = 1000          # tokens lus au plus par le plugin (phases.md, passe 4)
PROFILE_BUDGET = 900        # marge sous le plafond


def triplets(text):
    """[(declencheur, capacite, phase)] pour chaque ligne de tableau a 3 colonnes (hors entete et separateur)."""
    out = []
    rows = text.splitlines()
    for i, ln in enumerate(rows):
        if not ln.strip().startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        nxt = rows[i + 1].strip() if i + 1 < len(rows) else ""
        if len(cells) != 3 or re.match(r"^:?-{2,}", cells[0]) or re.match(r"^\|\s*:?-{2,}", nxt):     # separateur, ou entete (suivi d'un separateur)
            continue
        cap = re.sub(r"\*\*[^*]*\*\*", "", cells[1]).strip()
        out.append((cells[0].replace("**", "").strip(), cap.replace("**", "").strip(), cells[2].replace("**", "").strip()))
    return out


def _in_git(path):
    p = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(p, ".git")):
            return True
        parent = os.path.dirname(p)
        if parent == p:
            return False
        p = parent


def migrate(v1, out, lang="en", level="mixed", tier="standard", forbid=(), library_dir=None, library_hub=None):
    if not os.path.isdir(v1):
        raise FileNotFoundError(v1)
    if _in_git(out):
        raise ValueError("--out est dans un depot git : un profil prive doit rester hors depot (%s)" % out)
    os.makedirs(out, exist_ok=True)
    targets = {n: os.path.join(out, n) for n in ("profile.md", "routing.md", "budget-journal.json")}
    for n, p in targets.items():
        if os.path.exists(p):
            raise FileExistsError(p)
    rout_src = os.path.join(v1, "base", "routage.md")
    jour_src = os.path.join(v1, "base", "journal-budgets.json")
    trip = []
    if os.path.isfile(rout_src):
        text = open(rout_src, encoding="utf-8").read()
        trip = triplets(text)
        shutil.copyfile(rout_src, targets["routing.md"])
    if os.path.isfile(jour_src):
        shutil.copyfile(jour_src, targets["budget-journal.json"])
    head = ["---", "level: %s" % level, "lang: %s" % lang, "default_tier: %s" % tier]
    if forbid:
        head.append("forbidden_capabilities: [%s]" % ", ".join(forbid))
    if library_dir:
        head.append("library_dir: %s" % library_dir)
    if library_hub:
        head.append("library_hub: %s" % library_hub)
    head.append("---")
    tail = ["", "doctrines:", "  - Full routing table (every trigger -> capability -> phase): Read routing.md next to this profile, only when a trigger below is missing.",
            "  - A routing line is a capability to INVOKE in a named phase, never to merely cite. Drop it if no real call can be written."]
    lines = ["routing:"]
    used = len("\n".join(head + tail)) + 20
    kept = 0
    for t, c, p in trip:
        row = "  - [%s | %s | %s]" % (t[:70], c, p)
        if (used + len(row) + 1) / DIV > PROFILE_BUDGET:
            break
        lines.append(row)
        used += len(row) + 1
        kept += 1
    body = "\n".join(head + lines + tail) + "\n"
    with open(targets["profile.md"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    return {"triplets": len(trip), "dans_le_profil": kept, "profil_tokens": int(round(len(body) / DIV)), "out": out}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--v1", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--lang", default="en")
    ap.add_argument("--level", default="mixed", choices=("novice", "pro", "mixed"))
    ap.add_argument("--tier", default="standard", choices=("quick", "standard", "max"))
    ap.add_argument("--forbid", default="")
    ap.add_argument("--library-dir", default=None)
    ap.add_argument("--library-hub", default=None)
    a = ap.parse_args(argv)
    try:
        r = migrate(a.v1, a.out, a.lang, a.level, a.tier, [x.strip() for x in a.forbid.split(",") if x.strip()], a.library_dir, a.library_hub)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        print("refus : %s %s" % (type(e).__name__, e), file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
