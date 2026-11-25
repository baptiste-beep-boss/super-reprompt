# -*- coding: utf-8 -*-
"""vault.py : acces direct au second cerveau Obsidian (lot L3). Bibliotheque standard, aucun reseau, aucun MCP,
aucune application Obsidian requise.

  vault.py index [--full]            index SQLite FTS5 incremental (date + empreinte), HORS du vault
  vault.py search "mots" [--stats]   8 lignes max : note | titre | extrait (repli « un des mots » si < 3 resultats)
  vault.py brief <slug>              tout pour reprendre un projet (< 800 tokens)
  vault.py log <slug> [--kind K] ... une ligne de journal : 0 token, ajout seul, sous verrou fichier
  vault.py lint [--slug S|--scope P] orphelines, liens morts, notes sans MOC, doublons ; code 1 si defaut
  vault.py commit <slug> [-m MSG]    commit local des SEULS chemins du projet (jamais d'ajout global, jamais de push)
  vault.py init <slug>               cree les notes du projet (idempotent)

Vault : --vault, sinon SR_VAULT_PATH, sinon CLAUDE_PLUGIN_OPTION_VAULT_PATH (userConfig.vault_path).
Sans vault : tout va dans <cwd>/.super-reprompt/<slug>/memoire/.
Base d'index : SR_VAULT_DB, sinon ~/.claude/super-reprompt/vault-index/. Jamais dans le vault.

Codes de sortie : 0 ok · 1 defaut (lint) ou echec git · 2 usage / refus · 3 index ou projet absent.
Latence : `search` n'importe que os, sys et sqlite3 (mesure L3 : voir PREUVES / compte rendu), les autres modules
(json, re, hashlib, subprocess, argparse) ne sont charges que par les commandes qui en ont besoin.
"""
import os
import sys

SKIP_DIRS = frozenset((".git", ".obsidian", "graph", "node_modules", ".trash"))
MAX_LINES = 8
LINE_CHARS = 160
BRIEF_CHARS = 2800          # 800 tokens a 3,7 caracteres/token = 2960 : marge
SLUG_OK = "abcdefghijklmnopqrstuvwxyz0123456789-"


def out(s=""):
    sys.stdout.write(s + "\n")


def err(s):
    sys.stderr.write(s + "\n")


# ----------------------------------------------------------------------------- contexte
class Ctx:
    def __init__(self, root, vault):
        self.root = root          # racine scannee
        self.vault = vault        # True si un vrai vault est configure

    def project_dir(self, slug):
        if self.vault:
            return os.path.join(self.root, "projets", slug)
        return os.path.join(self.root, slug, "memoire")

    def moc_dir(self):
        return os.path.join(self.root, "projets") if self.vault else None


def resolve_ctx(vault_arg=None):
    v = vault_arg or os.environ.get("SR_VAULT_PATH") or os.environ.get("CLAUDE_PLUGIN_OPTION_VAULT_PATH") or ""
    if v:
        if not os.path.isdir(v):
            err("vault introuvable : %s" % v)
            sys.exit(2)
        return Ctx(os.path.abspath(v), True)
    return Ctx(os.path.join(os.getcwd(), ".super-reprompt"), False)


def check_slug(slug):
    if not slug or slug[0] == "-" or len(slug) > 40 or any(c not in SLUG_OK for c in slug):
        err("slug invalide (a-z, 0-9, tiret ; 40 max) : %r" % slug)
        sys.exit(2)
    return slug


def state_dir():
    d = os.path.join(os.path.expanduser("~"), ".claude", "super-reprompt", "vault-index")
    return d


def db_path(ctx):
    p = os.environ.get("SR_VAULT_DB")
    if p:
        return p
    import zlib
    tag = "%08x" % zlib.crc32(ctx.root.lower().encode("utf-8"))
    return os.path.join(state_dir(), tag + ".sqlite")


def lock_path(ctx, slug):
    import zlib
    tag = "%08x" % zlib.crc32((ctx.root.lower() + "|" + slug).encode("utf-8"))
    d = os.path.join(state_dir(), "locks")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, tag + ".lock")


def Lock(path, timeout=20.0, stale=60.0):
    """Single lock implementation (contracts.Lock, lot 1 V3.1): also survives the Windows PermissionError raised
    while another process deletes the lock file. Imported lazily so `search` keeps importing only os, sys, sqlite3."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import contracts
    return contracts.Lock(path, timeout=timeout, stale=stale)


# ----------------------------------------------------------------------------- scan / lecture
def read_text(p):
    with open(p, "rb") as fh:
        return fh.read().decode("utf-8", "replace")


def scan(ctx):
    """[(relpath, mtime_ns, size)] des .md ; en repli, seulement sous .../memoire/."""
    res = []
    for r, ds, fs in os.walk(ctx.root):
        ds[:] = [d for d in ds if d not in SKIP_DIRS]
        for f in fs:
            if not f.endswith(".md"):
                continue
            p = os.path.join(r, f)
            rel = os.path.relpath(p, ctx.root).replace(os.sep, "/")
            if not ctx.vault and "/memoire/" not in "/" + rel:
                continue
            st = os.stat(p)
            res.append((rel, st.st_mtime_ns, st.st_size))
    return res


def title_of(txt, rel):
    for line in txt.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return os.path.basename(rel)[:-3]


# ----------------------------------------------------------------------------- index / search
def open_db(ctx, create):
    try:
        import _sqlite3 as sqlite3      # saute sqlite3.dbapi2 (collections, datetime...) : demarrage a froid plus court
    except ImportError:                 # pragma: no cover - interpreteur sans module C
        import sqlite3
    p = db_path(ctx)
    if not create and not os.path.exists(p):
        return None
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE IF NOT EXISTS meta(path TEXT PRIMARY KEY, mtime INTEGER, size INTEGER, sha TEXT)")
    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS notes USING fts5(path UNINDEXED, title, body, "
              "tokenize='unicode61 remove_diacritics 2')")
    return c


def cmd_index(ctx, full=False):
    import hashlib
    import time
    t0 = time.perf_counter()
    c = open_db(ctx, True)
    c.commit()
    c.execute("PRAGMA synchronous=OFF")                 # before any write: a PRAGMA inside the implicit transaction fails
    if full:
        c.execute("DELETE FROM meta")
        c.execute("DELETE FROM notes")
    have = {p: (m, s, h) for p, m, s, h in c.execute("SELECT path,mtime,size,sha FROM meta")}
    cur = scan(ctx)
    seen, n_idx, n_touch = set(), 0, 0
    for rel, m, s in cur:
        seen.add(rel)
        old = have.get(rel)
        if old and old[0] == m and old[1] == s:
            continue
        txt = read_text(os.path.join(ctx.root, rel.replace("/", os.sep)))
        sha = hashlib.sha256(txt.encode("utf-8")).hexdigest()
        if old and old[2] == sha:                       # meme empreinte : on ne met a jour que la date
            c.execute("UPDATE meta SET mtime=?, size=? WHERE path=?", (m, s, rel))
            n_touch += 1
            continue
        c.execute("DELETE FROM notes WHERE path=?", (rel,))
        c.execute("INSERT INTO notes(path,title,body) VALUES(?,?,?)", (rel, title_of(txt, rel), txt))
        c.execute("INSERT OR REPLACE INTO meta VALUES(?,?,?,?)", (rel, m, s, sha))
        n_idx += 1
    gone = [p for p in have if p not in seen]
    for p in gone:
        c.execute("DELETE FROM notes WHERE path=?", (p,))
        c.execute("DELETE FROM meta WHERE path=?", (p,))
    c.commit()
    c.close()
    out("index : %d indexees, %d retirees, %d datees seulement, %d notes, %.2f s" %
        (n_idx, len(gone), n_touch, len(cur), time.perf_counter() - t0))
    return 0


def tokens(q):
    res, cur = [], []
    for ch in q:
        if ch.isalnum() or ch == "_":
            cur.append(ch)
        elif cur:
            res.append("".join(cur))
            cur = []
    if cur:
        res.append("".join(cur))
    return res


def fmt(path, title, snip):
    path = path if len(path) <= 55 else "…" + path[-54:]
    title = " ".join(title.split())[:40]
    line = "%s | %s | %s" % (path, title, " ".join(snip.split()))
    return line if len(line) <= LINE_CHARS else line[:LINE_CHARS - 1] + "…"


SQL = ("SELECT path, title, snippet(notes,2,'[',']','…',10) FROM notes WHERE notes MATCH ? "
       "ORDER BY bm25(notes,0,5,1) LIMIT ?")


def cmd_search(ctx, query, stats=False):
    import time
    toks = tokens(query)
    if not toks:
        err("requete vide")
        return 2
    t0 = time.perf_counter()
    c = open_db(ctx, False)
    if c is None:
        err("index absent : lancer `vault.py index` d'abord")
        return 3
    rows = c.execute(SQL, (" ".join('"%s"' % t for t in toks), MAX_LINES)).fetchall()
    mode = "ET"
    if len(rows) < 3 and len(toks) > 1:                 # repli « un des mots » (bm25), lecon L0
        rows = c.execute(SQL, (" OR ".join('"%s"' % t for t in toks), MAX_LINES)).fetchall()
        mode = "OU"
    for p, t, s in rows[:MAX_LINES]:
        out(fmt(p, t, s))
    if stats:
        err("%d resultats (%s) en %.1f ms (requete en processus)" % (len(rows), mode, (time.perf_counter() - t0) * 1000))
    return 0


# ----------------------------------------------------------------------------- projet : notes
def now_utc():
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def today():
    import time
    return time.strftime("%Y-%m-%d", time.gmtime())


def templates(slug):
    t = "%s-00-tableau" % slug
    j, d, le = "%s-journal" % slug, "%s-decisions" % slug, "%s-lecons" % slug
    day = today()
    return {
        t: ("---\ntype: projet\nstatut: en cours\navancement: 0\nphase: P0\nreste: a definir\ncap: a definir\ncree: %s\n---\n"
            "# %s : tableau de bord\n\nSuivi par [[%s]], [[%s]] et [[%s]] ; rattache a [[MOC-projets]].\n" % (day, slug, j, d, le)),
        j: ("---\ntype: journal\nprojet: %s\n---\n# %s : journal\n\nGenere par `vault.py log` (ajout seul). Tableau : [[%s]] · [[MOC-projets]].\n\n"
            % (slug, slug, t)),
        d: ("---\ntype: decisions\nprojet: %s\n---\n# %s : decisions\n\nUne ligne par decision : `- AAAA-MM-JJ · choix — raison (ecarte : …) [qui]`. "
            "Tableau : [[%s]] · [[%s]] · [[MOC-projets]].\n\n" % (slug, slug, t, j)),
        le: ("---\ntype: lecons\nprojet: %s\n---\n# %s : lecons\n\nErreurs et regles d'action, datees. Voir [[%s]] · [[%s]] · [[MOC-projets]].\n\n"
             % (slug, slug, t, d)),
    }


BASE = ('filters:\n  and:\n    - file.name.endsWith("-00-tableau")\nviews:\n  - type: table\n    name: Projets\n'
        '    order:\n      - file.name\n      - statut\n      - avancement\n      - phase\n      - reste\n      - cap\n'
        '    sort:\n      - property: avancement\n        direction: DESC\n')


def write_new(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return True


def append(path, text):
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def ensure_project(ctx, slug):
    """Cree ce qui manque ; ne modifie jamais une note existante, sauf ajout d'une ligne au MOC. Sous verrou."""
    d = ctx.project_dir(slug)
    created = []
    with Lock(lock_path(ctx, slug)):
        for name, text in templates(slug).items():
            if write_new(os.path.join(d, name + ".md"), text):
                created.append(name)
        md = ctx.moc_dir()
        if md:
            moc = os.path.join(md, "MOC-projets.md")
            line = "- [[%s-00-tableau]]\n" % slug
            write_new(moc, "---\ntype: moc\n---\n# MOC projets\n\nTous les projets suivis (vue : Projets.base).\n\n")
            if line not in read_text(moc):
                append(moc, line)
            write_new(os.path.join(md, "Projets.base"), BASE)
    return created


def cmd_init(ctx, slug):
    created = ensure_project(ctx, check_slug(slug))
    out("projet %s : %d notes creees dans %s" % (slug, len(created), ctx.project_dir(slug)))
    return 0


KINDS = ("note", "tache", "decision", "blocage", "phase", "lecon", "vigie", "budget")   # vigie, budget: L8 super-manager loop
SUSPECT = ("key", "secret", "token", "passw", "private", "sk-", "akia", "xox", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "eyj", "0x")


def looks_secret(text):
    """Pre-filtre sans `re` (demarrage a froid) : la regle complete (_lib.SECRET_PATTERNS) ne s'applique que si le texte est suspect."""
    low = text.lower()
    if not (any(w in low for w in SUSPECT) or any(len(t) >= 16 for t in text.split())):
        return False
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from _lib import SECRET_PATTERNS
    return any(pat.search(text) for pat, _label in SECRET_PATTERNS)


def jstr(s):
    out_ = []
    for ch in s:
        o = ord(ch)
        out_.append({'"': '\\"', "\\": "\\\\"}.get(ch) or (ch if o >= 32 else "\\u%04x" % o))
    return '"' + "".join(out_) + '"'


def cmd_log(ctx, slug, kind, text):
    check_slug(slug)
    text = " ".join(text.split())
    if not text:
        err("texte vide")
        return 2
    if looks_secret(text):
        err("refus : le texte ressemble a un secret (jamais de secret dans le cerveau)")
        return 2
    ts = now_utc()
    mdir = os.path.join(os.getcwd(), ".super-reprompt", slug)
    d = ctx.project_dir(slug)
    if not all(os.path.exists(os.path.join(d, n + ".md")) for n in templates(slug)):
        ensure_project(ctx, slug)
    import re
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import contracts                     # unified mission journal events.ndjson (lot 1 V3.1)
    with Lock(lock_path(ctx, slug)):
        contracts.emit(mdir, "log." + (re.sub(r"[^a-z0-9_]", "_", kind.lower()) or "note"), "manager",
                       {"kind": kind, "text": text}, mission_id=slug, timestamp=ts)
        append(os.path.join(d, slug + "-journal.md"), "- %s · %s · %s\n" % (ts, kind, text))
    return 0


# ----------------------------------------------------------------------------- brief
def front(txt):
    if not txt.startswith("---"):
        return {}
    end = txt.find("\n---", 3)
    res = {}
    for line in txt[3:end if end > 0 else 0].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            res[k.strip()] = v.strip()
    return res


def last_items(path, prefix, n):
    if not os.path.exists(path):
        return []
    items = [l.strip() for l in read_text(path).splitlines() if l.startswith(prefix)]
    return items[-n:]


def clip(s, n):
    return s if len(s) <= n else s[:n - 1] + "…"


def cmd_brief(ctx, slug):
    check_slug(slug)
    d = ctx.project_dir(slug)
    tab = os.path.join(d, slug + "-00-tableau.md")
    if not os.path.exists(tab):
        err("projet absent : %s" % slug)
        return 3
    fm = front(read_text(tab))
    lines = ["# brief %s" % slug,
             "statut: %s | avancement: %s | phase: %s | cap: %s" % tuple(clip(fm.get(k, "?"), 60) for k in ("statut", "avancement", "phase", "cap")),
             "reste: %s" % clip(fm.get("reste", "?"), 200)]
    for title, fn, pre, n, w in (("Decisions (5 dernieres)", "decisions", "- ", 5, 220), ("Lecons (3 dernieres)", "lecons", "- ", 3, 220),
                                 ("Journal (8 dernieres lignes)", "journal", "- ", 8, 170)):
        its = last_items(os.path.join(d, "%s-%s.md" % (slug, fn)), pre, n)
        if its:
            lines.append("## " + title)
            lines += [clip(i, w) for i in its]
    ph = sorted(f[:-3] for f in os.listdir(d) if f.startswith(slug + "-phase-") and f.endswith(".md"))
    if ph:
        lines.append("## Phases : " + ", ".join("[[%s]]" % p for p in ph[-6:]))
    res = "\n".join(lines)
    out(res if len(res) <= BRIEF_CHARS else res[:BRIEF_CHARS - 1] + "…")
    return 0


# ----------------------------------------------------------------------------- lint
def cmd_lint(ctx, slug=None, scope=None, max_lines=50, min_links=2):
    import hashlib
    import re
    wiki = re.compile(r"\[\[([^\]\|#\n]+)(?:#[^\]\|\n]*)?(?:\|[^\]\n]*)?\]\]")
    code = re.compile(r"```.*?```|`[^`\n]*`", re.S)
    notes = {}                       # rel -> (texte, liens)
    allfiles = set()
    for r, ds, fs in os.walk(ctx.root):
        ds[:] = [d for d in ds if d not in SKIP_DIRS]
        for f in fs:
            allfiles.add(f.lower())
    for rel, _m, _s in scan(ctx):
        txt = read_text(os.path.join(ctx.root, rel.replace("/", os.sep)))
        links = [x.strip() for x in wiki.findall(code.sub("", txt))]
        notes[rel] = (txt, links)
    by_name, by_path = {}, {}
    for rel in notes:
        by_name.setdefault(os.path.basename(rel)[:-3].lower(), []).append(rel)
        by_path[rel[:-3].lower()] = rel

    def resolve(t):
        t = t.replace("\\", "/")
        low = t.lower()
        if low.endswith(".md"):
            low = low[:-3]
        if "/" in low:
            hit = by_path.get(low)
            if hit:
                return hit
            tail = [p for k, p in by_path.items() if k.endswith("/" + low)]
            return tail[0] if tail else None
        if low in by_name:
            return by_name[low][0]
        return "#fichier" if (t.lower() in allfiles) else None

    inbound = {rel: set() for rel in notes}
    outgoing = {rel: set() for rel in notes}
    dead = []
    for rel, (_txt, links) in notes.items():
        for t in links:
            tgt = resolve(t)
            if tgt is None:
                dead.append((rel, t))
            elif tgt in notes and tgt != rel:
                inbound[tgt].add(rel)
                outgoing[rel].add(tgt)

    def is_moc(rel):
        return "moc" in os.path.basename(rel)[:-3].lower()

    if slug:
        prefix = "projets/%s/" % check_slug(slug) if ctx.vault else "%s/memoire/" % slug
    else:
        prefix = scope
    defects = []
    for rel in sorted(notes):
        base = os.path.basename(rel)[:-3]
        if not is_moc(rel) and not base.lower().startswith("00-") and not inbound[rel]:
            defects.append(("orpheline", rel, "aucun lien entrant"))
        if not is_moc(rel) and not any(is_moc(o) for o in outgoing[rel] | inbound[rel]):
            defects.append(("sans-moc", rel, "aucun MOC lie"))
        if prefix and rel.startswith(prefix) and len(notes[rel][1]) < min_links:
            defects.append(("liens<2", rel, "%d wikilien(s)" % len(notes[rel][1])))
    for rel, t in dead:
        defects.append(("lien-mort", rel, "[[%s]]" % t))
    h = {}
    for rel, (txt, _l) in notes.items():
        norm = " ".join(txt.lower().split())
        if len(norm) > 40:
            h.setdefault(hashlib.sha256(norm.encode("utf-8")).hexdigest(), []).append(rel)
    for rels in h.values():
        if len(rels) > 1:
            for rel in rels:
                defects.append(("doublon-contenu", rel, "= " + ", ".join(x for x in rels if x != rel)[:80]))
    for name, rels in by_name.items():
        if len(rels) > 1:
            for rel in rels:
                defects.append(("doublon-nom", rel, "meme nom que " + ", ".join(x for x in rels if x != rel)[:80]))
    if prefix:
        defects = [d for d in defects if d[1].startswith(prefix)]
    shown = defects[:max_lines]
    for k, rel, det in shown:
        out("%s | %s | %s" % (k, rel, det))
    if len(defects) > len(shown):
        out("… +%d autres" % (len(defects) - len(shown)))
    kinds = {}
    for k, _r, _d in defects:
        kinds[k] = kinds.get(k, 0) + 1
    out("lint : %d notes, %d defauts %s%s" % (len(notes), len(defects), kinds if kinds else "",
                                               (" (perimetre %s)" % prefix) if prefix else ""))
    return 1 if defects else 0


# ----------------------------------------------------------------------------- commit
def cmd_commit(ctx, slug, msg, with_moc=False):
    check_slug(slug)
    if not ctx.vault:
        out("pas de vault configure : rien a committer (les notes restent dans .super-reprompt/%s/memoire/)" % slug)
        return 0
    import subprocess
    paths = ["projets/%s/" % slug]
    if with_moc:
        paths += ["projets/MOC-projets.md", "projets/Projets.base"]
    paths = [p for p in paths if os.path.exists(os.path.join(ctx.root, p))]

    def git(*a):
        return subprocess.run(["git", "-C", ctx.root] + list(a), capture_output=True, text=True, encoding="utf-8")

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        err("le vault n'est pas un depot git")
        return 1
    r = git("add", "--", *paths)
    if r.returncode:
        err(r.stderr.strip())
        return 1
    if git("diff", "--cached", "--quiet", "--", *paths).returncode == 0:
        out("rien a committer pour %s" % slug)
        return 0
    r = git("commit", "-m", msg or "memoire(%s): mise a jour %s" % (slug, today()), "--", *paths)
    if r.returncode:
        err((r.stderr or r.stdout).strip())
        return 1
    out(r.stdout.strip().splitlines()[0])
    return 0


# ----------------------------------------------------------------------------- main
def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        out(__doc__)
        return 0 if len(argv) >= 2 else 2
    cmd, rest = argv[1], argv[2:]
    vault_arg = None
    if "--vault" in rest:
        i = rest.index("--vault")
        vault_arg = rest[i + 1] if i + 1 < len(rest) else None
        rest = rest[:i] + rest[i + 2:]
    ctx = resolve_ctx(vault_arg)
    if cmd == "search":                                  # chemin chaud : pas d'argparse
        stats = "--stats" in rest
        return cmd_search(ctx, " ".join(a for a in rest if a != "--stats"), stats)
    if cmd == "log":                                     # chemin chaud : pas d'argparse
        kind = "note"
        if "--kind" in rest:
            i = rest.index("--kind")
            kind = rest[i + 1] if i + 1 < len(rest) else ""
            rest = rest[:i] + rest[i + 2:]
        if kind not in KINDS or len(rest) < 2:
            err("usage : vault.py log <slug> [--kind %s] texte" % "|".join(KINDS))
            return 2
        check_slug(rest[0])
        try:
            return cmd_log(ctx, rest[0], kind, " ".join(rest[1:]))
        except TimeoutError as e:
            err(str(e))
            return 1
    import argparse
    ap = argparse.ArgumentParser(prog="vault.py " + cmd)
    if cmd == "index":
        ap.add_argument("--full", action="store_true")
        a = ap.parse_args(rest)
        return cmd_index(ctx, a.full)
    if cmd in ("init", "brief"):
        ap.add_argument("slug")
        a = ap.parse_args(rest)
        return cmd_init(ctx, a.slug) if cmd == "init" else cmd_brief(ctx, a.slug)
    if cmd == "lint":
        ap.add_argument("--slug")
        ap.add_argument("--scope")
        ap.add_argument("--max", type=int, default=50)
        a = ap.parse_args(rest)
        return cmd_lint(ctx, a.slug, a.scope, a.max)
    if cmd == "commit":
        ap.add_argument("slug")
        ap.add_argument("-m", "--message")
        ap.add_argument("--with-moc", action="store_true")
        a = ap.parse_args(rest)
        return cmd_commit(ctx, a.slug, a.message, a.with_moc)
    err("commande inconnue : %s" % cmd)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as e:                                # jamais de trace brute pour l'utilisateur
        sys.stderr.write("vault.py : %s: %s\n" % (type(e).__name__, e))
        sys.exit(1)
