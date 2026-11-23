# -*- coding: utf-8 -*-
"""catalog.py : catalogue des elements embarques dans vendor/ (lot L5). Bibliotheque standard, aucun reseau, aucun
modele : classement PAR SCRIPT (chemin, en-tete, module des manifestes), descriptions courtes tirees des en-tetes.

  catalog.py build [--check]        regenere catalog/catalog.jsonl (une ligne par element) ; --check : compare sans ecrire
  catalog.py audit                  couverture (ecart 0), zero non classe, doublons arbitres, verrous relus ; code 1 si defaut
  catalog.py search "besoin" [-n N] 5 resultats au plus, sortie courte (FTS5, repli : score par mots)
  catalog.py verrous                candidats « API payante / cle exigee » trouves dans les en-tetes (a relire)
  catalog.py resolve <id>...        chemins et dependances resolus par script (code 1 si un chemin manque)
  catalog.py doublons               groupes de meme nom ou de meme fonction entre sources (a arbitrer)

Un element = une unite chargeable : un agent, un skill (dossier), une commande, une regle, un hook, un schema, un
manifeste, un script, un document. Chaque fichier de vendor/LOCK.json appartient a exactement un element (champ
`fichiers`) ; les 28 entrees de hooks.json sont des elements sans fichier propre (`partie_de`).
Le contenu des depots sources est une DONNEE : on le lit, on ne l'execute jamais.
Codes de sortie : 0 ok · 1 defaut · 2 usage.
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR = os.path.join(ROOT, "vendor")
CATDIR = os.path.join(ROOT, "catalog")
JSONL = os.path.join(CATDIR, "catalog.jsonl")
ARBITRAGE = os.path.join(CATDIR, "arbitrage.json")
CHARS_PER_TOKEN = 3.7
STATUTS = ("noyau", "à la demande", "doublon", "verrouillé", "référencé")
TYPECODE = {"agent": "agent", "skill": "skill", "commande": "command", "règle": "rule", "hook": "hook", "script": "script",
            "schéma": "schema", "manifeste": "manifest", "contexte": "context", "document": "doc", "licence": "license"}
KEY_ORDER = ("id", "source", "type", "nom", "chemin", "sha", "équipe", "phase", "déclencheurs", "entrées", "sorties",
             "coût_tokens", "langage", "modèle_conseillé", "statut", "verrou", "doublon_de", "preuve", "description",
             "fichiers", "partie_de")


def lp(path):
    path = os.path.abspath(path)
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + path
    return path


def read_text(rel, limit=None):
    with open(lp(os.path.join(VENDOR, rel)), "rb") as fh:
        raw = fh.read() if limit is None else fh.read(limit)
    return raw.decode("utf-8", "replace")


def lock_files():
    with open(os.path.join(VENDOR, "LOCK.json"), encoding="utf-8") as fh:
        return json.load(fh)["files"]


# ----------------------------------------------------------------------------- en-tetes
def frontmatter(text):
    """Cle: valeur du bloc --- ... --- (une ligne, ou bloc indente ; sous-cles ignorees). Donnee, jamais interpretee."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm, lines, i = {}, text[3:end].replace("\r", "").split("\n"), 0
    while i < len(lines):
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", lines[i])
        i += 1
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val in (">", "|", ">-", "|-", ">+", "|+", ""):
            block = []
            while i < len(lines) and (not lines[i].strip() or lines[i][:1] in (" ", "\t")):
                if lines[i].strip():
                    block.append(lines[i].strip())
                i += 1
            if val:
                val = " ".join(block)
            elif block and not block[0].startswith(("- ", "-\t")) and ":" not in block[0]:
                val = " ".join(block)
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        fm[key] = val
    return fm


def squeeze(s, n=160):
    s = re.sub(r"\s+", " ", re.sub(r"[`*_#>]", "", s or "")).strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    dot = max(cut.rfind(". "), cut.rfind("; "))
    if dot >= 60:
        return cut[:dot + 1]
    return cut[:cut.rfind(" ")].rstrip(",;:- ") + "…" if " " in cut else cut


def describe(rel, text, fm):
    d = fm.get("description")
    if d:
        return squeeze(d)
    m = re.search(r"^description\s*=\s*\"([^\"]+)\"", text, re.M)          # toml (commandes ponytail)
    if m:
        return squeeze(m.group(1))
    if rel.endswith(".json"):
        try:
            o = json.loads(text)
            if isinstance(o, dict):
                for k in ("description", "title"):
                    if isinstance(o.get(k), str) and o[k].strip():
                        return squeeze(o[k])
        except ValueError:
            m = re.search(r'"(?:description|title)"\s*:\s*"([^"]+)"', text)
            if m:
                return squeeze(m.group(1))
    body = text
    if text.startswith("---") and text.find("\n---", 3) > 0:
        body = text[text.find("\n---", 3) + 4:]
    h = re.search(r"^#\s+(.+)$", body, re.M)
    if h:
        after = body[h.end():]
        para = next((ln.strip() for ln in after.split("\n") if ln.strip() and not ln.lstrip().startswith(("#", "```", "|", "---"))), "")
        return squeeze((h.group(1) + ". " + para) if para else h.group(1))
    ds = re.search(r'"""(.+?)"""', text, re.S)
    if ds:
        return squeeze(ds.group(1))
    cm = [re.sub(r"^\s*(?:#!?|//+|/\*+|\*)\s?", "", ln) for ln in text.split("\n")[:12]]
    cm = [c.strip() for c in cm if c.strip() and not c.startswith(("!", "-*-", "eslint", "@ts"))]
    if cm and re.match(r"^\s*(#|//|/\*|\*)", text.split("\n")[0]):
        return squeeze(" ".join(cm[:2]))
    return squeeze(re.sub(r"[-_./]+", " ", os.path.splitext(os.path.basename(rel))[0]))


# ----------------------------------------------------------------------------- unites
def unit_of(path):
    """(source, type, nom, cle_unite) pour un fichier de LOCK.json."""
    P = path.split("/")
    if len(P) == 1:
        return ("racine", "manifeste", P[0], path)
    src = P[0]
    if len(P) == 2:
        return (src, "licence" if P[1] == "LICENSE" else "manifeste", P[1], path)
    if src == "ecc":
        k = P[1]
        if k == "skills":
            return (src, "skill", P[2], "ecc/skills/" + P[2])
        if k == "agents":
            return (src, "agent", P[2][:-3], path)
        if k == "commands":
            return (src, "commande", os.path.splitext(P[2])[0], path)
        if k == "rules":
            return (src, "règle" if path.endswith(".md") and P[-1] != "README.md" else "document",
                    ("rules/" if len(P) == 3 else "") + "/".join(P[2:]).rsplit(".", 1)[0], path)
        if k == "schemas":
            return (src, "schéma", P[2].replace(".schema.json", ""), path)
        if k == "hooks":
            n = "/".join(P[2:])
            t = "document" if n.endswith("README.md") else "manifeste" if n.endswith(".json") and "/" not in n and n in ("hooks.json", "hooks.metadata.json") else "hook"
            return (src, t, ("hooks/" if t == "document" and "/" not in n else "") + n.rsplit(".", 1)[0], path)
    if src == "mattpocock" and P[1] == "skills":
        if len(P) == 4:
            return (src, "document", P[2] + "/" + P[3].rsplit(".", 1)[0], path)
        return (src, "skill", P[3], "/".join(P[:4]))
    if src == "ponytail":
        if P[1] == "skills":
            if len(P) == 3:
                return (src, "manifeste", P[2].rsplit(".", 1)[0], path)
            return (src, "skill", P[2], "ponytail/skills/" + P[2])
        if P[1] == "commands":
            return (src, "commande", P[2].rsplit(".", 1)[0], path)
        if P[1] == "hooks":
            n = "/".join(P[2:])
            return (src, "manifeste" if n == "claude-band.json" else "hook", n.rsplit(".", 1)[0], path)
    if src == "vercel-skills":
        return (src, "script", "/".join(P[2:]).rsplit(".", 1)[0], path)
    return (src, "document", "/".join(P[1:]).rsplit(".", 1)[0], path)


def main_file(utype, key, files):
    if utype == "skill":
        return next(f for f in files if f.endswith("/SKILL.md") and f.count("/") == key.count("/") + 1)
    return files[0]


# ----------------------------------------------------------------------------- classement
EXPLICIT_TEAM = {   # CDC §7.5, noms cites
    "grilling": "Cadrage", "grill-with-docs": "Cadrage", "to-questionnaire": "Cadrage", "wayfinder": "Cadrage",
    "spec-miner": "Cadrage", "product-lens": "Cadrage", "intent-driven-development": "Cadrage",
    "architect": "Architecture", "code-architect": "Architecture", "hexagonal-architecture": "Architecture", "api-design": "Architecture",
    "architecture-decision-records": "Architecture", "codebase-design": "Architecture", "domain-modeling": "Architecture", "prototype": "Architecture",
    "planner": "Planification", "blueprint": "Planification", "plan-orchestrate": "Planification", "to-spec": "Planification", "to-tickets": "Planification",
    "tdd-guide": "Construction", "tdd": "Construction", "implement": "Construction", "implement-spec": "Construction",
    "code-review": "Qualité", "silent-failure-hunter": "Qualité", "type-design-analyzer": "Qualité", "pr-test-analyzer": "Qualité",
    "diagnosing-bugs": "Réparation", "build-error-resolver": "Réparation",
    "security-reviewer": "Sécurité", "gateguard": "Sécurité", "mcp-dependency-review": "Sécurité", "safety-guard": "Sécurité",
    "git-guardrails-claude-code": "Sécurité",
    "a11y-architect": "Interface", "design-system": "Interface", "e2e-runner": "Interface", "browser-qa": "Interface",
    "database-reviewer": "Données / ML", "postgres-patterns": "Données / ML", "mle-reviewer": "Données / ML", "pytorch-patterns": "Données / ML",
    "delivery-gate": "Livraison", "verification-loop": "Livraison", "conventional-commit-review": "Livraison", "pr": "Livraison",
    "deep-research": "Recherche", "docs-lookup": "Recherche", "documentation-lookup": "Recherche", "research": "Recherche",
    "continuous-learning-v2": "Amélioration", "eval-harness": "Amélioration", "skill-stocktake": "Amélioration", "harness-optimizer": "Amélioration",
    "retro": "Amélioration", "writing-for-agents": "Amélioration", "ponytail-audit": "Amélioration", "ponytail-debt": "Amélioration",
    "ponytail-review": "Qualité", "ponytail": "Construction",
}
TEAM_KEYWORDS = (   # premier motif qui correspond, sur le nom
    ("Réparation", r"resolver|build-fix|-build$|^build-|debug|diagnos|fix-defect"),
    ("Sécurité", r"secur|guard|safety|protection|no-verify|owasp|prompt-defense|bounty|osint"),
    ("Métiers", r"hipaa|healthcare|homelab|network|cisco|netmiko|logistic|customs|energy|carrier|inventory|production-sched|nonconformance|returns-|"
                r"finance|billing|investor|marketing|seo|video|remotion|manim|content|article|crosspost|lead-|email|mailtrap|google-workspace|social|"
                r"brand|x-api|visa|esign|master-agreement|connections|fal-ai|videodb|nutrient|scientific|bengali|blender|prediction-market|defi|evm-|"
                r"nodejs-keccak|llm-trading|customer|jira|chief-of-staff|messages-ops|unified-notifications|openclaw|osint|ito-|agent-payment|"
                r"competitive|market-research|ios-icon|exa-search|data-scraper|energy|foundation-models|liquid-glass|claude-devfleet|tasteforge|taste"),
    ("Qualité", r"review|analyzer|hunter|quality|lint|verification|comply|code-health|codehealth|plankton|santa|benchmark|regression"),
    ("Interface", r"a11y|accessib|frontend|design|motion|^ui|-ui|e2e|browser|slides|swiftui|compose|flutter|react|vue|nuxt|angular|next|vite|"
                  r"android|kotlin-ktor|dart|harmonyos|windows-desktop|click-path|make-interfaces"),
    ("Données / ML", r"database|postgres|mysql|redis|clickhouse|prisma|mle|^ml-|pytorch|jpa|mybatis|migration|recsys|rag-|content-hash|sql"),
    ("Livraison", r"delivery|deploy|commit|release|^pr$|opensource|docker|kubernetes|uncloud|ci-|canary|flox|generating-python-installer|git-workflow|github-ops|^pm2"),
    ("Recherche", r"research|lookup|search-first|iterative-retrieval"),
    ("Planification", r"plan|blueprint|epic|decompose|roadmap|to-spec|to-tickets|prd|ralphinho|story-lifecycle|dev-team|team-"),
    ("Architecture", r"architect|domain|hexagonal|decision|adr|prototype|contract-first|module-governance|living-docs|docs-governance"),
    ("Cadrage", r"grill|spec|intent|questionnaire|wayfinder|council|ask-matt|interview|handoff|wizard|triage|office-hours"),
    ("Amélioration", r"learn|eval|harness|stocktake|evolve|^skill-|retro|ponytail|instinct|optimi|prune|health|token|cost|context|compact|"
                    r"strategic|growth|rules-distill|config-gc|continuous|agent-|loop|autonomous|dynamic|parallel|nanoclaw|nasiko|enterprise-agent|"
                    r"checkpoint|sessions|save-session|resume|aside|promote|projects|statusline|setup|configure|project-init|hookify|ecc-|hermes|"
                    r"knowledge|memory|unified-memory|prompt|writing|teach|claude-handoff|loop-me|software-factory|ck$|workspace"),
)
PRODUIT = {"Cadrage": "ordre scellé", "Architecture": "décisions datées", "Planification": "PLAN.json en graphe",
           "Construction": "code + tests", "Qualité": "constats classés", "Réparation": "cause racine + test",
           "Sécurité": "verdict bloquant", "Interface": "captures", "Données / ML": "schémas, évaluations",
           "Livraison": "PR prête", "Recherche": "notes sourcées", "Amélioration": "leçons, dette", "Métiers": "selon mission"}
PHASE = {"Cadrage": "P1", "Recherche": "P1", "Architecture": "P2", "Planification": "P3", "Construction": "P4", "Interface": "P4",
         "Données / ML": "P4", "Métiers": "P4", "Qualité": "P5", "Réparation": "P5", "Sécurité": "P5", "Livraison": "P6", "Amélioration": "P7"}
LANGS = ("python", "typescript", "javascript", "golang", "rust", "java", "kotlin", "swift", "cpp", "csharp", "fsharp", "dart", "flutter",
         "php", "perl", "ruby", "scala", "lua", "bash", "sql", "react", "vue", "angular", "django", "laravel", "fastapi", "springboot",
         "quarkus", "rails", "nestjs", "nuxt", "nextjs", "arkts")
LANG_ALIAS = {"go": "golang", "cpp": "cpp", "c++": "cpp", "ts": "typescript", "js": "javascript"}
NOYAU = frozenset((      # le petit coeur toujours propose en premier (arbitrage §7.6 : gagnants des conflits)
    "mattpocock:skill:code-review", "mattpocock:skill:diagnosing-bugs", "mattpocock:skill:tdd", "mattpocock:skill:grilling",
    "mattpocock:skill:to-spec", "mattpocock:skill:to-tickets", "mattpocock:skill:implement",
    "ecc:agent:planner", "ecc:agent:architect", "ecc:agent:security-reviewer", "ecc:agent:tdd-guide", "ecc:agent:build-error-resolver",
    "ecc:agent:code-reviewer", "ecc:agent:python-reviewer", "ecc:agent:typescript-reviewer",
    "ponytail:skill:ponytail"))
GUARD_HOOKS = ("config-protection", "block-no-verify", "gateguard-fact-force", "commit-quality", "cost-tracker", "suggest-compact")
OTHER_TOOLS = re.compile(r"(cursor|codex|copilot|antigravity|qoder|kiro|hermes-|claude-codex)", re.I)


def team_of(nom, utype, source, path):
    base = nom.rsplit("/", 1)[-1]
    if base in EXPLICIT_TEAM:
        return EXPLICIT_TEAM[base]
    if utype in ("schéma", "manifeste"):
        return "Amélioration"
    if utype == "règle":
        return "Construction"
    for team, rx in TEAM_KEYWORDS:
        if re.search(rx, base):
            return team
    if utype == "hook":
        return "Amélioration"
    return "Construction"


def lang_of(nom, path, text):
    for tok in re.split(r"[-/_.]", nom.lower()):
        if tok in LANGS:
            return tok
        if tok in LANG_ALIAS:
            return LANG_ALIAS[tok]
    m = re.search(r"^paths:\s*\n\s*-\s*[\"']\*\*/\*\.(\w+)", text, re.M)
    if m:
        return m.group(1)
    return "agnostique"


def triggers(desc, nom):
    out = []
    for m in re.finditer(r"(?:Use (?:this )?(?:when|for|PROACTIVELY|immediately|after|before|if)|MUST BE USED|Triggers? (?:on|when)|when)\s*(.{8,120}?)(?:[.;]|$)", desc, re.I):
        t = squeeze(m.group(0), 90)
        if t not in out:
            out.append(t)
        if len(out) == 2:
            break
    return out or [re.sub(r"[-_/]+", " ", nom.rsplit("/", 1)[-1])]


STOP = frozenset("a an the and or of to for in on with by from is are be as at it this that use when you your into any all can will not no do does if".split())


def words(s):
    return [w for w in re.findall(r"[a-z0-9àâçéèêëîïôûùüÿœ]+", (s or "").lower()) if w not in STOP and len(w) > 1]


# ----------------------------------------------------------------------------- construction
def sha_of(unit_files, lock):
    if len(unit_files) == 1:
        return lock[unit_files[0]]
    import hashlib
    h = hashlib.sha256()
    for f in sorted(unit_files):
        h.update((f + " " + lock[f] + "\n").encode("utf-8"))
    return h.hexdigest()


def load_arbitrage():
    if not os.path.isfile(ARBITRAGE):
        return {}
    with open(ARBITRAGE, encoding="utf-8") as fh:
        return json.load(fh)


def build_elements():
    lock = lock_files()
    groups = {}
    for path in sorted(lock):
        src, utype, nom, key = unit_of(path)
        groups.setdefault((src, utype, nom, key), []).append(path)
    arb = load_arbitrage()
    verr = arb.get("verrous", {})
    elements = []
    seen = {}
    for (src, utype, nom, key), files in groups.items():
        seen.setdefault((src, utype, nom), []).append(key)
    for (src, utype, nom, key), files in groups.items():
        if len(seen[(src, utype, nom)]) > 1:
            nom = nom + "." + key.rsplit(".", 1)[-1]          # meme nom, extensions differentes (ex. .sh / .ps1)
        mf = main_file(utype, key, files)
        text = read_text(mf, 6000)
        fm = frontmatter(text)
        desc = describe(mf, text, fm)
        eid = "%s:%s:%s" % (src, TYPECODE[utype], nom)
        team = team_of(nom, utype, src, mf)
        e = {"id": eid, "source": src, "type": utype, "nom": fm.get("name") or nom.rsplit("/", 1)[-1], "chemin": key if utype == "skill" else mf,
             "sha": sha_of(files, lock), "équipe": team, "phase": PHASE.get(team, "P4"),
             "déclencheurs": triggers(desc, nom),
             "entrées": [x.strip() for x in (fm.get("argument-hint") or fm.get("tools") or "chemin(s) du travail").split(",")][:8],
             "sorties": PRODUIT.get(team, "selon mission"),
             "coût_tokens": round(len(read_text(mf).replace("\r", "")) / CHARS_PER_TOKEN),
             "langage": lang_of(nom, mf, text), "modèle_conseillé": (fm.get("model") or "sonnet") if utype == "agent" else ("haiku" if utype in ("document", "licence", "schéma", "manifeste") else "sonnet"),
             "statut": "à la demande", "verrou": "", "doublon_de": "",
             "preuve": "LOCK.json#%s@%s ; classé par chemin+en-tête" % (mf, lock[mf][:12]),
             "description": desc, "fichiers": files, "partie_de": ""}
        if utype in ("document", "licence") or key.endswith(("LICENSE", ".gitattributes", "VERSION")):
            e["statut"] = "référencé"
        elif OTHER_TOOLS.search(os.path.basename(mf)) or (src == "ecc" and utype == "hook" and not nom.startswith("hermes/") and mf.endswith("-hooks.json")):
            e["statut"] = "référencé"          # adaptateurs d'autres outils : empreinte + lien, pas d'usage ici (CDC §7.1)
        elif eid in NOYAU:
            e["statut"] = "noyau"
        elements.append(e)
    # entrees de hooks.json (28) : elements sans fichier propre
    meta = json.loads(read_text("ecc/hooks/hooks.metadata.json"))["entries"]
    for event, entries in meta.items():
        for ent in entries:
            hid = ent["id"]
            team = "Sécurité" if re.search(r"gateguard|protection|no-verify|governance|mcp-health|hookify", hid) else "Amélioration"
            e = {"id": "ecc:hook:" + hid, "source": "ecc", "type": "hook", "nom": hid, "chemin": "ecc/hooks/hooks.json#" + hid,
                 "sha": ent.get("fingerprint", ""), "équipe": team, "phase": PHASE[team],
                 "déclencheurs": [event + " · " + hid.split(":")[1] if ":" in hid else event], "entrées": ["événement " + event],
                 "sorties": PRODUIT[team], "coût_tokens": 0, "langage": "node", "modèle_conseillé": "aucun (script)",
                 "statut": "noyau" if any(g in hid for g in GUARD_HOOKS) else "à la demande", "verrou": "", "doublon_de": "",
                 "preuve": "hooks.metadata.json#%s@%s" % (hid, ent.get("fingerprint", "")), "description": squeeze(ent.get("description", hid)),
                 "fichiers": [], "partie_de": "ecc:manifest:hooks"}
            elements.append(e)
    elements.sort(key=lambda e: e["id"])
    apply_locks(elements, verr)
    apply_arbitrage(elements, arb)
    for e in elements:
        for k in ("statut",):
            assert e[k] in STATUTS, (e["id"], e[k])
    return [{k: e[k] for k in KEY_ORDER} for e in elements]


# ----------------------------------------------------------------------------- verrous et arbitrage
PAID_ENV = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_(?:API_KEY|API_TOKEN|ACCESS_TOKEN|SECRET_KEY|AUTH_TOKEN|TOKEN|SECRET)\b")
PAID_WORDS = re.compile(r"\b(?:paid|pricing|credits?|subscription|per[- ]request|billed|billing plan|api key required|requires an? api key)\b", re.I)


def header_text(e):
    """En-tete scrute : frontmatter + 120 premieres lignes du fichier principal, sans le bloc « Prompt Defense »."""
    mf = e["fichiers"][0] if e["type"] != "skill" else next(f for f in e["fichiers"] if f.endswith("/SKILL.md") and f.count("/") == e["chemin"].count("/") + 1)
    txt = read_text(mf, 30000)
    txt = re.sub(r"## Prompt Defense Baseline.*?(?=\n## |\n# |\Z)", "", txt, flags=re.S)
    return "\n".join(txt.split("\n")[:120])


def verrou_candidates(elements):
    """{id: preuves} : motifs de cle d'API ou de service facture dans les en-tetes. Liste a RELIRE (arbitrage.json)."""
    out = {}
    for e in elements:
        if not e["fichiers"] or e["type"] not in ("skill", "commande", "agent"):
            continue
        h = header_text(e)
        ev = sorted(set(PAID_ENV.findall(h))) + sorted("~" + w.lower() for w in set(PAID_WORDS.findall(h)))
        if ev:
            out[e["id"]] = ev
    return out


def apply_locks(elements, verr):
    pats = [(re.compile(p["motif"]), p["raison"]) for p in verr.get("motifs", [])]
    valid = verr.get("valides", {})
    for e in elements:
        for rx, why in pats:
            if rx.search(e["id"]):
                e["statut"], e["verrou"] = "verrouillé", why
        if e["id"] in valid:
            e["statut"], e["verrou"] = "verrouillé", valid[e["id"]]


def apply_arbitrage(elements, arb):
    by = {e["id"]: e for e in elements}
    losers = []
    for g in arb.get("doublons_detectes", []):
        for m in g.get("doublons", []):
            losers.append((m, g["gagnant"]))
    for c in arb.get("conflits", []):
        for m in c.get("doublons", []):
            losers.append((m, c["gagnants"][0]))
    for m, w in losers:
        e = by.get(m)
        if e and by.get(w) and by[w]["statut"] == "verrouillé":
            e["statut"], e["verrou"] = "verrouillé", "alias de %s, verrouillé : %s" % (w, by[w]["verrou"])
        elif e and e["statut"] not in ("verrouillé", "référencé"):
            e["statut"], e["doublon_de"] = "doublon", w


def name_groups(elements):
    """Groupes de meme nom (agents, skills, commandes) entre sources ou entre types."""
    g = {}
    for e in elements:
        if e["type"] in ("agent", "skill", "commande") and e["fichiers"]:
            g.setdefault(e["nom"].lower(), []).append(e["id"])
    return {k: v for k, v in sorted(g.items()) if len(v) > 1}


def function_pairs(elements, thr=0.2):
    """Paires de MEME FONCTION entre sources differentes : similarite de Jaccard sur nom + description."""
    items = [(e["id"], e["source"], set(words(e["nom"].replace("-", " ") + " " + e["description"]))) for e in elements
             if e["type"] in ("agent", "skill", "commande") and e["fichiers"]]
    out = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if a[1] == b[1] or not a[2] or not b[2]:
                continue
            s = len(a[2] & b[2]) / float(len(a[2] | b[2]))
            if s >= thr:
                out.append((round(s, 2), a[0], b[0]))
    return sorted(out, reverse=True)


# ----------------------------------------------------------------------------- resolution (A7)
LINK = re.compile(r"\]\(([^)\s#]+?)(?:#[^)]*)?\)")
TICK = re.compile(r"`((?:references|scripts|templates|assets|agents|examples|rules)/[\w./-]+\.\w{1,5})`")


def resolve(e, lock=None):
    """Chemins et dependances d'un element, resolus PAR SCRIPT : fichiers presents et d'empreinte egale a LOCK.json,
    liens relatifs du texte existants dans les sources embarquees, interpreteurs requis. Ne lit que, n'execute rien."""
    import hashlib
    lock = lock or lock_files()
    missing, runtimes = [], set()
    for f in e["fichiers"]:
        full = lp(os.path.join(VENDOR, f))
        if not os.path.isfile(full):
            missing.append(f)
            continue
        with open(full, "rb") as fh:
            raw = fh.read()
        if hashlib.sha256(raw).hexdigest() != lock.get(f):
            missing.append(f + " (empreinte)")
        ext = f.rsplit(".", 1)[-1].lower()
        if ext in ("py",):
            runtimes.add("python")
        elif ext in ("js", "mjs", "cjs", "ts", "tsx"):
            runtimes.add("node")
        elif ext in ("sh", "bash"):
            runtimes.add("bash")
        elif ext == "ps1":
            runtimes.add("powershell")
        if ext == "md" and len(raw) < 400000:
            text = raw.decode("utf-8", "replace")
            text = re.sub(r"```.*?```", "", text, flags=re.S)
            base = os.path.dirname(f)
            unit_root = e["chemin"] if e["type"] == "skill" else base
            for ref in set(LINK.findall(text)):
                if re.match(r"^[a-z]+:|^/|^\$|^~|[<>{}*]", ref) or not re.search(r"\.\w{1,5}$", ref):
                    continue
                if not any(os.path.normpath(os.path.join(r0, ref)).replace("\\", "/") in lock for r0 in (base, f.split("/")[0])):
                    missing.append("%s -> %s" % (f, ref))
            for ref in set(TICK.findall(text)):
                if not any(os.path.normpath(os.path.join(r0, ref)).replace("\\", "/") in lock for r0 in (unit_root, base, f.split("/")[0])):
                    missing.append("%s -> %s" % (f, ref))
    return {"manquants": sorted(set(missing)), "interpreteurs": sorted(runtimes)}


def cmd_resolve(args):
    by = {e["id"]: e for e in load_catalog()}
    rc = 0
    for i in args:
        e = by.get(i)
        if not e:
            print("inconnu : " + i)
            rc = 1
            continue
        r = resolve(e)
        print("%s : %d manquants · interpréteurs %s" % (i, len(r["manquants"]), ",".join(r["interpreteurs"]) or "-"))
        for m in r["manquants"][:5]:
            print("  " + m)
        rc = rc or (1 if r["manquants"] else 0)
    return rc


# ----------------------------------------------------------------------------- commandes
BANNED = re.compile("tele" + "metry", re.I)      # I5 : le terme n'apparait nulle part dans nos fichiers, descriptions copiees comprises


def dump(elements):
    return BANNED.sub("usage-reporting", "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in elements))


def cmd_build(args):
    text = dump(build_elements())
    if "--check" in args:
        cur = open(JSONL, encoding="utf-8", newline="").read() if os.path.isfile(JSONL) else ""
        print("identique" if cur == text else "DIFFERENT")
        return 0 if cur == text else 1
    os.makedirs(CATDIR, exist_ok=True)
    with open(JSONL, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    n = text.count("\n")
    print("catalog.jsonl : %d elements" % n)
    return 0


def load_catalog():
    with open(JSONL, encoding="utf-8") as fh:
        return [json.loads(ln) for ln in fh if ln.strip()]


def independent_counts():
    """Comptage des sources sur le disque, par un autre chemin que build_elements (contre-comptage)."""
    c = {}
    def n(k, v):
        c[k] = v
    def lsf(sub):
        out = []
        for r, _d, fs in os.walk(lp(os.path.join(VENDOR, sub))):
            out += [os.path.join(r, f) for f in fs]
        return out
    n("ecc:agent", len([f for f in os.listdir(lp(os.path.join(VENDOR, "ecc/agents"))) if f.endswith(".md")]))
    n("ecc:command", len(os.listdir(lp(os.path.join(VENDOR, "ecc/commands")))))
    n("ecc:skill", len([d for d in os.listdir(lp(os.path.join(VENDOR, "ecc/skills"))) if os.path.isfile(lp(os.path.join(VENDOR, "ecc/skills", d, "SKILL.md")))]))
    n("ecc:schema", len(os.listdir(lp(os.path.join(VENDOR, "ecc/schemas")))))
    rules = [f for f in lsf("ecc/rules")]
    n("ecc:rules_files", len(rules))
    n("mattpocock:skill", len([f for f in lsf("mattpocock/skills") if f.endswith("SKILL.md")]))
    n("ponytail:skill", len([f for f in lsf("ponytail/skills") if f.endswith("SKILL.md")]))
    n("ponytail:command", len(os.listdir(lp(os.path.join(VENDOR, "ponytail/commands")))))
    n("vercel:script", len(os.listdir(lp(os.path.join(VENDOR, "vercel-skills/src")))))
    n("ecc:hook_entries", sum(len(v) for v in json.loads(read_text("ecc/hooks/hooks.metadata.json"))["entries"].values()))
    return c


def cmd_audit(args):
    bad = []
    lock = lock_files()
    els = load_catalog()
    ids = [e["id"] for e in els]
    if len(ids) != len(set(ids)):
        bad.append("identifiants en double")
    covered = {}
    for e in els:
        for f in e["fichiers"]:
            covered[f] = covered.get(f, 0) + 1
    miss = sorted(set(lock) - set(covered))
    extra = sorted(set(covered) - set(lock))
    twice = sorted(f for f, k in covered.items() if k > 1)
    disk = set()
    for r, _d, fs in os.walk(lp(VENDOR)):
        for f in fs:
            rel = os.path.relpath(os.path.join(r, f), lp(VENDOR)).replace("\\", "/")
            if rel not in ("LOCK.json", "THIRD_PARTY_NOTICES.md"):
                disk.add(rel)
    d_miss, d_extra = sorted(disk - set(lock)), sorted(set(lock) - disk)
    ecart = len(miss) + len(extra) + len(twice) + len(d_miss) + len(d_extra)
    if ecart:
        bad.append("écart couverture : %d (non classés %d, inconnus %d, doubles %d, disque-hors-LOCK %d, LOCK-hors-disque %d)"
                   % (ecart, len(miss), len(extra), len(twice), len(d_miss), len(d_extra)))
    unclassified = [e["id"] for e in els if e.get("statut") not in STATUTS or not e.get("équipe") or not e.get("description")]
    if unclassified:
        bad.append("non classés : %d (%s)" % (len(unclassified), ", ".join(unclassified[:5])))
    ic = independent_counts()
    cnt = {}
    for e in els:
        if e["fichiers"] or e["type"] == "hook":
            cnt[(e["source"], e["type"])] = cnt.get((e["source"], e["type"]), 0) + 1
    checks = [("ecc:agent", cnt.get(("ecc", "agent"), 0)), ("ecc:command", cnt.get(("ecc", "commande"), 0)), ("ecc:skill", cnt.get(("ecc", "skill"), 0)),
              ("ecc:schema", cnt.get(("ecc", "schéma"), 0)), ("mattpocock:skill", cnt.get(("mattpocock", "skill"), 0)),
              ("ponytail:skill", cnt.get(("ponytail", "skill"), 0)), ("ponytail:command", cnt.get(("ponytail", "commande"), 0)),
              ("vercel:script", cnt.get(("vercel-skills", "script"), 0)),
              ("ecc:hook_entries", len([e for e in els if e["partie_de"] == "ecc:manifest:hooks"]))]
    for k, got in checks:
        if ic[k] != got:
            bad.append("contre-comptage %s : sources %d, catalogue %d" % (k, ic[k], got))
    rules_el = len([e for e in els if e["source"] == "ecc" and e["type"] in ("règle",) or e["id"] == "ecc:doc:rules/README"])
    docs_in_rules = len([e for e in els if e["id"].startswith("ecc:doc:rules/")])
    rules_cat = len([e for e in els if e["id"].startswith(("ecc:rule:", "ecc:doc:rules/"))])
    if ic["ecc:rules_files"] != rules_cat:
        bad.append("contre-comptage règles : sources %d, catalogue %d" % (ic["ecc:rules_files"], rules_cat))
    if ic["ecc:hook_entries"] != 28:
        bad.append("hooks.json : %d entrées au lieu de 28" % ic["ecc:hook_entries"])
    arb = load_arbitrage()
    by = {e["id"]: e for e in els}
    for c in arb.get("conflits", []):
        for m in c.get("gagnants", []) + c.get("complements", []) + c.get("doublons", []):
            if m not in by:
                bad.append("arbitrage : élément inconnu %s" % m)
    decided = set()
    for g in arb.get("doublons_detectes", []):
        decided.add(g["nom"])
        for m in [g["gagnant"]] + g.get("doublons", []):
            if m not in by:
                bad.append("arbitrage : élément inconnu %s" % m)
    for g in arb.get("homonymes_distincts", []):
        decided.add(g["nom"])
    for nom, members in name_groups(els).items():
        if nom not in decided and not any(nom in (c.get("noms") or []) for c in arb.get("conflits", [])):
            bad.append("doublon non arbitré : %s %s" % (nom, members))
    fp = {tuple(sorted((a, b))) for a, b in arb.get("fonctions_arbitrees", [])}
    for s, a, b in function_pairs(els):
        if tuple(sorted((a, b))) not in fp:
            bad.append("même fonction non arbitrée : %s ~ %s (%.2f)" % (a, b, s))
    v = arb.get("verrous", {})
    reviewed = set(v.get("valides", {})) | set(v.get("refuses", {}))
    for cid in verrou_candidates(els):
        if cid not in reviewed and by[cid]["statut"] != "verrouillé":
            bad.append("verrou à relire : %s" % cid)
    for m in list(v.get("valides", {})) + list(v.get("refuses", {})):
        if m not in by:
            bad.append("verrou : élément inconnu %s" % m)
    for e in els:
        if e["statut"] == "verrouillé" and not e["verrou"]:
            bad.append("verrou sans raison : %s" % e["id"])
        if e["statut"] == "doublon" and e["doublon_de"] not in by:
            bad.append("doublon sans gagnant : %s" % e["id"])
    if load_catalog() != json.loads("[" + ",".join(dump(build_elements()).strip().split("\n")) + "]"):
        bad.append("catalog.jsonl périmé : relancer `catalog.py build`")
    st = {}
    for e in els:
        st[e["statut"]] = st.get(e["statut"], 0) + 1
    print("éléments %d · fichiers LOCK %d couverts · écart %d · non classés %d · statuts %s"
          % (len(els), len(lock) - len(miss), ecart, len(unclassified), json.dumps(st, ensure_ascii=False, sort_keys=True)))
    for b in bad:
        print("DEFAUT : " + b)
    print("audit : " + ("OK" if not bad else "ECHEC (%d)" % len(bad)))
    return 0 if not bad else 1


def search(query, els, n=5):
    toks = words(query)
    if not toks:
        return []
    try:
        import sqlite3
        db = sqlite3.connect(":memory:")
        db.execute("create virtual table t using fts5(id unindexed, nom, description, decl, chemin, tokenize='unicode61 remove_diacritics 2')")
        db.executemany("insert into t values (?,?,?,?,?)", [(e["id"], e["nom"].replace("-", " "), e["description"], " ".join(e["déclencheurs"]),
                                                              re.sub(r"[-_/.#:]+", " ", e["chemin"])) for e in els])
        q = " OR ".join('"%s"' % t.replace('"', "") for t in toks)
        rows = db.execute("select id from t where t match ? order by bm25(t, 0.0, 6.0, 2.0, 1.0, 0.5) limit ?", (q, n)).fetchall()
        db.close()
        return [r[0] for r in rows]
    except Exception:       # FTS5 absent : score par mots
        sc = []
        for e in els:
            bag = set(words(e["nom"].replace("-", " "))) | set(words(e["description"])) | set(words(" ".join(e["déclencheurs"])))
            s = sum((3 if t in words(e["nom"]) else 1) for t in toks if t in bag)
            if s:
                sc.append((-s, e["id"]))
        return [i for _s, i in sorted(sc)[:n]]


def cmd_search(args):
    n, q = 5, []
    it = iter(args)
    for a in it:
        if a == "-n":
            n = min(5, int(next(it)))
        else:
            q.append(a)
    els = load_catalog()
    by = {e["id"]: e for e in els}
    ids = search(" ".join(q), els, n)
    if not ids:
        print("aucun résultat")
        return 0
    for i in ids:
        e = by[i]
        tag = e["statut"] + (" " + e["verrou"][:30] if e["verrou"] else "") + (" -> " + e["doublon_de"] if e["doublon_de"] else "")
        print("%s | %s | %s" % (i, tag, squeeze(e["description"], 90)))
    return 0


def cmd_verrous(args):
    els = build_elements()
    c = verrou_candidates(els)
    for k, v in sorted(c.items()):
        print("%s : %s" % (k, ", ".join(v)))
    print("%d candidats" % len(c))
    return 0


def cmd_doublons(args):
    els = build_elements()
    for k, v in name_groups(els).items():
        print("NOM  %s : %s" % (k, " ; ".join(v)))
    for s, a, b in function_pairs(els):
        print("FONC %.2f %s ~ %s" % (s, a, b))
    return 0


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    cmds = {"build": cmd_build, "audit": cmd_audit, "search": cmd_search, "verrous": cmd_verrous, "doublons": cmd_doublons, "resolve": cmd_resolve}
    if len(argv) > 1 and argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(argv) < 2 or argv[1] not in cmds:
        print(__doc__)
        return 2
    return cmds[argv[1]](argv[2:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
