# -*- coding: utf-8 -*-
"""eclaireur.py : l'Eclaireur (lot L7, CDC 11) - trouver et adapter le meilleur skill pour chaque tache d'un PLAN.json.
Bibliotheque standard, AUCUN reseau : le 3e cercle (skills.sh) est INJECTE (`remote=`) ; son transport vit dans net/scout.py.

  eclaireur.py plan <PLAN.json> [--installed DIR]...   un classement (3 premiers) par tache, 1er et 2e cercles seulement
  eclaireur.py adapter <SKILL.md> mot [mot...] [--contrainte "texte"]   extrait adapte (<= 1200 tokens), original intact

Trois cercles, dans l'ordre : (1) skills installes de l'utilisateur, (2) catalogue embarque (catalog.jsonl), (3) skills.sh - ouvert
SEULEMENT si le meilleur score des deux premiers est sous le seuil. Vie privee : seuls des mots d'un vocabulaire ferme (VOCAB) peuvent
sortir, 4 au plus ; ni titre, ni description, ni chemin, ni nom de projet n'entrent jamais dans une requete.
Score (CDC 11.4) : adequation .40 · preuve passee .20 · confiance .15 · cout .10 · fraicheur .10 · absence de conflit .05.
La relecture Haiku des 5 premiers n'est pas faite par ce script (elle exige un modele) : `a_relire` liste ces 5 pour le manager.
"""
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog as C  # noqa: E402

POIDS = {"adequation": 0.40, "preuve": 0.20, "confiance": 0.15, "cout": 0.10, "fraicheur": 0.10, "conflit": 0.05}
SEUIL = 0.62
MAX_TOKENS = 1200
CHARS_PER_TOKEN = 3.7

# vocabulaire ferme : variante (FR ou EN) -> mot canonique. Seuls les mots canoniques peuvent sortir.
SYN = {}
for _canon, _vars in {
    "python": "python py", "go": "go golang", "rust": "rust", "kotlin": "kotlin", "java": "java", "typescript": "typescript ts",
    "javascript": "javascript js node nodejs", "swift": "swift", "ruby": "ruby", "php": "php", "csharp": "csharp dotnet", "cpp": "cpp c++",
    "dart": "dart flutter", "perl": "perl", "sql": "sql",
    "react": "react", "django": "django", "postgres": "postgres postgresql", "docker": "docker conteneur container", "kubernetes": "kubernetes k8s",
    "redis": "redis", "security": "security securite sécurité", "api": "api", "database": "database db base bdd", "frontend": "frontend",
    "backend": "backend", "seo": "seo", "video": "video vidéo", "mcp": "mcp", "git": "git", "spring": "spring springboot", "ios": "ios",
    "healthcare": "healthcare santé sante", "benchmark": "benchmark", "e2e": "e2e", "accessibility": "accessibility accessibilité accessibilite a11y",
    "literature": "literature littérature litterature", "architecture": "architecture", "pr": "pr", "pull": "pull", "request": "request",
    "ui": "ui interface", "browser": "browser navigateur", "server": "server serveur", "cache": "cache", "mysql": "mysql", "terraform": "terraform",
    "test": "test tests tester testing tdd", "review": "review revue relecture", "debug": "debug debugger deboguer", "refactor": "refactor refactorer refactoring",
    "design": "design concevoir conception", "deploy": "deploy deployer déployer deploiement", "document": "document documenter documentation docs",
    "audit": "audit auditer", "plan": "plan planifier", "research": "research recherche", "migration": "migration migrer", "optimize": "optimize optimiser optimisation",
    "build": "build construire", "commit": "commit", "create": "create creer créer", "measure": "measure mesurer", "patterns": "patterns pattern",
    "concurrency": "concurrency concurrence", "compliance": "compliance conformité conformite", "workflow": "workflow", "scaffold": "scaffold",
    "performance": "performance", "schema": "schema schéma", "wcag": "wcag", "hipaa": "hipaa", "evaluation": "evaluation évaluation", "synthesis": "synthesis synthèse synthese",
    "decision": "decision décision", "codebase": "codebase", "bug": "bug", "spec": "spec", "tickets": "tickets", "ci": "ci", "logging": "logging", "monitoring": "monitoring",
}.items():
    for _v in _vars.split():
        SYN[_v] = _canon
VOCAB = frozenset(SYN.values())
ORDRE = ("langage", "domaine", "acte", "livrable")
EXT = {".py": "python", ".go": "go", ".rs": "rust", ".kt": "kotlin", ".java": "java", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
       ".jsx": "javascript", ".swift": "swift", ".rb": "ruby", ".php": "php", ".cs": "csharp", ".cpp": "cpp", ".dart": "dart", ".pl": "perl", ".sql": "sql"}
TYPES = ("skill",)
EXCLUS = ("doublon", "verrouillé", "référencé")


# ----------------------------------------------------------------------------- besoin
def crochets(task):
    """Crochets d'une tache : explicites (`crochets`) sinon langage deduit de l'extension des `files`. Jamais le titre."""
    c = {k: v for k, v in dict(task.get("crochets") or {}).items() if k in ORDRE and isinstance(v, str)}
    if "langage" not in c:
        langs = [EXT[os.path.splitext(f)[1].lower()] for f in task.get("files", []) if isinstance(f, str) and os.path.splitext(f)[1].lower() in EXT]
        if langs:
            c["langage"] = max(set(langs), key=langs.count)
    return c


def mots_cles(cr):
    """1 a 4 mots du vocabulaire ferme, dans l'ordre langage, domaine, acte, livrable. Tout le reste est jete."""
    out = []
    for k in ORDRE:
        v = cr.get(k)
        if not isinstance(v, str):
            continue
        for w in re.findall(r"[a-zA-Z0-9+#éèêàçùûîô]+", v.lower()):
            canon = SYN.get(w)
            if canon and canon not in out:
                out.append(canon)
    return out[:4]


# ----------------------------------------------------------------------------- texte
_SUF = ("ization", "isation", "ation", "ize", "ise", "ing", "ers", "er", "ed", "es", "s", "ion")


def stem(w):
    w = w.lower()
    for s in _SUF:
        if w.endswith(s) and len(w) - len(s) >= 3:
            return w[:-len(s)]
    return w


def toks(s):
    return [stem(w) for w in re.findall(r"[a-z0-9+#]+", (s or "").lower()) if len(w) > 1]


def _cand(e):
    return {"id": e["id"], "nom": e["nom"], "cercle": 2, "nom_t": set(toks(e["nom"].replace("-", " "))),
            "desc_t": set(toks(e["description"])) | set(toks(" ".join(e.get("déclencheurs", [])))), "chemin_t": set(toks(re.sub(r"[-_/.#:]+", " ", e["chemin"]))),
            "cout_tokens": e.get("coût_tokens") or 0, "elt": e}


def cercle1(dirs):
    """Skills installes : dossiers contenant <nom>/SKILL.md (frontmatter name/description). Lecture seule."""
    out = []
    for d in dirs or []:
        if not os.path.isdir(d):
            continue
        for nom in sorted(os.listdir(d)):
            p = os.path.join(d, nom, "SKILL.md")
            if not os.path.isfile(p):
                continue
            with open(C.lp(p), "rb") as fh:
                raw = fh.read(6000).decode("utf-8", "replace")
            fm = C.frontmatter(raw)
            nm = (fm.get("name") or nom).strip() or nom
            desc = fm.get("description") or ""
            age = (time.time() - os.path.getmtime(p)) / 86400.0
            out.append({"id": "installe:" + nm, "nom": nm, "cercle": 1, "nom_t": set(toks(nm.replace("-", " "))), "desc_t": set(toks(desc)),
                        "chemin_t": set(), "cout_tokens": int(os.path.getsize(p) / CHARS_PER_TOKEN), "age_jours": age, "chemin_local": p})
    return out


def cercle2(els, types=TYPES):
    return [_cand(e) for e in els if e["type"] in types and e["statut"] not in EXCLUS and not e.get("verrou") and not e.get("doublon_de")]


def cercle3(items, kws):
    out = []
    for it in items:
        nm = it["nom"]
        out.append({"id": "skills.sh:" + it["id"], "nom": nm, "cercle": 3, "nom_t": set(toks(nm.replace("-", " "))), "desc_t": set(toks(it.get("source", "").replace("/", " "))),
                    "chemin_t": set(), "cout_tokens": 0, "installs": it.get("installs", 0), "source": it.get("source", ""), "quarantaine_requise": True})
    return out


# ----------------------------------------------------------------------------- score
def _adequation(c, kst):
    if not kst:
        return 0.0
    best = []
    for k in kst:
        if k in c["nom_t"]:
            best.append(1.0)
        elif k in c["desc_t"]:
            best.append(0.55)
        elif k in c["chemin_t"]:
            best.append(0.35)
        else:
            best.append(0.0)
    cover = sum(best) / len(kst)
    ncov = (len(c["nom_t"] & set(kst)) / len(c["nom_t"])) if c["nom_t"] else 0.0
    return 0.65 * cover + 0.35 * ncov


def _fts(cands, kst):
    """Rang FTS5 (bm25) -> {id: 0..1} ; repli sans FTS5 : tous a 0. Les mots du besoin sont tous deja racinises."""
    if not kst or not cands:
        return {}
    try:
        import sqlite3
        db = sqlite3.connect(":memory:")
        db.execute("create virtual table t using fts5(id unindexed, nom, description, chemin)")
        db.executemany("insert into t values (?,?,?,?)", [(c["id"], " ".join(c["nom_t"]), " ".join(c["desc_t"]), " ".join(c["chemin_t"])) for c in cands])
        q = " OR ".join('"%s"' % k.replace('"', "") for k in kst)
        rows = db.execute("select id from t where t match ? order by bm25(t, 0.0, 6.0, 2.0, 1.0) limit 50", (q,)).fetchall()
        db.close()
        n = len(rows)
        return {r[0]: 1.0 - i / max(n, 1) for i, r in enumerate(rows)}
    except Exception:
        return {}


def _confiance(c):
    if c["cercle"] == 1:
        return 1.0
    if c["cercle"] == 2:
        return 0.9
    return 0.15 + 0.45 * min(1.0, math.log10(c.get("installs", 0) + 1) / 6.0)      # distant : plafonne tant que non vetted


def _fraicheur(c):
    if c["cercle"] == 1:
        return 1.0 if c.get("age_jours", 0) <= 180 else max(0.3, 1.0 - (c["age_jours"] - 180) / 720.0)
    return 0.8 if c["cercle"] == 2 else 0.5


def _cout(c):
    if c["cercle"] == 3:
        return 0.5
    return max(0.0, 1.0 - min(1.0, c.get("cout_tokens", 0) / 8000.0))


def noter(c, kst, fts, preuves, noms_installes):
    ok = ko = 0
    p = (preuves or {}).get(c["id"])
    if p:
        ok, ko = int(p.get("ok", 0)), int(p.get("ko", 0))
    conflit = 0.0 if (c["cercle"] != 1 and c["nom"] in noms_installes) else 1.0
    d = {"adequation": min(1.0, 0.8 * _adequation(c, kst) + 0.2 * fts.get(c["id"], 0.0)), "preuve": (ok + 1.0) / (ok + ko + 2.0),
         "confiance": _confiance(c), "cout": _cout(c), "fraicheur": _fraicheur(c), "conflit": conflit}
    s = sum(POIDS[k] * d[k] for k in POIDS)
    return round(max(0.0, min(1.0, s)), 4), {k: round(v, 3) for k, v in d.items()}


def scout(task, els, installed_dirs=None, remote=None, preuves=None, seuil=SEUIL, n=5, types=TYPES):
    """Classement pour UNE tache. `remote(kws) -> [{id, nom, source, installs}]` n'est appele que sous le seuil et si kws est non vide.
    `types` : skills par defaut (A19) ; l'Eclaireur universel (capacites) interroge chaque type a part."""
    cr = crochets(task)
    kws = mots_cles(cr)
    kst = [stem(k) for k in kws]
    c1, c2 = (cercle1(installed_dirs) if "skill" in types else []), cercle2(els, types)
    if "skill" not in types:
        remote = None                                    # skills.sh only serves skills
    noms_inst = {c["nom"] for c in c1}
    fts = _fts(c1 + c2, kst)

    def rank(cands):
        res = []
        for c in cands:
            s, d = noter(c, kst, fts, preuves, noms_inst)
            if d["adequation"] > 0:
                res.append(dict({k: v for k, v in c.items() if k not in ("nom_t", "desc_t", "chemin_t", "elt")}, score=s, details=d, mots_cles=kws))
        return sorted(res, key=lambda x: (-x["score"], x["id"]))

    r1, r2 = rank(c1), rank(c2)
    best = max([x["score"] for x in r1 + r2] or [0.0])
    ouvre = False
    r3 = []
    if best < seuil and kws and remote is not None:
        ouvre = True
        try:
            got = remote(kws) or []
        except Exception:
            got = []
        r3 = rank(cercle3(got, kws))
    first = [x for x in r1 if x["score"] >= seuil]
    rest = sorted([x for x in r1 if x["score"] < seuil] + r2 + r3, key=lambda x: (-x["score"], x["id"]))
    cl = (first + rest)[:n]
    return {"mots_cles": kws, "cercle3": ouvre, "classement": cl, "a_relire": [x["id"] for x in cl[:5]], "meilleur": best}


def scout_plan(plan, els, **kw):
    return [dict(tache=t.get("id"), **scout(t, els, **kw)) for t in plan.get("tasks", [])]


# ----------------------------------------------------------------------------- Eclaireur universel (lot 4 V3.1)
TOUS_TYPES = ("skill", "agent", "commande", "hook", "règle", "script", "schéma")
SEUIL_TYPE = 0.5          # point de depart, non calibre (n = 0) : configurable, jamais presente comme optimal
BUDGET_CONTEXTE = 6000    # tokens de capacites chargees par tache au plus (cercle 2 : detail) ; l'index n'est jamais charge


def nom_norm(nom):
    return re.sub(r"[^a-z0-9]", "", (nom or "").lower().replace("reviewer", "review").replace("-review", "review"))


def _fichier(e):
    p = os.path.join(C.VENDOR, e["chemin"])
    if os.path.isdir(p):
        p = os.path.join(p, "SKILL.md")
    return p


def _sha_fichier(p):
    import hashlib
    with open(C.lp(p), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def integrite(e, els=None):
    """-> (ok, raison). Compare le fichier vendor a l'empreinte du catalogue (elle-meme issue de LOCK.json). Une entree
    sans fichier propre (`conteneur#id`, hooks de hooks.json) : conteneur verifie contre son element, puis presence de
    l'entree et de son empreinte dans hooks.metadata.json."""
    import hashlib
    if "#" in e.get("chemin", ""):
        cont, hid = e["chemin"].split("#", 1)
        parent = next((x for x in (els or []) if x["id"] == e.get("partie_de")), None)
        cp = os.path.join(C.VENDOR, cont)
        if not os.path.isfile(C.lp(cp)):
            return False, "integrite : conteneur absent (%s)" % cont
        if parent is not None and parent.get("sha") and _sha_fichier(cp) != parent["sha"]:
            return False, "integrite : conteneur %s modifie" % cont
        meta = os.path.join(os.path.dirname(cp), "hooks.metadata.json")
        try:
            with open(C.lp(meta), encoding="utf-8") as fh:
                ents = [x for v in json.load(fh)["entries"].values() for x in v]
        except (OSError, ValueError, KeyError):
            return False, "integrite : metadonnees illisibles"
        if not any(x.get("id") == hid and (not e.get("sha") or x.get("fingerprint") == e["sha"]) for x in ents):
            return False, "integrite : entree %s absente ou empreinte differente" % hid
        return True, "integrite verifiee (conteneur + empreinte de l'entree)"
    fichiers = [f for f in e.get("fichiers") or [] if isinstance(f, str)]
    if len(fichiers) > 1:                         # multi-file unit: same composite digest as catalog.sha_of
        try:
            h = C.sha_of(fichiers, {f: _sha_fichier(os.path.join(C.VENDOR, f)) for f in fichiers})
        except OSError:
            return False, "integrite : fichier absent dans %s" % e["chemin"]
        if e.get("sha") and h != e["sha"]:
            return False, "integrite : empreinte composite differente du catalogue (%s...)" % h[:12]
        return True, "integrite verifiee (%d fichiers)" % len(fichiers)
    p = _fichier(e)
    if not os.path.isfile(C.lp(p)):
        return False, "integrite : fichier absent (%s)" % e["chemin"]
    with open(C.lp(p), "rb") as fh:
        h = hashlib.sha256(fh.read()).hexdigest()
    if e.get("sha") and h != e["sha"]:
        return False, "integrite : empreinte differente du catalogue (%s...)" % h[:12]
    return True, "integrite verifiee"


def _cout_mesure(e):
    if "#" in e.get("chemin", ""):                      # hook entry: runs as a script, loads no instructions in context
        return int(e.get("coût_tokens") or 0), "estime"
    p = _fichier(e)
    try:
        return int(math.ceil(os.path.getsize(C.lp(p)) / CHARS_PER_TOKEN)), "mesure"
    except OSError:
        return int(e.get("coût_tokens") or 0), "estime"


def capacites(task, els, types=TOUS_TYPES, budget=BUDGET_CONTEXTE, par_type=1, seuil=SEUIL_TYPE):
    """Plan de capacites d'une tache, tous types confondus. Cercle 0 : index (catalogue en memoire, jamais charge dans un
    prompt) ; cercle 1 : shortlist par type ; cercle 2 : seules les retenues sont chargees, dans la limite du budget.
    Chaque retenue et chaque ecart porte sa raison. Couts MESURES (taille du fichier) quand le fichier existe."""
    by_id = {e["id"]: e for e in els}
    cands = []
    for ty in types:
        r = scout(task, els, types=(ty,), n=max(3, par_type + 2))
        for x in r["classement"]:
            x = dict(x, type=ty)
            cands.append(x)
    cands.sort(key=lambda x: (-x["score"], x["id"]))
    retenues, ecartees, pris, vus = [], [], {}, set()
    total = 0
    for x in cands:
        e = by_id.get(x["id"])
        base = {"id": x["id"], "type": x["type"], "nom": x["nom"], "score": x["score"]}
        if x["score"] < seuil:
            ecartees.append(dict(base, raison="sous le seuil %.2f (adequation %.2f)" % (seuil, x["details"]["adequation"])))
            continue
        if pris.get(x["type"], 0) >= par_type:
            ecartees.append(dict(base, raison="deja %d capacite(s) de type %s" % (par_type, x["type"])))
            continue
        if nom_norm(x["nom"]) in vus:
            ecartees.append(dict(base, raison="redondante avec une capacite deja retenue (meme nom)"))
            continue
        if e is not None:
            ok, why = integrite(e, els)
            if not ok:
                ecartees.append(dict(base, raison=why))
                continue
            cout, src = _cout_mesure(e)
        else:
            cout, src = 0, "estime"
        if total + cout > budget:
            ecartees.append(dict(base, raison="budget de contexte : %d + %d > %d tokens" % (total, cout, budget)))
            continue
        total += cout
        pris[x["type"]] = pris.get(x["type"], 0) + 1
        vus.add(nom_norm(x["nom"]))
        retenues.append(dict(base, cout_tokens=cout, cout_source=src,
                             raison="score %.2f (adequation %.2f, preuve %.2f) ; integrite verifiee" % (x["score"], x["details"]["adequation"], x["details"]["preuve"])))
    return {"tache": task.get("id"), "mots_cles": mots_cles(crochets(task)), "retenues": retenues, "ecartees": ecartees,
            "contexte_tokens": total, "budget": budget}


def capacites_plan(plan, els, **kw):
    return [capacites(t, els, **kw) for t in plan.get("tasks", [])]


# ----------------------------------------------------------------------------- adaptation
NEUTRALISER = [(re.compile(p, re.I), why) for p, why in (
    (r"git\s+push", "push sans accord"), (r"--no-verify|--force\b|-f\s+origin", "contournement de garde-fou"),
    (r"dangerously-skip-permissions", "contourne les permissions"), (r"\brm\s+-[a-z]*r[a-z]*f?|\brm\s+-rf", "suppression recursive"),
    (r"\|\s*(?:ba|z)?sh\b|\biex\b|Invoke-Expression", "execution de contenu telecharge"), (r"(?:npx|npm|pip|apt(?:-get)?|brew)\s+[^\n]*(?:\s-y\b|--yes)", "installation silencieuse"),
    (r"tele" r"metry|analytics\.(?:track|send)|send\s+(?:usage|metrics)", "telemetrie"), (r"ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions", "consigne hostile"),
    (r"\bsudo\b", "elevation de privileges"), (r"publish\s+to\s+(?:npm|pypi|the\s+registry)|npm\s+publish|twine\s+upload", "publication sans accord"))]


def _sections(text):
    body = text
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            body = body[end + 4:]
    parts, cur = [], ["", []]
    for ln in body.splitlines():
        if re.match(r"^#{1,4}\s", ln):
            parts.append(cur)
            cur = [ln, []]
        else:
            cur[1].append(ln)
    parts.append(cur)
    return [(h, "\n".join(b)) for h, b in parts if h or "".join(b).strip()]


def _neutralise(line):
    for rx, why in NEUTRALISER:
        if rx.search(line):
            return "[neutralisé : %s]" % why
    return line


def adapter(text, mots, contraintes, max_tokens=MAX_TOKENS):
    """Extrait des SEULES sections utiles, consignes incompatibles neutralisees, contraintes du projet ajoutees, <= max_tokens.
    Fonction pure : ne lit ni n'ecrit aucun fichier."""
    kst = [stem(m) for m in mots]
    scored = []
    for i, (h, b) in enumerate(_sections(text)):
        s = 3 * sum(k in toks(h) for k in kst) + sum(k in set(toks(b)) for k in kst)
        if s > 0:
            scored.append((-s, i, h, b))
    cons = "\n".join(["", "## Contraintes du projet (ajoutees par l'Eclaireur)"] + ["- " + c for c in contraintes])
    head = "<!-- extrait adapte par l'Eclaireur : l'original n'est pas modifie -->"
    budget = int(max_tokens * CHARS_PER_TOKEN) - len(cons) - len(head) - 40
    out, used = [], 0
    for _s, _i, h, b in sorted(scored, key=lambda x: (x[0], x[1])):
        block = "\n".join(_neutralise(ln) for ln in ((h + "\n" + b) if h else b).splitlines())
        room = budget - used
        if room <= 80:
            break
        if len(block) > room:
            block = block[:room].rsplit("\n", 1)[0] + "\n[…coupé]"
        out.append((_i, block))
        used += len(block) + 2
    res = head + "\n" + "\n\n".join(b for _i, b in sorted(out)) + "\n" + cons
    return res[:int(max_tokens * CHARS_PER_TOKEN)]


def adapter_fichier(path, mots, contraintes):
    with open(C.lp(path), "rb") as fh:
        return adapter(fh.read().decode("utf-8", "replace"), mots, contraintes)


# ----------------------------------------------------------------------------- contrat (regle v2.5)
def contrat(cand, phase, els=None, suivant=None):
    nom = cand["nom"]
    if cand["cercle"] == 1:
        appel, preuve = "Skill(%s)" % nom, "un tool_use Skill nomme %s dans le transcript" % nom
    elif cand["cercle"] == 2:
        chemin = next((e["chemin"] for e in (els or []) if e["id"] == cand["id"]), None)
        appel = "Read(${CLAUDE_PLUGIN_ROOT}/vendor/%s)" % (chemin or nom)
        preuve = "un Read de ce fichier dans le transcript, puis l'extrait adapte cite dans la sortie de la phase"
    else:
        appel = "Skill(%s) apres quarantaine, scan et accord ecrit" % nom
        preuve = "fiche de scan + entree dans LOCK.json"
    pb = ("candidat suivant : %s" % suivant["nom"]) if suivant else "etat not_executable avec la raison, executer la phase sans ce skill"
    return {"id": cand["id"], "declencheur": "la tache vise : %s" % ", ".join(cand.get("mots_cles") or ["?"]), "phase": phase,
            "appel": appel, "preuve": preuve, "plan_b": pb, "obligatoire": False}


def contrats(paires, els=None):
    """paires : [(candidat, phase)] dans l'ordre de preference. Deux contrats par phase au plus."""
    par, out = {}, []
    allc = [c for c, _p in paires]
    for c, ph in paires:
        if par.get(ph, 0) >= 2:
            continue
        nxt = next((x for x in allc if x["id"] != c["id"] and x not in [p for p, q in paires if q == ph][:par.get(ph, 0) + 1]), None)
        out.append(contrat(c, ph, els, suivant=nxt))
        par[ph] = par.get(ph, 0) + 1
    return out


# ----------------------------------------------------------------------------- CLI
def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(argv) >= 2 and argv[0] == "plan":
        inst = [argv[i + 1] for i, a in enumerate(argv) if a == "--installed" and i + 1 < len(argv)]
        with open(argv[1], encoding="utf-8") as fh:
            plan = json.load(fh)
        for r in scout_plan(plan, C.load_catalog(), installed_dirs=inst):
            print("%s | mots-cles: %s | meilleur %.2f%s" % (r["tache"], " ".join(r["mots_cles"]) or "-", r["meilleur"], "" if r["meilleur"] >= SEUIL else " (sous le seuil : 3e cercle via net/scout.py)"))
            for x in r["classement"][:3]:
                print("   %.2f c%d %s" % (x["score"], x["cercle"], x["id"]))
        return 0
    if len(argv) >= 2 and argv[0] == "capacites":
        bud = int(argv[argv.index("--budget") + 1]) if "--budget" in argv else BUDGET_CONTEXTE
        with open(argv[1], encoding="utf-8") as fh:
            plan = json.load(fh)
        for r in capacites_plan(plan, C.load_catalog(), budget=bud):
            print("%s | mots-cles: %s | contexte %d/%d tokens" % (r["tache"], " ".join(r["mots_cles"]) or "-", r["contexte_tokens"], r["budget"]))
            for x in r["retenues"]:
                print("   + %-8s %s (%d tokens %s) : %s" % (x["type"], x["id"], x["cout_tokens"], x["cout_source"], x["raison"]))
            for x in r["ecartees"][:5]:
                print("   - %-8s %s : %s" % (x["type"], x["id"], x["raison"]))
        return 0
    if len(argv) >= 3 and argv[0] == "adapter":
        mots = [a for a in argv[2:] if not a.startswith("--")]
        cons = [argv[i + 1] for i, a in enumerate(argv) if a == "--contrainte" and i + 1 < len(argv)]
        mots = [m for m in mots if m not in cons]
        print(adapter_fichier(argv[1], mots, cons))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
