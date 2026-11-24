# -*- coding: utf-8 -*-
"""library.py : bibliotheque de gabarits d'ordres de mission (lot L9, port generique de lib-add.ps1 / lib-search.ps1 du skill v1).
Bibliotheque standard, AUCUN reseau. Un ordre qui a marche est un GABARIT ; un ordre qui a echoue est un ANTI-GABARIT.

  library.py search --crochets "etf,allocation" [--classe CODE] [--top 3] [--all]     ne lit QUE les en-tetes, jamais les corps
  library.py add <slug> --titre T --classe C --crochets a,b,c --verdict reussi|partiel|echec --corps FICHIER [--capacites a,b]
                       [--tiers "T0=2 T1=1"] [--cout-estime-hebdo N] [--force]
  library.py mark-used <slug>                                                           incremente `reutilisations`
  library.py rebuild                                                                    regenere le tableau du hub

Dossier : --dir, sinon SUPER_REPROMPT_LIBRARY, sinon la cle `library_dir` du profil prive (<home>/profile.md). Aucun dossier par defaut :
la bibliotheque est une donnee personnelle, elle vit hors du depot. Hub : `library_hub` du profil (defaut INDEX.md) ; sa prose est
ecrite a la main, SEUL le tableau sous le marqueur est regenere. Classes : CODE ANALYSE RECHERCHE DOCUMENT INFRA DECISION.
Codes : 0 succes · 2 usage/validation · 3 aucun gabarit pertinent (cadrer depuis zero, puis capturer le resultat).
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

CLASSES = ("CODE", "ANALYSE", "RECHERCHE", "DOCUMENT", "INFRA", "DECISION")
VERDICTS = ("reussi", "partiel", "echec")
MARKER = "<!-- TABLE AUTO"


class LibError(Exception):
    pass


def front(path, max_lines=40):
    fm, inside, n = {}, False, 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            n += 1
            if n > max_lines:
                break
            line = line.rstrip("\r\n")
            if re.match(r"^---\s*$", line):
                if inside:
                    break
                inside = True
                continue
            if not inside:
                continue
            m = re.match(r"^([a-z_]+):\s*(.*)$", line)
            if m:
                k, v = m.group(1), m.group(2).strip()
                b = re.match(r"^\[(.*)\]$", v)
                fm[k] = [x.strip() for x in b.group(1).split(",") if x.strip()] if b else v
    return fm


def profile_value(key):
    p = os.path.join(str(L.home_dir()), "profile.md")
    if not os.path.isfile(p):
        return None
    for line in open(p, encoding="utf-8", errors="replace").read().split("\n---", 1)[0].split("\n"):
        m = re.match(r"^%s:\s*(.+?)\s*$" % re.escape(key), line)
        if m:
            return m.group(1).strip("\"'")
    return None


def libdir(arg=None):
    d = arg or os.environ.get("SUPER_REPROMPT_LIBRARY") or profile_value("library_dir")
    if not d:
        raise LibError("Aucun dossier de bibliotheque : --dir, SUPER_REPROMPT_LIBRARY, ou `library_dir` dans le profil prive.")
    if not os.path.isdir(d):
        raise LibError("Bibliotheque introuvable : %s" % d)
    return d


def hub_name():
    return profile_value("library_hub") or "INDEX.md"


def notes(d):
    return sorted(f for f in os.listdir(d) if re.match(r"^om-.+\.md$", f))


def rebuild(d, hub=None):
    hub = hub or hub_name()
    path = os.path.join(d, hub)
    head = []
    if os.path.isfile(path):
        for line in open(path, encoding="utf-8").read().split("\n"):
            if line.startswith(MARKER):
                break
            head.append(line)
        while head and head[-1] == "":
            head.pop()
    else:
        head = ["# Bibliotheque d'ordres de mission", ""]
    head += ["", "<!-- TABLE AUTO — regeneree par library.py, ne rien editer sous cette ligne -->", "", "## Gabarits", ""]
    ents = []
    for f in notes(d):
        fm = front(os.path.join(d, f))
        ents.append({"file": f[:-3], "slug": f[3:-3], "classe": fm.get("classe", ""), "verdict": fm.get("verdict", ""),
                     "reuse": fm.get("reutilisations", "") or "0", "croch": " · ".join(fm.get("crochets", []))})
    if not ents:
        head.append("_Bibliotheque vide. Le premier ordre de mission execute viendra ici._")
    else:
        label = {"reussi": "reussi", "partiel": "partiel", "echec": "ANTI-GABARIT"}
        head += ["| Gabarit | Classe | Verdict | Reutil. | Crochets |", "|---|---|---|---|---|"]
        for e in sorted(ents, key=lambda x: (x["verdict"], x["slug"])):
            head.append("| [[%s]] | %s | %s | %s | %s |" % (e["file"], e["classe"], label.get(e["verdict"], e["verdict"]), e["reuse"], e["croch"]))
        head += ["", "_%d gabarit(s). Tableau regenere le %s._" % (len(ents), time.strftime("%d/%m/%Y %H:%M"))]
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(head) + "\n")
    return len(ents)


def mark_used(d, slug):
    target = os.path.join(d, "om-%s.md" % slug)
    if not os.path.isfile(target):
        raise LibError("Gabarit inconnu : om-%s.md" % slug)
    lines = open(target, encoding="utf-8").read().split("\n")
    for i, ln in enumerate(lines):
        m = re.match(r"^reutilisations:\s*(\d+)\s*$", ln)
        if m:
            lines[i] = "reutilisations: %d" % (int(m.group(1)) + 1)
            break
        if i > 0 and ln.strip() == "---":
            raise LibError("Champ 'reutilisations' absent de om-%s.md" % slug)
    else:
        raise LibError("Champ 'reutilisations' absent de om-%s.md" % slug)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    rebuild(d)


def add(d, a):
    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", a.slug):
        raise LibError("Slug invalide '%s' : minuscules, chiffres et tirets seulement (kebab-case)." % a.slug)
    note = os.path.join(d, "om-%s.md" % a.slug)
    if os.path.exists(note) and not a.force:
        raise LibError("om-%s.md existe deja. Un gabarit par FORME de mission : enrichis l'existant, ou --force pour un remplacement." % a.slug)
    if not os.path.isfile(a.corps):
        raise LibError("Corps introuvable : %s" % a.corps)
    croch = [c.strip().lower() for c in a.crochets.split(",") if c.strip()]
    if len(croch) < 3:
        raise LibError("Au moins 3 crochets : c'est la cle d'appariement.")
    bad = [c for c in croch if not re.match(r"^[a-z0-9][a-z0-9-]*$", c)]
    if bad:
        raise LibError("Crochets invalides (accents ou espaces interdits, ils deviendraient introuvables) : %s" % ", ".join(bad))
    body = open(a.corps, encoding="utf-8").read()
    if not re.search(r"(?m)^##\s+Squelette", body):
        raise LibError("Section '## Squelette reutilisable' absente : sans elle il n'y a rien a recopier.")
    if not re.search(r"(?m)^##\s+R.{0,2}utiliser ce gabarit quand", body):
        raise LibError("Section '## Reutiliser ce gabarit quand...' absente : sans elle le gabarit est inappariable, donc mort.")
    caps = [c.strip() for c in (a.capacites or "").split(",") if c.strip()]
    hub = hub_name()
    stem = hub[:-3] if hub.endswith(".md") else hub
    fm = ["---", "type: reference", "created: %s" % time.strftime("%Y-%m-%d"), "titre: %s" % a.titre, "classe: %s" % a.classe,
          "crochets: [%s]" % ", ".join(croch), "capacites: [%s]" % ", ".join(caps), "tiers: %s" % (a.tiers or ""),
          "cout_estime_hebdo: %s" % (a.cout_estime_hebdo or ""), "cout_reel_hebdo:", "cout_reel_5h:", "verdict: %s" % a.verdict,
          "reutilisations: 0", "tags: [ordre-mission]", "---", ""]
    out = "\n".join(fm) + body.rstrip()
    if stem not in out:
        out += "\n\n---\nRattache a [[%s]]" % stem            # une note orpheline est un echec
    with open(note, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(out + "\n")
    rebuild(d, hub)
    return note


def search(d, want, classe=None, top=3, everything=False):
    cands = []
    for f in notes(d):
        fm = front(os.path.join(d, f))
        has = fm.get("crochets", [])
        common, partial = [], 0
        for w in want:
            if w in has:
                common.append(w)
                continue
            if any(len(h) >= 4 and (w.startswith(h) or h.startswith(w)) for h in has):
                partial += 1
        score = len(common) * 2 + partial
        if classe and fm.get("classe") == classe and (len(common) + partial) > 0:
            score += 1
        cands.append({"file": f[:-3], "path": os.path.join(d, f), "titre": fm.get("titre", ""), "classe": fm.get("classe", ""),
                      "verdict": fm.get("verdict", ""), "reuse": fm.get("reutilisations", "") or "0", "capacites": ", ".join(fm.get("capacites", [])),
                      "crochets": " · ".join(has), "communs": ", ".join(common), "score": score})
    sel = sorted(cands, key=lambda c: c["file"]) if everything else sorted([c for c in cands if c["score"] > 0], key=lambda c: -c["score"])[:top]
    return cands, sel


def run(argv):
    ap = argparse.ArgumentParser(prog="library.py", description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=None)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("search")
    s.add_argument("--crochets", default="")
    s.add_argument("--classe", choices=CLASSES)
    s.add_argument("--top", type=int, default=3)
    s.add_argument("--all", action="store_true")
    s.add_argument("--dir", default=None, dest="dir2")
    ad = sub.add_parser("add")
    ad.add_argument("slug")
    ad.add_argument("--titre", required=True)
    ad.add_argument("--classe", required=True, choices=CLASSES)
    ad.add_argument("--crochets", required=True)
    ad.add_argument("--verdict", required=True, choices=VERDICTS)
    ad.add_argument("--corps", required=True)
    ad.add_argument("--capacites", default="")
    ad.add_argument("--tiers", default="")
    ad.add_argument("--cout-estime-hebdo", default="")
    ad.add_argument("--force", action="store_true")
    ad.add_argument("--dir", default=None, dest="dir2")
    mu = sub.add_parser("mark-used")
    mu.add_argument("slug")
    mu.add_argument("--dir", default=None, dest="dir2")
    rb = sub.add_parser("rebuild")
    rb.add_argument("--dir", default=None, dest="dir2")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return (0 if e.code in (0, None) else 2), ""
    if not a.cmd:
        return 2, __doc__
    out = []
    try:
        d = libdir(getattr(a, "dir2", None) or a.dir)
        if a.cmd == "rebuild":
            out.append("Hub regenere : %d gabarit(s)." % rebuild(d))
        elif a.cmd == "mark-used":
            mark_used(d, a.slug)
            out.append("om-%s : reutilisations incremente." % a.slug)
        elif a.cmd == "add":
            out.append("Ecrit : %s" % add(d, a))
            out.append("Ne pas oublier : sauvegarder le dossier de la bibliotheque (commit si c'est un depot).")
        else:
            want = [w.strip().lower() for w in a.crochets.split(",") if w.strip()]
            if not a.all and not want:
                raise LibError("Preciser --crochets 'mot,mot' ou --all.")
            cands, sel = search(d, want, a.classe, a.top, a.all)
            if not cands:
                return 3, "Bibliotheque vide : aucun gabarit. Cadrer depuis zero, puis capturer le resultat avec `add`."
            if not sel:
                return 3, "Aucun gabarit pertinent pour : %s\n%d gabarit(s) en bibliotheque, aucun crochet commun.\nCadrer depuis zero, puis capturer le resultat." % (", ".join(want), len(cands))
            out.append("Gabarits candidats (%d sur %d) :" % (len(sel), len(cands)))
            for c in sel:
                v = {"reussi": "reussi", "partiel": "PARTIEL", "echec": "ANTI-GABARIT — lire pourquoi avant de refaire cette forme"}.get(c["verdict"], c["verdict"])
                out += ["", "  score %-3s %-9s %s" % (c["score"], c["classe"], v), "    %s" % c["titre"]]
                if c["communs"]:
                    out.append("    communs  : %s" % c["communs"])
                out.append("    crochets : %s" % c["crochets"])
                if c["capacites"]:
                    out.append("    capacites: %s" % c["capacites"])
                out += ["    reutilise: %s fois" % c["reuse"], "    corps    : %s" % c["path"]]
            out += ["", "N'ouvrir que le corps du candidat retenu. Lire sa section 'Ce qui a rate' avant de relancer la meme erreur.",
                    "Apres reutilisation : library.py mark-used <slug>"]
    except LibError as e:
        return 2, str(e)
    return 0, "\n".join(out)


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    code, text = run(argv)
    if text:
        print(text, file=sys.stdout if code in (0, 3) else sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
