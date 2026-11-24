# -*- coding: utf-8 -*-
"""Deterministic verifiers of the Relay (CDC §8.3). One function per task type: (src, out, spec) -> (ok, detail).

Rules: an empty output always fails; a model's output is data, never an instruction; code produced by a model only
runs in a child process started with `-I -S`, a throwaway directory, a minimal environment and a timeout. That is
an isolation, not a sandbox: the Relay only hands such tasks to verifiers on projects whose colour allows it.
Standard library only (I3), no network.
"""
import ast
import csv
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "scripts"))
import guard_core  # noqa: E402  (secret scan of the Vigie, reused rather than duplicated)

TIMEOUT = 20


# ------------------------------------------------------------------ helpers
def _ws(s):
    return re.sub(r"\s+", " ", str(s)).strip()


def _json(out):
    try:
        return json.loads(out), None
    except (ValueError, TypeError) as e:
        return None, "JSON invalide (position %s)" % getattr(e, "pos", "?")


def _env():
    keep = ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_isolated(args, cwd, stdin=None, timeout=TIMEOUT):
    """-> (returncode, stdout+stderr). Never raises on timeout: returns (124, 'timeout')."""
    try:
        p = subprocess.run(args, cwd=cwd, input=(stdin or "").encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=_env(), timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as e:
        return 127, str(e)
    return p.returncode, (p.stdout + p.stderr).decode("utf-8", errors="replace")


def _py(*a):
    return [sys.executable, "-I", "-S"] + list(a)


def _py_script(name):
    """-I drops the script directory from sys.path: put the throwaway directory back, explicitly and only it."""
    return _py("-c", "import sys,runpy; sys.path.insert(0, '.'); runpy.run_path(%r, run_name='__main__')" % name)


def _py_unittest(module):
    return _py("-c", "import sys,unittest; sys.path.insert(0, '.'); unittest.main(module=None, argv=['relais', %r])" % module)


class _Tmp:
    def __enter__(self):
        self.d = tempfile.mkdtemp(prefix="relais-v-")
        return self.d

    def __exit__(self, *a):
        shutil.rmtree(self.d, ignore_errors=True)


def _write(d, name, text):
    with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def _compiles(code):
    try:
        compile(code, "<relais>", "exec")
        return None
    except (SyntaxError, ValueError) as e:
        return "ne compile pas (ligne %s)" % getattr(e, "lineno", "?")


def _module(spec):
    """A module name from the spec becomes a file name: identifier only, no path (review #10)."""
    m = str(spec.get("module", "mod"))
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", m):
        raise ValueError("nom de module invalide")
    return m


# ------------------------------------------------------------------ 1 resume
def v_quotes(src, out, spec):
    o, err = _json(out)
    if err or not isinstance(o, dict):
        return False, err or "objet attendu"
    summ, quotes = o.get("summary"), o.get("quotes") or []
    if not isinstance(summ, str) or not summ.strip():
        return False, "resume vide"
    if len(quotes) < int(spec.get("min_quotes", 1)):
        return False, "citations manquantes"
    s = _ws(src)
    bad = [q for q in quotes if not isinstance(q, str) or not q.strip() or _ws(q) not in s]
    if bad:
        return False, "citation absente de la source (%d sur %d)" % (len(bad), len(quotes))
    if len(summ) > float(spec.get("max_ratio", 0.5)) * max(1, len(src)):
        return False, "resume trop long"
    return True, "citations %d/%d, longueur ok" % (len(quotes), len(quotes))


# ------------------------------------------------------------------ 2 extraction
_TYPES = {"int": int, "str": str, "float": (int, float), "bool": bool, "list": list, "dict": dict}


def _scalars(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from _scalars(x)
    elif isinstance(v, list):
        for x in v:
            yield from _scalars(x)
    elif v is not None and not isinstance(v, bool):
        yield v


def v_schema_source(src, out, spec):
    o, err = _json(out)
    if err or not isinstance(o, dict) or not o:
        return False, err or "objet non vide attendu"
    miss = [k for k in spec.get("required", []) if k not in o]
    if miss:
        return False, "champ requis absent: " + miss[0]
    for k, t in (spec.get("types") or {}).items():
        if k in o and (not isinstance(o[k], _TYPES.get(t, object)) or (t == "int" and isinstance(o[k], bool))):
            return False, "type faux: %s" % k
    for v in _scalars(o):
        if str(v) not in src:
            return False, "valeur absente de la source"
    return True, "schema ok, %d valeurs retrouvees" % len(list(_scalars(o)))


# ------------------------------------------------------------------ 3 classement
def v_labels(src, out, spec):
    o, err = _json(out)
    if err or not isinstance(o, dict) or not o:
        return False, err or "objet non vide attendu"
    labels = set(spec.get("labels", []))
    bad = [v for v in o.values() if v not in labels]
    if bad:
        return False, "etiquette non autorisee (%d)" % len(bad)
    items = spec.get("items")
    if items is not None and set(o) != set(items):
        return False, "elements manquants ou en trop"
    return True, "etiquettes ok %d/%d" % (len(o), len(o))


def double_pass_sample(items, rate=0.1):
    """Deterministic ~10 % sample (at least one) re-asked to check stability."""
    items = sorted(items)
    if not items:
        return []
    k = max(1, int(round(len(items) * rate)))
    ranked = sorted(items, key=lambda x: hashlib.sha256(str(x).encode("utf-8")).hexdigest())
    return sorted(ranked[:k])


def double_pass_agree(first, second):
    return all(first.get(k) == v for k, v in second.items())


# ------------------------------------------------------------------ 4 docstrings
def _strip_doc(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            b = node.body[0]
            if isinstance(b, ast.Expr) and isinstance(getattr(b, "value", None), ast.Constant) and isinstance(b.value.value, str):
                node.body = node.body[1:] or [ast.Pass()]
    return ast.dump(tree, include_attributes=False)


def v_ast_same(src, out, spec):
    if not out.strip():
        return False, "sortie vide"
    try:
        a, b = _strip_doc(ast.parse(src)), _strip_doc(ast.parse(out))
    except SyntaxError as e:
        return False, "ne compile pas (ligne %s)" % getattr(e, "lineno", "?")
    return (True, "AST identique hors commentaires") if a == b else (False, "le code a change (AST different)")


# ------------------------------------------------------------------ 5 doc
def v_doc_refs(src, out, spec):
    if not out.strip():
        return False, "sortie vide"
    root = spec.get("root") or "."
    links = re.findall(r"\]\(([^)\s]+)\)", out)
    for l in links:
        if re.match(r"^[a-z]+://|^mailto:|^#", l):
            continue
        p = l.split("#")[0]
        full = os.path.normpath(os.path.join(root, p))
        if ".." in os.path.relpath(full, root).split(os.sep) or not os.path.exists(full):
            return False, "lien mort"
    syms = re.findall(r"`([A-Za-z_][A-Za-z0-9_.]*)\(", out)
    for s in syms:
        name = s.split(".")[-1]
        if not re.search(r"\b(?:def|class)\s+%s\b" % re.escape(name), src):
            return False, "symbole inexistant"
    for cmd in re.findall(r"```(?:sh|bash|shell|console|powershell)\n(.*?)```", out, re.S):
        allowed = spec.get("commands")
        for line in cmd.strip().splitlines():
            if allowed is not None and line.split()[:1] and line.split()[0] not in allowed:
                return False, "commande inconnue"
    return True, "liens %d, symboles %d ok" % (len(links), len(syms))


# ------------------------------------------------------------------ 6 traduction
_PH = re.compile(r"\{\{[^}]*\}\}|\{[^{}]*\}|%\([a-zA-Z_]+\)[sdif]|%[sdif]|\$\{[^}]*\}")


def v_i18n(src, out, spec):
    a, err = _json(src)
    b, err2 = _json(out)
    if err or err2 or not isinstance(a, dict) or not isinstance(b, dict):
        return False, err2 or "objets attendus"
    if set(a) != set(b):
        return False, "cles differentes"
    for k in a:
        if not isinstance(b[k], str) or not b[k].strip():
            return False, "valeur vide: " + k
        if sorted(_PH.findall(str(a[k]))) != sorted(_PH.findall(b[k])):
            return False, "variables differentes: " + k
        r = len(b[k]) / max(1, len(str(a[k])))
        if not 0.3 <= r <= 3.0:
            return False, "longueur hors bornes: " + k
    return True, "cles et variables identiques (%d)" % len(a)


# ------------------------------------------------------------------ 7 code repetitif
def v_compile_check(src, out, spec):
    if not out.strip():
        return False, "sortie vide"
    e = _compiles(out)
    if e:
        return False, e
    chk = spec.get("check")
    if not chk:
        return True, "compile"
    with _Tmp() as d:
        _write(d, _module(spec) + ".py", out)
        _write(d, "check_relais.py", chk)
        rc, txt = run_isolated(_py_script("check_relais.py"), d)
    return (True, "compile + controle ok") if rc == 0 else (False, "controle en echec (code %d)" % rc)


# ------------------------------------------------------------------ 8 tests unitaires (+ mutation)
_SWAP = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult, ast.Gt: ast.LtE, ast.LtE: ast.Gt,
         ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.And: ast.Or, ast.Or: ast.And}


def mutants(code, limit=8):
    """One mutant per mutable site (arithmetic, comparison, boolean, True/False constants), deterministic order."""
    tree = ast.parse(code)
    sites = []
    for n in ast.walk(tree):
        if isinstance(n, ast.BinOp) and type(n.op) in _SWAP:
            sites.append((n, "op"))
        elif isinstance(n, ast.BoolOp) and type(n.op) in _SWAP:
            sites.append((n, "op"))
        elif isinstance(n, ast.Compare) and type(n.ops[0]) in _SWAP:
            sites.append((n, "cmp"))
        elif isinstance(n, ast.Constant) and isinstance(n.value, bool):
            sites.append((n, "bool"))
    out = []
    for i in range(min(limit, len(sites))):
        t = ast.parse(code)
        found = 0
        for m in ast.walk(t):
            ok = (isinstance(m, (ast.BinOp, ast.BoolOp)) and type(m.op) in _SWAP) or \
                 (isinstance(m, ast.Compare) and type(m.ops[0]) in _SWAP) or (isinstance(m, ast.Constant) and isinstance(m.value, bool))
            if not ok:
                continue
            if found == i:
                if isinstance(m, (ast.BinOp, ast.BoolOp)):
                    m.op = _SWAP[type(m.op)]()
                elif isinstance(m, ast.Compare):
                    m.ops[0] = _SWAP[type(m.ops[0])]()
                else:
                    m.value = not m.value
                break
            found += 1
        out.append(ast.unparse(t))
    return out


def v_mutation(src, out, spec):
    if not out.strip():
        return False, "sortie vide"
    e = _compiles(out)
    if e:
        return False, e
    mod = _module(spec)
    with _Tmp() as d:
        _write(d, mod + ".py", src)
        _write(d, "test_relais_gen.py", out)
        rc, txt = run_isolated(_py_unittest("test_relais_gen"), d)
        if rc != 0 or "Ran 0 tests" in txt:
            return False, "les tests ne passent pas sur le code"
        muts = mutants(src)
        if not muts:
            return False, "aucune mutation possible: verification impossible"
        killed = 0
        for m in muts:
            _write(d, mod + ".py", m)
            rc, _t = run_isolated(_py_unittest("test_relais_gen"), d)
            killed += rc != 0
    if killed == 0:
        return False, "aucune mutation detectee (0/%d)" % len(muts)
    return True, "passent; mutations tuees %d/%d" % (killed, len(muts))


# ------------------------------------------------------------------ 9 conversion
def _parse(fmt, text):
    if fmt == "json":
        return json.loads(text)
    if fmt in ("csv", "tsv"):
        rows = list(csv.DictReader(io.StringIO(text), delimiter="\t" if fmt == "tsv" else ","))
        return [dict(r) for r in rows]
    raise ValueError("format inconnu: " + fmt)


def _norm_rows(x):
    if isinstance(x, list):
        return [{str(k): ("" if v is None else str(v)) for k, v in r.items()} if isinstance(r, dict) else r for r in x]
    return x


def v_roundtrip(src, out, spec):
    if not out.strip():
        return False, "sortie vide"
    try:
        a, b = _parse(spec.get("from", "json"), src), _parse(spec.get("to", "csv"), out)
    except (ValueError, csv.Error) as e:
        return False, "sortie illisible dans le format cible"
    if _norm_rows(a) != _norm_rows(b):
        return False, "aller-retour avec perte"
    return True, "aller-retour sans perte (%d)" % (len(a) if isinstance(a, list) else 1)


# ------------------------------------------------------------------ 10 regex / SQL / script
_RX_RUN = ("import json,re,sys\nd=json.loads(sys.stdin.read())\nr=re.compile(d['p'])\n"
           "print(json.dumps([bool(r.search(s)) for s in d['m']]+[bool(r.search(s)) for s in d['n']]))")


def v_examples(src, out, spec):
    if not out.strip():
        return False, "sortie vide"
    kind = spec.get("kind", "regex")
    if kind == "regex":
        m, n = spec.get("match", []), spec.get("nomatch", [])
        with _Tmp() as d:
            rc, txt = run_isolated(_py("-c", _RX_RUN), d, stdin=json.dumps({"p": out.strip(), "m": m, "n": n}), timeout=5)
        if rc != 0:
            return False, "regex invalide ou trop lente"
        res = json.loads(txt.strip().splitlines()[-1])
        good = res[:len(m)].count(True) + res[len(m):].count(False)
        return (good == len(res)), "exemples %d/%d" % (good, len(res))
    if kind == "sql":
        q = out.strip().rstrip(";")
        if ";" in q or not re.match(r"(?is)^\s*(select|with)\b", q):
            return False, "SQL de lecture seule attendu"
        con = sqlite3.connect(":memory:")
        deadline = time.time() + 3.0              # review #12: a recursive CTE never ends on its own
        con.set_progress_handler(lambda: 1 if time.time() > deadline else 0, 10000)
        try:
            con.executescript(spec.get("setup", ""))
            con.execute("PRAGMA query_only = ON")
            rows = [list(r) for r in con.execute(q).fetchmany(10000)]
        except sqlite3.Error as e:
            return False, "SQL en erreur ou trop long"
        finally:
            con.close()
        return (rows == spec.get("expected")), "resultat %s" % ("conforme" if rows == spec.get("expected") else "different")
    if kind == "script":
        e = _compiles(out)
        if e:
            return False, e
        with _Tmp() as d:
            _write(d, "jetable.py", out)
            rc, txt = run_isolated(_py_script("jetable.py"), d, stdin=spec.get("stdin", ""), timeout=10)
        same = rc == 0 and txt.replace("\r\n", "\n") == spec.get("stdout", "")
        return same, "sortie %s" % ("conforme" if same else "differente")
    return False, "genre inconnu"


# ------------------------------------------------------------------ 11 migration
def v_bounded_diff(src, out, spec):
    if not out.strip():
        return False, "sortie vide"
    e = _compiles(out)
    if e:
        return False, e
    d = list(difflib.ndiff(src.splitlines(), out.splitlines()))
    add = sum(1 for l in d if l.startswith("+ "))
    rem = sum(1 for l in d if l.startswith("- "))
    lim = int(spec.get("max_changed_lines", 20))
    if max(add, rem) > lim:
        return False, "diff trop large: %d lignes > %d" % (max(add, rem), lim)
    if spec.get("check"):
        ok, det = v_compile_check(src, out, spec)
        if not ok:
            return False, det
    return True, "diff borne: %d lignes, tests ok" % max(add, rem)


# ------------------------------------------------------------------ 12 revue
def v_findings(src, out, spec):
    o, err = _json(out)
    if err or not isinstance(o, list) or not o:
        return False, err or "liste non vide attendue"
    root = spec.get("root") or "."
    for f in o:
        if not isinstance(f, dict):
            return False, "constat mal forme"
        p = os.path.normpath(os.path.join(root, str(f.get("file", ""))))
        if ".." in os.path.relpath(p, root).split(os.sep) or not os.path.isfile(p):
            return False, "fichier inexistant"
        with open(p, encoding="utf-8", errors="replace") as fh:
            n = len(fh.read().splitlines())
        line = f.get("line")
        if not isinstance(line, int) or not 1 <= line <= n:
            return False, "ligne inexistante"
    return True, "constats %d/%d localises" % (len(o), len(o))


# ------------------------------------------------------------------ 13 commit
_CC = re.compile(r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([A-Za-z0-9._/\-]+\))?!?: \S.*$")


def v_conventional(src, out, spec):
    first = out.strip().splitlines()[0] if out.strip() else ""
    if not first or len(first) > 72 or not _CC.match(first):
        return False, "hors Conventional Commits"
    return True, "Conventional Commits ok"


# ------------------------------------------------------------------ 14 donnees de test
_SAFE_MAIL = re.compile(r"@(?:[a-z0-9-]+\.)*(?:example\.(?:com|org|net)|[a-z0-9-]+\.(?:test|invalid|example|localhost))$", re.I)


def _luhn(d):
    s, alt = 0, False
    for c in reversed(d):
        n = int(c)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        s, alt = s + n, not alt
    return s % 10 == 0


def v_fake_data(src, out, spec):
    o, err = _json(out)
    rows = o if isinstance(o, list) else None
    if err or not rows:
        return False, err or "liste non vide attendue"
    for r in rows:
        if not isinstance(r, dict):
            return False, "ligne mal formee"
        miss = [k for k in spec.get("required", []) if k not in r]
        if miss:
            return False, "champ requis absent: " + miss[0]
    text = json.dumps(rows, ensure_ascii=False)
    for m in re.findall(r"[\w.+-]{1,64}@[\w.-]{1,253}\.[a-z]{2,24}", text, re.I):
        if not _SAFE_MAIL.search(m):
            return False, "adresse reelle possible (domaine non reserve)"
    for m in re.findall(r"\b\d(?:[ -]?\d){12,18}\b", text):
        if _luhn(re.sub(r"\D", "", m)):
            return False, "numero de carte plausible"
    if re.search(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){3,7}\b", text):
        return False, "IBAN plausible"
    if guard_core.secret_in(text):
        return False, "secret dans les donnees"
    return True, "schema ok, %d lignes factices" % len(rows)


# ------------------------------------------------------------------ 15 lecture de doc publique
def v_citations_url(src, out, spec):
    o, err = _json(out)
    pages, err2 = _json(src)
    if err or err2 or not isinstance(o, dict) or not isinstance(pages, dict):
        return False, err or "source: objet {url: texte} attendu"
    cits = o.get("citations") or []
    if not str(o.get("answer", "")).strip() or not cits:
        return False, "reponse ou citations absentes"
    for c in cits:
        url, q = str(c.get("url", "")), str(c.get("quote", ""))
        if not url.startswith("https://") or url not in pages:
            return False, "URL non lue ou non https"
        if not q.strip() or _ws(q) not in _ws(pages[url]):
            return False, "citation introuvable dans la page"
    return True, "citations + URL %d/%d" % (len(cits), len(cits))


# ------------------------------------------------------------------ 16 fiches du catalogue
def v_catalog(src, out, spec):
    lines = [l for l in out.splitlines() if l.strip()]
    if not lines:
        return False, "sortie vide"
    req = spec.get("required", ["id", "name", "kind", "description"])
    recs = []
    for l in lines:
        try:
            r = json.loads(l)
        except ValueError:
            return False, "ligne JSON invalide"
        miss = [k for k in req if not r.get(k)]
        if miss:
            return False, "champ requis absent: " + miss[0]
        recs.append(r)
    for r in recs[::10]:
        if str(r["name"]) not in src:
            return False, "echantillon absent de la source"
    return True, "schema ok, echantillon %d/%d" % (len(recs[::10]), len(recs[::10]))


# ------------------------------------------------------------------ 17 erreur de build
def v_repro(src, out, spec):
    o, err = _json(out)
    if err or not isinstance(o, dict):
        return False, err or "objet attendu"
    cmd = o.get("command")
    # review #11: the command must be listed by the caller AND appear verbatim in the build log the model read
    if not isinstance(cmd, list) or cmd not in (spec.get("allowed_commands") or []):
        return False, "commande non autorisee"
    if _ws(" ".join(str(x) for x in cmd)) not in _ws(src):
        return False, "commande non autorisee (absente du journal)"
    if not str(o.get("explanation", "")).strip() or not str(o.get("error_line", "")).strip():
        return False, "explication ou ligne d'erreur absente"
    with _Tmp() as d:
        rc, txt = run_isolated(cmd, d, timeout=60)
    if rc == 0:
        return False, "la commande ne reproduit pas d'erreur"
    if _ws(o["error_line"]) not in _ws(txt):
        return False, "ligne d'erreur non reproduite"
    return True, "erreur reproduite (code %d)" % rc


# ------------------------------------------------------------------ 18 reformulation
_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def v_facts(src, out, spec):
    if not out.strip():
        return False, "sortie vide"
    a, b = set(_NUM.findall(src)), set(_NUM.findall(out))
    if a != b:
        lost, new = sorted(a - b), sorted(b - a)
        return False, "nombres modifies: %d perdus, %d ajoutes" % (len(lost), len(new))
    miss = [t for t in spec.get("keep", []) if t not in out]
    if miss:
        return False, "fait perdu (%d)" % len(miss)
    return True, "faits et nombres conserves (%d)" % len(a)


VERIFIERS = {
    "quotes": v_quotes, "schema_source": v_schema_source, "labels": v_labels, "ast_same": v_ast_same, "doc_refs": v_doc_refs,
    "i18n": v_i18n, "compile_check": v_compile_check, "mutation": v_mutation, "roundtrip": v_roundtrip, "examples": v_examples,
    "bounded_diff": v_bounded_diff, "findings": v_findings, "conventional": v_conventional, "fake_data": v_fake_data,
    "citations_url": v_citations_url, "catalog": v_catalog, "repro": v_repro, "facts": v_facts,
}

_TASKS = None


def tasks():
    global _TASKS
    if _TASKS is None:
        with open(os.path.join(_HERE, "tasks.json"), encoding="utf-8") as f:
            _TASKS = json.load(f)
    return _TASKS


def check(task_type, src, out, spec=None):
    t = tasks()["types"].get(task_type)
    if not t:
        return False, "type inconnu: " + str(task_type)
    if out is None or not str(out).strip():
        return False, "sortie vide"
    try:
        return VERIFIERS[t["verifier"]](src or "", out, dict(t.get("spec_defaults", {}), **(spec or {})))
    except Exception as e:  # a verifier that crashes rejects: fail closed
        return False, "verificateur en erreur: %s" % type(e).__name__
