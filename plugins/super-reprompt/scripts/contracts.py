# -*- coding: utf-8 -*-
"""contracts.py : le socle CORE de V3.1 (lot 1). Bibliotheque standard seule, AUCUN reseau.

Une seule implementation pour :
  - les schemas versionnes (STATE, PLAN, SCELLE, evenement, recu) et leur validation ;
  - l'ecriture atomique (temporaire unique + fsync + os.replace), et la lecture stricte (jamais d'ecrasement
    silencieux d'un fichier illisible) ;
  - le journal unique de mission `events.ndjson` (append sous verrou, event_id deduplique) ;
  - la machine a etats des taches (proposed ready running review done + blocked failed cancelled skipped) ;
  - les recus d'execution (`receipts/<tache>/<run>.json`), champs inconnus a null, jamais inventes ;
  - la migration de l'ancien `journal.ndjson` (deux schemas) vers `events.ndjson`, idempotente, original intact.

CLI :
  contracts.py validate {state|plan|seal|event|receipt} FICHIER [--strict]   -> 0 valide, 1 invalide
  contracts.py migrate DOSSIER_MISSION                                       -> rapport JSON
  contracts.py events DOSSIER_MISSION [--tail N]                             -> derniers evenements
"""
import hashlib
import json
import os
import re
import sys
import time

SCHEMA_VERSIONS = {"state": 1, "plan": 2, "seal": 1, "event": 1, "receipt": 1}
STATUSES = ("proposed", "ready", "running", "review", "done", "blocked", "failed", "cancelled", "skipped")
TERMINAL = ("done", "cancelled", "skipped")
TRANSITIONS = {
    "proposed": ("ready", "blocked", "cancelled", "skipped"),
    "ready": ("running", "blocked", "cancelled", "skipped"),
    "running": ("review", "failed", "blocked", "cancelled"),
    "review": ("done", "failed", "running", "blocked"),            # blocked: a blocking Vigie finding holds the closure
    "blocked": ("ready", "cancelled", "skipped"),
    "failed": ("ready", "blocked", "cancelled", "skipped"),       # blocked: attempts exhausted, a human decides
    "done": (), "cancelled": (), "skipped": (),
}
LEGACY_STATUS = {"todo": "ready", "echec": "failed"}
ACTORS = ("core", "manager", "agent", "user", "provider", "system")
RECEIPT_STATUS = ("ok", "failed", "partial")
EXEC_MODES = ("script", "session", "specialiste", "sous-manager", "relais")
UNKNOWN = (None, "unavailable")
EVENTS = "events.ndjson"
_TYPE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
_HEX = re.compile(r"^[0-9a-f]{16,64}$")


class ContractError(ValueError):
    pass


def now_utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ------------------------------------------------------------------ storage
def atomic_write_text(path, text):
    path = os.path.abspath(path)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, ".%s.%d.%s.tmp" % (os.path.basename(path), os.getpid(), os.urandom(4).hex()))
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        for i in range(50):                       # Windows: a reader (antivirus, indexer, another agent) holding the target
            try:                                  # makes replace fail for a while under load: back off up to ~8 s in total
                os.replace(tmp, path)
                return path
            except PermissionError:
                if i == 49:
                    raise
                time.sleep(min(0.25, 0.02 * (i + 1)))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return path


def atomic_write_json(path, obj, indent=1):
    return atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=indent) + "\n")


def read_json(path, default=KeyError):
    """Strict: a missing file gives `default` if one is given, an unreadable one ALWAYS raises ContractError."""
    if not os.path.exists(path):
        if default is KeyError:
            raise ContractError("fichier absent : %s" % path)
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, UnicodeDecodeError) as e:
        raise ContractError("fichier illisible, rien n'est ecrase : %s (%s)" % (path, e))


def save_checked(path, obj, kind, strict=False):
    """Validate, refuse to replace an unreadable file, then write atomically."""
    errs = validate(kind, obj, strict=strict)
    if errs:
        raise ContractError("%s invalide : %s" % (kind, "; ".join(errs[:5])))
    if os.path.exists(path):
        read_json(path)                          # raises if the current file is corrupt: a human must look first
    return atomic_write_json(path, obj)


class Lock:
    """Exclusive-creation lock file, stale after `stale` seconds (portable: Windows, Linux, macOS)."""

    def __init__(self, path, timeout=30.0, stale=60.0):
        self.path, self.timeout, self.stale, self.fd = path, timeout, stale, None

    def __enter__(self):
        end = time.time() + self.timeout
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except (FileExistsError, PermissionError):
                try:
                    if time.time() - os.stat(self.path).st_mtime > self.stale:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                if time.time() > end:
                    raise TimeoutError("verrou occupe : " + self.path)
                time.sleep(0.01)

    def __exit__(self, *a):
        os.close(self.fd)
        try:
            os.remove(self.path)
        except OSError:
            pass


def _seal_torn_tail(path):
    """A crash mid-write leaves a last line without newline: close it so the next line is not glued to it."""
    try:
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            last = f.read(1)
        if last != b"\n":
            with open(path, "ab") as g:
                g.write(b"\n")
    except OSError:
        pass


def append_line(path, line):
    """Append one complete line under a lock (no interleaving between processes)."""
    with Lock(path + ".lock"):
        _seal_torn_tail(path)
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line.rstrip("\n") + "\n")
            f.flush()
            os.fsync(f.fileno())


# ------------------------------------------------------------------ validation
def _need(o, k, types, errs, where=""):
    if k not in o:
        errs.append("%schamp manquant : %s" % (where, k))
        return False
    if not isinstance(o[k], types):
        errs.append("%s%s : type %s inattendu" % (where, k, type(o[k]).__name__))
        return False
    return True


def _cycle(tasks):
    deps = {t.get("id"): [d for d in (t.get("deps") or []) if isinstance(d, str)] for t in tasks}
    state = {}

    def visit(n, path):
        state[n] = 1
        for d in deps.get(n, []):
            if d not in deps:
                continue
            if state.get(d) == 1:
                return path + [d]
            if not state.get(d):
                c = visit(d, path + [d])
                if c:
                    return c
        state[n] = 2
        return None

    for n in deps:
        if not state.get(n):
            c = visit(n, [n])
            if c:
                return c
    return None


def _v_state(o, strict, errs):
    if o.get("schema") != SCHEMA_VERSIONS["state"]:
        errs.append("schema STATE attendu %d" % SCHEMA_VERSIONS["state"])
    if _need(o, "slug", str, errs) and not _SLUG.match(o["slug"]):
        errs.append("slug invalide")
    _need(o, "status", str, errs)
    if _need(o, "requirements", list, errs):
        for r in o["requirements"]:
            if not isinstance(r, dict) or not isinstance(r.get("id"), str):
                errs.append("exigence sans id")
    if _need(o, "verification", dict, errs):
        if not isinstance(o["verification"].get("criteria", []), list):
            errs.append("verification.criteria doit etre une liste")


def _v_plan(o, strict, errs):
    sv = o.get("schema")
    if sv is not None and sv != SCHEMA_VERSIONS["plan"]:
        errs.append("schema PLAN %r inconnu (attendu %d)" % (sv, SCHEMA_VERSIONS["plan"]))
    if strict:
        if sv != SCHEMA_VERSIONS["plan"]:
            errs.append("schema PLAN absent")
        if not (isinstance(o.get("source_order_hash"), str) and re.match(r"^[0-9a-f]{64}$", o["source_order_hash"])):
            errs.append("source_order_hash absent ou invalide")
    if not _need(o, "tasks", list, errs):
        return
    seen = set()
    for i, t in enumerate(o["tasks"]):
        w = "tache %d : " % i
        if not isinstance(t, dict):
            errs.append(w + "pas un objet")
            continue
        tid = t.get("id")
        if not (isinstance(tid, str) and _ID.match(tid)):
            errs.append(w + "id invalide")
            continue
        if tid in seen:
            errs.append("id en double : %s" % tid)
        seen.add(tid)
        st = t.get("status", "todo")
        if st not in STATUSES and st not in LEGACY_STATUS:
            errs.append("%s : statut inconnu %r" % (tid, st))
        if not isinstance(t.get("deps", []), list):
            errs.append("%s : deps doit etre une liste" % tid)
        if strict:
            if not (isinstance(t.get("acceptance_criteria"), list) and t["acceptance_criteria"]):
                errs.append("%s : acceptance_criteria vide" % tid)
            if not ((isinstance(t.get("preuve"), list) and t["preuve"]) or (isinstance(t.get("preuve"), str) and t["preuve"].strip())):
                errs.append("%s : preuve (commande) absente" % tid)
            if st in LEGACY_STATUS:
                errs.append("%s : statut historique %r interdit en mode strict" % (tid, st))
    ids = {t.get("id") for t in o["tasks"] if isinstance(t, dict)}
    for t in o["tasks"]:
        if isinstance(t, dict):
            for d in t.get("deps", []) if isinstance(t.get("deps", []), list) else []:
                if d not in ids:
                    errs.append("%s : dependance inconnue %r" % (t.get("id"), d))
    c = _cycle([t for t in o["tasks"] if isinstance(t, dict)])
    if c:
        errs.append("cycle de dependances : %s" % " -> ".join(c))


def _v_seal(o, strict, errs):
    if o.get("schema") != SCHEMA_VERSIONS["seal"]:
        errs.append("schema SCELLE attendu %d" % SCHEMA_VERSIONS["seal"])
    _need(o, "slug", str, errs)
    if _need(o, "body_sha", str, errs) and not re.match(r"^[0-9a-f]{64}$", o["body_sha"]):
        errs.append("body_sha invalide")
    _need(o, "perimeter", list, errs)
    _need(o, "avenants", list, errs)
    _need(o, "criteria", list, errs)
    if "budget" in o and not isinstance(o["budget"], dict):
        errs.append("budget doit etre un objet")
    if "plan_sha256" in o and o["plan_sha256"] is not None and not re.match(r"^[0-9a-f]{64}$", str(o["plan_sha256"])):
        errs.append("plan_sha256 invalide")


def _v_event(o, strict, errs):
    if _need(o, "event_id", str, errs) and not _HEX.match(o["event_id"]):
        errs.append("event_id invalide")
    _need(o, "mission_id", str, errs)
    if _need(o, "timestamp", str, errs) and not _TS.match(o["timestamp"]):
        errs.append("timestamp non UTC ISO 8601")
    if _need(o, "event_type", str, errs) and not _TYPE.match(o["event_type"]):
        errs.append("event_type invalide")
    if _need(o, "actor", str, errs) and o["actor"] not in ACTORS:
        errs.append("actor inconnu %r" % o["actor"])
    if o.get("schema_version") != SCHEMA_VERSIONS["event"]:
        errs.append("schema_version attendu %d" % SCHEMA_VERSIONS["event"])
    if "correlation_id" not in o or not isinstance(o["correlation_id"], (str, type(None))):
        errs.append("correlation_id manquant (null permis)")
    _need(o, "payload", dict, errs)


RECEIPT_FIELDS = ("run_id", "task_id", "agent_id", "execution_mode", "status", "summary", "files_changed", "evidence",
                  "tests_run", "test_results", "unresolved_risks", "tokens_input", "tokens_output", "latency_ms",
                  "cost_actual", "cost_estimated", "currency", "provider", "model", "timestamp", "retry_of", "schema")


def _v_receipt(o, strict, errs):
    for k in RECEIPT_FIELDS:
        if k not in o:
            errs.append("champ manquant : %s" % k)
    if o.get("schema") != SCHEMA_VERSIONS["receipt"]:
        errs.append("schema recu attendu %d" % SCHEMA_VERSIONS["receipt"])
    for k in ("run_id", "task_id"):
        if k in o and not (isinstance(o[k], str) and _ID.match(o[k])):
            errs.append("%s invalide" % k)
    if o.get("status") not in RECEIPT_STATUS:
        errs.append("status %r inconnu" % o.get("status"))
    if o.get("execution_mode") not in EXEC_MODES:
        errs.append("execution_mode %r inconnu" % o.get("execution_mode"))
    for k in ("files_changed", "evidence", "tests_run", "unresolved_risks"):
        if k in o and not isinstance(o[k], list):
            errs.append("%s doit etre une liste" % k)
    for k in ("tokens_input", "tokens_output", "latency_ms", "cost_actual", "cost_estimated"):
        v = o.get(k)
        if v not in UNKNOWN and not (isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0):
            errs.append("%s : nombre >= 0, null ou 'unavailable'" % k)
    if "timestamp" in o and not (isinstance(o["timestamp"], str) and _TS.match(o["timestamp"])):
        errs.append("timestamp non UTC ISO 8601")


_VALIDATORS = {"state": _v_state, "plan": _v_plan, "seal": _v_seal, "event": _v_event, "receipt": _v_receipt}


def validate(kind, obj, strict=False):
    if kind not in _VALIDATORS:
        raise ContractError("type de contrat inconnu : %s" % kind)
    if not isinstance(obj, dict):
        return ["%s : un objet JSON est attendu" % kind]
    errs = []
    _VALIDATORS[kind](obj, strict, errs)
    return errs


def check(kind, obj, strict=False):
    errs = validate(kind, obj, strict=strict)
    if errs:
        raise ContractError("%s invalide : %s" % (kind, "; ".join(errs[:5])))
    return obj


PROGRESS_KEYS = ("status", "attempt", "receipt", "updated_at", "owner", "started_at", "finished_at", "execution_mode", "blocked_by")


def plan_structure_sha(plan):
    """SHA-256 of what the plan PROMISES (tasks, deps, coverage, proofs), not of its progress: statuses, attempts and
    receipts change during execution without changing this hash; adding or rewiring a task changes it."""
    tasks = [{k: v for k, v in sorted(t.items()) if k not in PROGRESS_KEYS} for t in plan.get("tasks", []) if isinstance(t, dict)]
    body = {"tasks": tasks, "source_order_hash": plan.get("source_order_hash")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ events
def event_id(mission_id, event_type, key):
    return hashlib.sha256(("%s|%s|%s" % (mission_id, event_type, key)).encode("utf-8")).hexdigest()[:32]


def read_events(mdir):
    p = os.path.join(mdir, EVENTS)
    out = []
    if not os.path.isfile(p):
        return out
    with open(p, encoding="utf-8", errors="replace") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                e = json.loads(ln)
            except ValueError:
                continue                                  # torn line (crash mid-write): skipped, never fatal
            if isinstance(e, dict) and "event_id" in e:
                out.append(e)
    return out


def emit(mdir, event_type, actor, payload=None, mission_id=None, correlation_id=None, dedup_key=None, timestamp=None):
    """Append one validated event. With `dedup_key`, the id is deterministic and a replay writes nothing (-> None)."""
    mid = mission_id or os.path.basename(os.path.normpath(mdir))
    eid = event_id(mid, event_type, dedup_key) if dedup_key is not None else os.urandom(16).hex()
    ev = {"event_id": eid, "mission_id": mid, "timestamp": timestamp or now_utc(), "event_type": event_type,
          "actor": actor, "schema_version": SCHEMA_VERSIONS["event"], "correlation_id": correlation_id,
          "payload": payload or {}}
    check("event", ev)
    os.makedirs(mdir, exist_ok=True)
    p = os.path.join(mdir, EVENTS)
    line = json.dumps(ev, ensure_ascii=False, separators=(",", ":"))
    with Lock(p + ".lock"):
        if dedup_key is not None and any(e.get("event_id") == eid for e in read_events(mdir)):
            return None
        _seal_torn_tail(p)
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
    return ev


# ------------------------------------------------------------------ task states
def normalize_status(s):
    s = s or "todo"
    return LEGACY_STATUS.get(s, s)


def transition(task, new, receipt=None, retry=False):
    """Validated state change, in place. `done` needs an ok receipt with evidence; `failed -> ready` is a retry."""
    cur = normalize_status(task.get("status"))
    if new not in STATUSES:
        raise ContractError("statut inconnu : %s" % new)
    if new not in TRANSITIONS.get(cur, ()):
        raise ContractError("transition interdite %s -> %s (%s)" % (cur, new, task.get("id")))
    if new == "done":
        if not receipt:
            raise ContractError("%s : done exige un recu" % task.get("id"))
        check("receipt", receipt)
        if receipt["status"] != "ok" or not receipt["evidence"] or receipt["task_id"] != task.get("id"):
            raise ContractError("%s : recu non probant (statut %s, %d preuve(s))" % (task.get("id"), receipt["status"], len(receipt["evidence"])))
        task["receipt"] = receipt["run_id"]
    if cur == "failed" and new == "ready":
        if not retry:
            raise ContractError("%s : relancer une tache en echec demande retry=True (nouvelle tentative)" % task.get("id"))
        task["attempt"] = int(task.get("attempt") or 1) + 1
    task["status"] = new
    task["updated_at"] = now_utc()
    return task


# ------------------------------------------------------------------ receipts
def make_receipt(task_id, run_id, execution_mode, status, summary="", agent_id=None, files_changed=None, evidence=None,
                 tests_run=None, test_results=None, unresolved_risks=None, tokens_input=None, tokens_output=None,
                 latency_ms=None, cost_actual=None, cost_estimated=None, currency=None, provider=None, model=None,
                 retry_of=None, timestamp=None):
    r = {"schema": SCHEMA_VERSIONS["receipt"], "run_id": run_id, "task_id": task_id, "agent_id": agent_id,
         "execution_mode": execution_mode, "status": status, "summary": summary, "files_changed": list(files_changed or []),
         "evidence": list(evidence or []), "tests_run": list(tests_run or []), "test_results": test_results,
         "unresolved_risks": list(unresolved_risks or []), "tokens_input": tokens_input, "tokens_output": tokens_output,
         "latency_ms": latency_ms, "cost_actual": cost_actual, "cost_estimated": cost_estimated, "currency": currency,
         "provider": provider, "model": model, "timestamp": timestamp or now_utc(), "retry_of": retry_of}
    return check("receipt", r)


def save_receipt(mdir, receipt):
    """receipts/<task>/<run>.json, written once: same content again is a no-op, different content is refused."""
    check("receipt", receipt)
    p = os.path.join(mdir, "receipts", receipt["task_id"], receipt["run_id"] + ".json")
    if os.path.exists(p):
        old = read_json(p)
        if {k: v for k, v in old.items() if k != "timestamp"} != {k: v for k, v in receipt.items() if k != "timestamp"}:
            raise ContractError("recu %s/%s deja ecrit avec un autre contenu" % (receipt["task_id"], receipt["run_id"]))
        return p
    return atomic_write_json(p, receipt)


# ------------------------------------------------------------------ migration
def _legacy_ts(s):
    s = str(s or "")
    if _TS.match(s):
        return s
    if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", s):
        return s + "Z"                        # historical guard lines: local time without zone, kept as written
    return now_utc()


def migrate_journal(mdir):
    """journal.ndjson (vault.py `{ts,slug,kind,text}` and guard `{t,ev,rule,msg}`) -> events.ndjson.
    Deterministic ids (hash of the line and its rank): replaying migrates nothing twice. The original is never modified."""
    src = os.path.join(mdir, "journal.ndjson")
    rep = {"migrated": 0, "skipped": 0, "already": 0}
    if not os.path.isfile(src):
        return rep
    with open(src, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    for i, ln in enumerate(lines):
        if not ln.strip():
            continue
        try:
            o = json.loads(ln)
        except ValueError:
            rep["skipped"] += 1
            continue
        if not isinstance(o, dict):
            rep["skipped"] += 1
            continue
        key = "%d|%s" % (i, hashlib.sha256(ln.encode("utf-8")).hexdigest())
        if "kind" in o:
            et, actor, pl, ts = "log." + re.sub(r"[^a-z0-9_]", "_", str(o["kind"]).lower()), "manager", {"text": o.get("text", "")}, o.get("ts")
        elif "ev" in o:
            et, actor, pl, ts = "guard." + re.sub(r"[^a-z0-9_]", "_", str(o["ev"]).lower()), "system", {"rule": o.get("rule", ""), "msg": o.get("msg", "")}, o.get("t")
        else:
            rep["skipped"] += 1
            continue
        pl["legacy"] = True
        if emit(mdir, et, actor, pl, dedup_key="legacy|" + key, timestamp=_legacy_ts(ts)):
            rep["migrated"] += 1
        else:
            rep["already"] += 1
    return rep


# ------------------------------------------------------------------ CLI
def main(argv=None):
    import argparse
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="contracts.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("kind", choices=sorted(_VALIDATORS))
    v.add_argument("file")
    v.add_argument("--strict", action="store_true")
    m = sub.add_parser("migrate")
    m.add_argument("mission_dir")
    e = sub.add_parser("events")
    e.add_argument("mission_dir")
    e.add_argument("--tail", type=int, default=20)
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        try:
            errs = validate(a.kind, read_json(a.file), strict=a.strict)
        except ContractError as ex:
            errs = [str(ex)]
        for x in errs:
            print("INVALIDE : " + x)
        if not errs:
            print("VALIDE : %s %s (schema %d)" % (a.kind, a.file, SCHEMA_VERSIONS[a.kind]))
        return 1 if errs else 0
    if a.cmd == "migrate":
        print(json.dumps(migrate_journal(os.path.abspath(a.mission_dir)), ensure_ascii=False))
        return 0
    for ev in read_events(a.mission_dir)[-a.tail:]:
        print(json.dumps(ev, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
