# -*- coding: utf-8 -*-
"""net/scout.py : transport reseau de l'Eclaireur (lot L7) - le SEUL endroit ou l'Eclaireur ouvre une connexion (invariant I2).
Bibliotheque standard (urllib, zipfile). Aucun hook n'appelle ce module ; il ne tourne que sur commande explicite.

  scout.py trouver <PLAN.json> [--installed DIR]...     classement par tache ; skills.sh interroge SEULEMENT sous le seuil
  scout.py quarantaine <owner/repo> <commit40> --home H  telecharge l'archive du commit fige dans H/quarantaine/, scanne, ecrit la fiche
                                                         (n'installe RIEN : l'installation passe par skillscan.py installer ... --accord)

Vie privee : la requete est `GET /api/search?q=<1 a 4 mots du vocabulaire ferme>` ; aucun en-tete d'identification, aucun cookie, aucun
corps. Les mots sont verifies ICI encore (defense en profondeur) : un mot hors vocabulaire leve ValueError avant tout envoi.
Les reponses sont des DONNEES : normalisees champ par champ, jamais interpretees comme des consignes.
Codes de sortie : 0 ok · 1 refus/defaut · 2 usage.
"""
import io
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import catalog as C  # noqa: E402
import eclaireur as E  # noqa: E402
import skillscan as S  # noqa: E402

BASE = "https://skills.sh"
GITHUB = "https://codeload.github.com"
LOCAL = ("127.0.0.1", "localhost", "[::1]")
MAX_REPONSE = 1_000_000
MAX_ARCHIVE = 5_000_000
UA = "super-reprompt-scout"


def _check_base(base):
    u = urllib.parse.urlparse(base)
    if u.scheme == "https" or (u.scheme == "http" and (u.hostname or "") in [h.strip("[]") for h in LOCAL]):
        return base.rstrip("/")
    raise ValueError("base refusee (https exige hors 127.0.0.1) : %s" % base)


def _get(url, timeout, opener=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, */*"}, method="GET")
    with (opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))).open(req, timeout=timeout) as r:
        data = r.read(MAX_ARCHIVE + 1)
    return data


def normaliser(raw):
    """Reponse skills.sh -> [{id, nom, source, installs}] ; champ par champ, types forces, noms assainis. Donnee, jamais consigne."""
    out = []
    items = raw.get("skills") if isinstance(raw, dict) else None
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        sid = it.get("skillId") if isinstance(it.get("skillId"), str) else it.get("name")
        nom = re.sub(r"[^a-z0-9._-]+", "-", str(sid or "").lower()).strip("-")[:64]
        src = re.sub(r"[^A-Za-z0-9._/-]+", "", str(it.get("source") or ""))[:100]
        try:
            inst = max(0, int(it.get("installs")))
        except (TypeError, ValueError):
            inst = 0
        if nom:
            out.append({"id": (src + "/" + nom) if src else nom, "nom": nom, "source": src, "installs": inst})
    return out


def search(kws, base=BASE, timeout=10, opener=None):
    """Recherche skills.sh. Repli par terme retire (comme vercel find) : 4 mots, puis 3, puis 2, puis 1 jusqu'a un resultat."""
    base = _check_base(base)
    if not (1 <= len(kws) <= 4) or any(k not in E.VOCAB for k in kws):
        raise ValueError("mots-cles hors vocabulaire ferme ou en nombre invalide : %r" % (kws,))
    terms = list(kws)
    while terms:
        url = base + "/api/search?" + urllib.parse.urlencode({"q": " ".join(terms)})
        try:
            raw = json.loads(_get(url, timeout, opener).decode("utf-8", "replace"))
        except (urllib.error.URLError, OSError, ValueError):
            return []
        res = normaliser(raw)
        if res:
            return res
        terms.pop()
    return []


def trouver_plan(plan, els, base=BASE, **kw):
    return E.scout_plan(plan, els, remote=lambda kws: search(kws, base), **kw)


# ----------------------------------------------------------------------------- quarantaine
def extraire_zip(data, dest):
    """Extraction sure : pas de chemin absolu ni '..', pas de lien symbolique, taille plafonnee. Retourne le dossier racine du depot."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    total = 0
    os.makedirs(dest, exist_ok=True)
    root = os.path.realpath(dest)
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if name.startswith("/") or ":" in name or ".." in name.split("/"):
            raise ValueError("chemin dangereux dans l'archive : %s" % name)
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError("lien symbolique dans l'archive : %s" % name)
        total += info.file_size
        if total > 20_000_000:
            raise ValueError("archive trop volumineuse une fois decompressee")
        target = os.path.realpath(os.path.join(dest, name))
        if not (target == root or target.startswith(root + os.sep)):
            raise ValueError("evasion de chemin : %s" % name)
        if info.is_dir():
            os.makedirs(S.lp(target), exist_ok=True)
        else:
            os.makedirs(S.lp(os.path.dirname(target)), exist_ok=True)
            with open(S.lp(target), "wb") as fh:
                fh.write(zf.read(info))
    tops = [d for d in os.listdir(dest) if os.path.isdir(os.path.join(dest, d))]
    return os.path.join(dest, tops[0]) if len(tops) == 1 else dest


def quarantaine(owner_repo, commit, home, base=GITHUB, timeout=30):
    if not re.match(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$", owner_repo or "") or any(p in (".", "..") for p in owner_repo.split("/")):
        raise ValueError("depot invalide : %r" % (owner_repo,))
    if not S.COMMIT_RX.match(commit or ""):
        raise ValueError("commit non fige (40 hexadecimaux exiges)")
    base = _check_base(base)
    data = _get("%s/%s/zip/%s" % (base, owner_repo, commit), timeout)
    if len(data) > MAX_ARCHIVE:
        raise ValueError("archive trop volumineuse (> %d octets)" % MAX_ARCHIVE)
    dest = os.path.join(home, "quarantaine", owner_repo.replace("/", "__") + "@" + commit[:12])
    if os.path.isdir(dest):
        shutil.rmtree(S.lp(dest))
    racine = extraire_zip(data, dest)
    scan = S.scan_dir(racine)
    os.makedirs(os.path.join(home, "fiches"), exist_ok=True)
    nom = owner_repo.split("/")[1].lower()
    with open(os.path.join(home, "fiches", nom + ".quarantaine.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(S.fiche(nom, owner_repo, commit, scan))
    return racine, scan


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(argv) >= 2 and argv[0] == "trouver":
        inst = [argv[i + 1] for i, a in enumerate(argv) if a == "--installed" and i + 1 < len(argv)]
        with open(argv[1], encoding="utf-8") as fh:
            plan = json.load(fh)
        for r in trouver_plan(plan, C.load_catalog(), installed_dirs=inst):
            print("%s | %s | 3e cercle %s" % (r["tache"], " ".join(r["mots_cles"]) or "-", "ouvert" if r["cercle3"] else "ferme"))
            for x in r["classement"][:3]:
                print("   %.2f c%d %s%s" % (x["score"], x["cercle"], x["id"], "  [quarantaine requise]" if x.get("quarantaine_requise") else ""))
        return 0
    if len(argv) >= 3 and argv[0] == "quarantaine":
        home = argv[argv.index("--home") + 1] if "--home" in argv else None
        if not home:
            print("--home requis")
            return 2
        try:
            racine, scan = quarantaine(argv[1], argv[2], home)
        except (ValueError, OSError, zipfile.BadZipFile) as e:
            print("refus : %s" % e)
            return 1
        print("quarantaine : %s | verdict %s | %d trouvailles" % (racine, scan["verdict"], len(scan["findings"])))
        return 0 if scan["verdict"] == "ok" else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
