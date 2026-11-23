# -*- coding: utf-8 -*-
"""skillscan.py : chaine « skill tiers » du lot L7 (Eclaireur). Bibliotheque standard, AUCUN reseau (le telechargement vit dans net/scout.py).

  skillscan.py scan <dossier>                           scan en quarantaine ; code 1 si verdict « arret »
  skillscan.py fiche <nom> <source> <commit> <dossier>  fiche Markdown (resultat du scan + demande d'accord)
  skillscan.py installer <nom> <dossier> <source> <commit40> --home H --target T --accord
  skillscan.py retirer <nom> --home H --target T        retrait en UNE commande (dossier + verrou)
  skillscan.py verifier --home H --target T             derive : skill installe different de son empreinte verrouillee

Principes : le contenu d'un skill est une DONNEE, jamais executee ni suivie. Le scan cherche : consignes cachees, unicode invisible,
reseau, shell, secrets, licence, taille. Une trouvaille « bloquante » arrete l'installation MEME avec accord ; une « avertissement »
va dans la fiche. Installer exige un accord explicite (`accord=True`) ET un commit fige de 40 hex. L'original en quarantaine n'est
jamais modifie. Codes de sortie : 0 ok · 1 arret/defaut · 2 usage.
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time

MAX_FICHIERS = 80
MAX_FICHIER = 150_000
MAX_TOTAL = 600_000
COMMIT_RX = re.compile(r"^[0-9a-f]{40}$")
NOM_RX = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


class AccordRequis(Exception):
    pass


class ScanBloquant(Exception):
    pass


# ----------------------------------------------------------------------------- motifs
INVISIBLES = re.compile("[​‌‎‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
CONSIGNES = [re.compile(p, re.I) for p in (
    r"ignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above|earlier)\s+(?:instructions|rules|prompts?)",
    r"disregard\s+(?:your|the|all)\s+(?:system\s+prompt|instructions|rules|guidelines)",
    r"(?:never|do\s+not|don'?t)\s+(?:tell|inform|mention\s+(?:this\s+)?to|let)\s+the\s+user",
    r"dangerously-skip-permissions",
    r"disable\s+(?:the\s+|all\s+)?(?:safety\s+|security\s+)?(?:hooks?|guardrails?|permissions?)",
    r"you\s+are\s+now\s+(?:in\s+)?(?:dan|developer)\s+mode",
    r"bypass\s+(?:the\s+)?(?:permission|safety|guard|sandbox)")]
COMMENT_RX = re.compile(r"<!--(.*?)-->", re.S)
COMMENT_IMP = re.compile(r"\b(ignore|disregard|send|upload|exfiltrate|execute|run|curl|wget|delete|override|forget)\b", re.I)
SECRETS = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[bp]-[A-Za-z0-9-]{10,}"
                     r"|AIza[0-9A-Za-z_-]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY)")
SENSIBLE = re.compile(r"(\.ssh[/\\]|id_rsa|id_ed25519|\.aws[/\\]credentials|\.gnupg|\.npmrc|\.netrc|Login Data|Cookies\b|wallet\.dat|\.kube[/\\]config)", re.I)
PIPE_SHELL = re.compile(r"\b(?:curl|wget|iwr|Invoke-WebRequest|Invoke-RestMethod|irm)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b|\|\s*(?:iex|Invoke-Expression)\b", re.I)
DOWNLOAD = re.compile(r"\b(?:curl|wget|Invoke-WebRequest|iwr|certutil\s+-urlcache|bitsadmin)\b", re.I)
EXEC_AFTER = re.compile(r"(Start-Process|\biex\b|Invoke-Expression|chmod\s+\+x|\bsource\s+\S+|\bbash\s+\S+\.sh|\.\\\S+\.exe)", re.I)
IP_URL = re.compile(r"https?://\d{1,3}(?:\.\d{1,3}){3}")
NET_CODE = re.compile(r"\b(?:requests\.|urllib|http\.client|socket\.|fetch\(|XMLHttpRequest|axios|Invoke-WebRequest|curl\b|wget\b)", re.I)
SHELL_BLOQ = [re.compile(p, re.I) for p in (
    r"base64\s+(?:-d|--decode)[^\n]*\|\s*(?:ba|z)?sh\b", r"(?:powershell|pwsh)[^\n]*\s-(?:enc|encodedcommand)\b",
    r"\brm\s+-[a-z]*r[a-z]*f[a-z]*\s+(?:/|~|\$HOME|\.\.|\*)", r"\brm\s+-[a-z]*f[a-z]*r[a-z]*\s+(?:/|~|\$HOME|\.\.|\*)",
    r"\beval\s+[\"'`]?\$\(", r"\bnc\s+-e\b|\bmkfifo\b[^\n]*\bnc\b", r":\(\)\s*\{\s*:\|:", r"chmod\s+-?R?\s*777\s+/")]
SHELL_AVERT = [re.compile(p, re.I) for p in (r"\bsudo\b", r"\bgit\s+push\b", r"\brm\s+-[a-z]*r", r"\beval\b", r"\bchmod\b", r"Remove-Item[^\n]*-Recurse")]
PERMISSIVE = re.compile(r"\b(MIT|Apache[- ]?(?:License)?[- ]?2|BSD|ISC|Unlicense|CC0|0BSD)\b|Permission is hereby granted", re.I)
COPYLEFT = re.compile(r"\b(A?L?GPL|GNU (?:Lesser |Affero )?General Public)", re.I)
TEXTE_EXT = (".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".rst", "")
CODE_EXT = (".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".py", ".js", ".mjs", ".ts", ".rb", ".pl", ".php")


def lp(path):
    path = os.path.abspath(path)
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + path
    return path


def _walk(root):
    out = []
    for dp, dn, fn in os.walk(lp(root)):
        dn[:] = [d for d in dn if d != ".git"]
        for f in sorted(fn):
            full = os.path.join(dp, f)
            out.append((os.path.relpath(full, lp(root)).replace("\\", "/"), full))
    return sorted(out)


def tree_sha(root):
    h = hashlib.sha256()
    for rel, full in _walk(root):
        with open(full, "rb") as fh:
            h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(fh.read()).digest())
    return h.hexdigest()


def _f(cat, gravite, fichier, detail):
    return {"cat": cat, "gravite": gravite, "fichier": fichier, "detail": detail}


def _licence(files, texts, license_hint):
    blob = "\n".join(t for rel, t in texts if re.match(r"(?i)(licen[sc]e|copying)", os.path.basename(rel)))
    fm = ""
    sk = dict(texts).get("SKILL.md", "")
    m = re.search(r"(?mi)^license:\s*(.+)$", sk[:2000]) if sk.startswith("---") else None
    if m:
        fm = m.group(1)
    for src in (blob, fm, license_hint or ""):
        if src and PERMISSIVE.search(src):
            return None
    for src in (blob, fm, license_hint or ""):
        if src and COPYLEFT.search(src):
            return _f("licence", "avertissement", "", "licence copyleft : a relire avant reutilisation")
    return _f("licence", "bloquant", "", "licence absente ou non permissive")


def scan_dir(path, license_hint=None):
    """Scan lecture seule. Retourne {"verdict": "ok"|"arret", "findings": [...], "fichiers": n, "octets": n}."""
    findings, texts, total = [], [], 0
    files = _walk(path)
    if len(files) > MAX_FICHIERS:
        findings.append(_f("taille", "bloquant", "", "%d fichiers (> %d)" % (len(files), MAX_FICHIERS)))
    for rel, full in files:
        if os.path.islink(full):
            findings.append(_f("lien", "bloquant", rel, "lien symbolique (lecture hors du skill)"))
            continue
        size = os.path.getsize(full)
        total += size
        if size > MAX_FICHIER:
            findings.append(_f("taille", "bloquant", rel, "%d octets (> %d)" % (size, MAX_FICHIER)))
            continue
        with open(full, "rb") as fh:
            raw = fh.read()
        if b"\0" in raw[:2048]:
            findings.append(_f("taille", "avertissement", rel, "fichier binaire non analysable"))
            continue
        texts.append((rel, raw.decode("utf-8", "replace")))
    if total > MAX_TOTAL:
        findings.append(_f("taille", "bloquant", "", "%d octets au total (> %d)" % (total, MAX_TOTAL)))
    for rel, t in texts:
        ext = os.path.splitext(rel)[1].lower()
        code = ext in CODE_EXT
        body = t[1:] if t.startswith("﻿") else t
        for m in INVISIBLES.finditer(body):
            ch = m.group(0)
            if ch == "‍":
                continue
            findings.append(_f("unicode_invisible", "bloquant", rel, "caractere invisible U+%04X" % ord(ch)))
            break
        clean = INVISIBLES.sub("", body)
        for rx in CONSIGNES:
            m = rx.search(clean)
            if m:
                findings.append(_f("consignes_cachees", "bloquant", rel, "consigne suspecte : " + m.group(0)[:60]))
        for m in COMMENT_RX.finditer(clean):
            if COMMENT_IMP.search(m.group(1)):
                findings.append(_f("consignes_cachees", "bloquant", rel, "commentaire cache avec imperatif : " + m.group(1).strip()[:60]))
        for m in SECRETS.finditer(body):
            findings.append(_f("secrets", "bloquant", rel, "motif de secret : " + m.group(0)[:6] + "…"))
            break
        if SENSIBLE.search(body):
            findings.append(_f("secrets", "bloquant" if code else "avertissement", rel, "chemin sensible reference"))
        if PIPE_SHELL.search(clean):
            findings.append(_f("reseau", "bloquant", rel, "telechargement redirige vers un interprete"))
        elif DOWNLOAD.search(clean) and EXEC_AFTER.search(clean) and (code or IP_URL.search(clean)):
            findings.append(_f("reseau", "bloquant", rel, "telechargement suivi d'une execution"))
        elif IP_URL.search(clean):
            findings.append(_f("reseau", "avertissement", rel, "URL vers une adresse IP"))
        elif code and NET_CODE.search(clean):
            findings.append(_f("reseau", "avertissement", rel, "appel reseau dans un script"))
        for rx in SHELL_BLOQ:
            m = rx.search(clean)
            if m:
                findings.append(_f("shell", "bloquant", rel, "commande dangereuse : " + m.group(0)[:50]))
        if code:
            for rx in SHELL_AVERT:
                if rx.search(clean):
                    findings.append(_f("shell", "avertissement", rel, "commande sensible : " + rx.pattern[:24]))
                    break
    lic = _licence(files, texts, license_hint)
    if lic:
        findings.append(lic)
    verdict = "arret" if any(x["gravite"] == "bloquant" for x in findings) else "ok"
    return {"verdict": verdict, "findings": findings, "fichiers": len(files), "octets": total}


# ----------------------------------------------------------------------------- fiche, verrou, installation
def fiche(nom, source, commit, scan, note=None):
    L = ["# Fiche skill tiers : %s" % nom, "", "- source : %s" % source, "- commit fige : %s" % commit,
         "- verdict du scan : **%s** (%d fichiers, %d octets)" % (scan["verdict"], scan["fichiers"], scan["octets"]),
         "- note de l'Eclaireur : %s" % ("n/d" if note is None else note), "", "## Trouvailles", ""]
    if not scan["findings"]:
        L.append("- aucune")
    for x in scan["findings"]:
        L.append("- [%s] %s %s : %s" % (x["gravite"], x["cat"], x["fichier"], x["detail"]))
    L += ["", "## Decision", "",
          "Installation seulement apres l'accord ecrit de l'utilisateur ; verdict « arret » = refus, meme avec accord.",
          "Retrait : `skillscan.py retirer %s --home H --target T`." % nom, ""]
    return "\n".join(L)


def _check_nom(nom):
    if not isinstance(nom, str) or not NOM_RX.match(nom) or ".." in nom:
        raise ValueError("nom de skill invalide : %r" % (nom,))


def _lock_path(home):
    return os.path.join(home, "LOCK.json")


def _lock_read(home):
    p = _lock_path(home)
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    return {"schema": 1, "skills": {}}


def _lock_write(home, data):
    os.makedirs(home, exist_ok=True)
    tmp = _lock_path(home) + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, _lock_path(home))


def installer(nom, src, home, target, source, commit, accord=False, license_hint=None):
    _check_nom(nom)
    if not isinstance(commit, str) or not COMMIT_RX.match(commit):
        raise ValueError("commit non fige (40 hexadecimaux exiges) : %r" % (commit,))
    scan = scan_dir(src, license_hint=license_hint)
    if scan["verdict"] != "ok":
        raise ScanBloquant("; ".join("%s:%s" % (x["cat"], x["detail"]) for x in scan["findings"] if x["gravite"] == "bloquant")[:300])
    if accord is not True:
        raise AccordRequis("installation d'un skill tiers : accord ecrit de l'utilisateur requis")
    dest = os.path.join(target, nom)
    if os.path.exists(dest):
        raise FileExistsError(dest)
    os.makedirs(target, exist_ok=True)
    shutil.copytree(lp(src), lp(dest), ignore=shutil.ignore_patterns(".git"))
    os.makedirs(os.path.join(home, "fiches"), exist_ok=True)
    with open(os.path.join(home, "fiches", nom + ".md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fiche(nom, source, commit, scan))
    lock = _lock_read(home)
    lock["skills"][nom] = {"source": source, "commit": commit, "sha256": tree_sha(dest), "date": time.strftime("%Y-%m-%d", time.gmtime()),
                           "scan": scan["verdict"], "avertissements": sum(1 for x in scan["findings"] if x["gravite"] == "avertissement")}
    _lock_write(home, lock)
    return lock["skills"][nom]


def retirer(nom, home, target):
    _check_nom(nom)
    lock = _lock_read(home)
    if nom not in lock["skills"]:
        raise KeyError(nom)
    dest = os.path.join(target, nom)
    if os.path.isdir(dest):
        shutil.rmtree(lp(dest))
    del lock["skills"][nom]
    _lock_write(home, lock)


def verifier_verrou(home, target):
    """[(nom, raison)] pour chaque skill verrouille absent ou different de l'empreinte enregistree."""
    bad = []
    for nom, e in sorted(_lock_read(home)["skills"].items()):
        d = os.path.join(target, nom)
        if not os.path.isdir(d):
            bad.append((nom, "absent"))
        elif tree_sha(d) != e["sha256"]:
            bad.append((nom, "empreinte differente"))
    return bad


# ----------------------------------------------------------------------------- CLI
def _opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        return args[i + 1] if i + 1 < len(args) else default
    return default


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if not argv:
        print(__doc__)
        return 2
    cmd, a = argv[0], argv[1:]
    try:
        if cmd == "scan" and a:
            r = scan_dir(a[0])
            print(json.dumps(r, ensure_ascii=False, indent=1))
            return 0 if r["verdict"] == "ok" else 1
        if cmd == "fiche" and len(a) >= 4:
            print(fiche(a[0], a[1], a[2], scan_dir(a[3])))
            return 0
        if cmd == "installer" and len(a) >= 4:
            e = installer(a[0], a[1], _opt(a, "--home"), _opt(a, "--target"), a[2], a[3], accord="--accord" in a)
            print(json.dumps(e, ensure_ascii=False))
            return 0
        if cmd == "retirer" and a:
            retirer(a[0], _opt(a, "--home"), _opt(a, "--target"))
            print("retire : " + a[0])
            return 0
        if cmd == "verifier":
            bad = verifier_verrou(_opt(a, "--home"), _opt(a, "--target"))
            for n, why in bad:
                print("DERIVE %s : %s" % (n, why))
            return 1 if bad else 0
    except (AccordRequis, ScanBloquant, ValueError, KeyError, FileExistsError, TypeError) as e:
        print("refus : %s %s" % (type(e).__name__, e))
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
