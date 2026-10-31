# -*- coding: utf-8 -*-
"""Shared helpers for the super-reprompt plugin scripts.

Rules this module enforces for every script:
  - Python 3.8+, standard library only, no network.
  - UTF-8 on stdout/stderr (Windows consoles default to a legacy code page).
  - Writes only under <project>/.super-reprompt/ and ~/.claude/super-reprompt/
    (or the paths passed as arguments).
  - Hooks never raise: callers wrap main() with run_hook().
"""
import json
import os
import re
import sys
import time
from pathlib import Path

if sys.version_info < (3, 8):  # pragma: no cover - cannot be reached on 3.8+
    sys.exit(0)

SCHEMA = 1
LOG_MAX_BYTES = 200 * 1024

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
CLASSES = ("CODE", "DOCUMENT", "RESEARCH", "DATA", "DECISION", "INFRA", "OTHER")
TIERS = ("quick", "standard", "max")
LEVELS = ("novice", "pro", "mixed")
STATUSES = ("framing", "ready", "executing", "done", "aborted")
CAP_KINDS = ("skill", "agent", "mcp", "command", "script")
REQ_KINDS = ("unguessable", "guessable")
VERIF_STATES = ("pending", "executed", "not_executable", "not_run")
CRIT_SOURCES = ("test", "document", "person", "second_model")
PHASES = ("P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
PERMISSION_MODES = ("default", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")
ISOLATIONS = ("none", "worktree")
DEFAULT_DENY = ["delete files", "git push", "network writes", "credentials"]

# Patterns that look like API keys or tokens. Used by validate_order.py.
SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"), "Anthropic-style API key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "API key starting with sk-"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "Google API key"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "JWT"),
    (re.compile(r"\b0x[a-fA-F0-9]{64}\b"), "64-hex-digit value (possible private key)"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|token|passw(?:or)?d|passwd)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-/+=]{16,}"),
     "key/secret/token/password assignment"),
]


# ----------------------------------------------------------------- basics
def setup_stdio():
    """Force UTF-8 so accents survive Windows consoles and pipes."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def hooks_disabled():
    return os.environ.get("SUPER_REPROMPT_HOOKS", "").strip() == "0"


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def claude_home():
    """Claude Code config dir: CLAUDE_CONFIG_DIR if set, else ~/.claude."""
    env = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    if env:
        return Path(env)
    return Path(os.path.expanduser("~")) / ".claude"


def home_dir():
    """~/.claude/super-reprompt (SUPER_REPROMPT_HOME overrides it, used by tests)."""
    env = os.environ.get("SUPER_REPROMPT_HOME", "").strip()
    if env:
        return Path(env)
    return claude_home() / "super-reprompt"


def log(source, message):
    """Append one line to hook.log (rotated at 200 KB). Never raises."""
    try:
        d = home_dir()
        d.mkdir(parents=True, exist_ok=True)
        p = d / "hook.log"
        try:
            if p.exists() and p.stat().st_size > LOG_MAX_BYTES:
                old = d / "hook.log.1"
                try:
                    if old.exists():
                        old.unlink()
                except Exception:
                    pass
                p.replace(old)
        except Exception:
            pass
        line = "%s %s %s\n" % (now_iso(), source, str(message).replace("\n", " ")[:500])
        with open(str(p), "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def read_stdin_json():
    """Read stdin as JSON. Empty, invalid or non-object input returns {}."""
    try:
        raw = sys.stdin.buffer.read()
    except Exception:
        return {}
    try:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return {}
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def run_hook(name, func, doc=None):
    """Run a hook body; every failure is logged and turned into exit code 0.

    -h/--help prints the module docstring and exits 0 without reading stdin."""
    setup_stdio()
    if doc is not None and any(a in ("-h", "--help") for a in sys.argv[1:]):
        emit(doc)
        return 0
    try:
        if hooks_disabled():
            return 0
        func()
    except SystemExit:
        pass
    except BaseException as exc:  # fail-open on purpose
        log(name, "internal error: %s: %s" % (type(exc).__name__, exc))
    return 0


def emit(text):
    """Write text to stdout as UTF-8, flushing so it survives os._exit paths."""
    try:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    except Exception:
        pass


# ----------------------------------------------------------------- JSON io
def read_json(path, default=None):
    """Tolerant JSON read: missing or invalid file returns default."""
    try:
        with open(str(path), "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    """Atomic write (temp file + replace)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp%d" % os.getpid())
    with open(str(tmp), "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    os.replace(str(tmp), str(p))


def write_text(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp%d" % os.getpid())
    with open(str(tmp), "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(str(tmp), str(p))


# ----------------------------------------------------------------- paths
STATE_DIRNAME = ".super-reprompt"


def find_project(start):
    """Walk up from start looking for a .super-reprompt directory. None if absent."""
    try:
        p = Path(start).resolve()
    except Exception:
        return None
    for cand in [p] + list(p.parents):
        try:
            if (cand / STATE_DIRNAME).is_dir():
                return cand
        except Exception:
            continue
    return None


def project_for_cli(arg_project):
    """Project dir for command-line scripts: --project, else nearest ancestor with
    a .super-reprompt dir, else the current directory."""
    if arg_project:
        return Path(arg_project).resolve()
    found = find_project(os.getcwd())
    return found if found else Path(os.getcwd()).resolve()


def mission_dir(project, slug):
    return Path(project) / STATE_DIRNAME / slug


def state_path(project, slug):
    return mission_dir(project, slug) / "STATE.json"


class UsageError(Exception):
    """Invalid input; message names the faulty field and the valid values."""


def check_slug(slug):
    if not isinstance(slug, str) or not SLUG_RE.match(slug):
        raise UsageError(
            "slug: %r is invalid. Valid: lowercase letters, digits and hyphens, "
            "starting with a letter or digit, at most 40 characters (regex %s)"
            % (slug, SLUG_RE.pattern)
        )
    return slug


def load_state(project, slug):
    check_slug(slug)
    p = state_path(project, slug)
    if not p.is_file():
        existing = list_slugs(project)
        raise UsageError(
            "slug: no mission %r under %s. Existing missions: %s"
            % (slug, Path(project) / STATE_DIRNAME, ", ".join(existing) if existing else "(none)")
        )
    try:
        with open(str(p), "r", encoding="utf-8-sig") as f:
            st = json.load(f)
    except Exception as exc:
        raise UsageError("STATE.json: cannot parse %s (%s). Fix the JSON or recreate the mission" % (p, exc))
    if not isinstance(st, dict):
        raise UsageError("STATE.json: top level must be a JSON object, got %s" % type(st).__name__)
    return st


def save_state(project, slug, state):
    write_json(state_path(project, slug), state)


def list_slugs(project):
    base = Path(project) / STATE_DIRNAME
    out = []
    try:
        for child in sorted(base.iterdir()):
            if child.is_dir() and (child / "STATE.json").is_file():
                out.append(child.name)
    except Exception:
        pass
    return out


def iter_missions(project):
    """Yield (slug, state) for every readable mission under project."""
    for slug in list_slugs(project):
        st = read_json(state_path(project, slug), None)
        if isinstance(st, dict):
            yield slug, st


# ----------------------------------------------------------------- transcript
def count_tool_calls(transcript_path, max_bytes=64 * 1024 * 1024):
    """Count tool calls found in a Claude Code transcript (JSONL).

    Returns {"counts": {"Skill:dataviz": 2, "Agent:reprompt-reviewer": 1, "mcp__x__y": 3, "Bash": 7},
             "bash": [first 300 chars of each Bash command]}.

    Only lines whose top-level "type" is "assistant" are read: the same file also holds
    "api-request-blob" lines that repeat tool_use blocks (observed on Claude Code 2.1.266;
    this layout is not documented, so everything here is defensive).
    """
    counts = {}
    bash = []
    try:
        p = Path(transcript_path)
        if not p.is_file() or p.stat().st_size > max_bytes:
            return {"counts": counts, "bash": bash}
        with open(str(p), "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"tool_use"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "assistant":
                    continue
                msg = obj.get("message")
                content = msg.get("content") if isinstance(msg, dict) else None
                if not isinstance(content, list):
                    continue
                for blk in content:
                    if not isinstance(blk, dict) or blk.get("type") != "tool_use":
                        continue
                    name = str(blk.get("name", ""))
                    inp = blk.get("input") if isinstance(blk.get("input"), dict) else {}
                    if name == "Skill":
                        key = "Skill:%s" % inp.get("skill", "")
                    elif name in ("Agent", "Task"):
                        key = "Agent:%s" % inp.get("subagent_type", "general-purpose")
                    else:
                        key = name
                    counts[key] = counts.get(key, 0) + 1
                    if name == "Bash" and len(bash) < 500:
                        bash.append(str(inp.get("command", ""))[:300])
    except Exception:
        pass
    return {"counts": counts, "bash": bash}


def capability_called(cap, tally):
    """True if the transcript tally shows the capability was called."""
    name = str(cap.get("name", ""))
    kind = cap.get("kind")
    counts = tally.get("counts", {})
    short = name.split(":")[-1]
    if kind == "skill":
        for k, n in counts.items():
            if k.startswith("Skill:") and n > 0 and k[6:].split(":")[-1] == short:
                return True
        return False
    if kind == "agent":
        for k, n in counts.items():
            if k.startswith("Agent:") and n > 0 and k[6:].split(":")[-1] == short:
                return True
        return False
    if kind == "mcp":
        for k, n in counts.items():
            if k.startswith("mcp__") and n > 0:
                if k == name or k.startswith(name) or ("mcp__%s__" % name) in k or name in k:
                    return True
        return False
    # command / script: look for the name in a Bash command line
    for cmd in tally.get("bash", []):
        if name and name in cmd:
            return True
    return False


def cap_satisfied(cap, state, tally=None):
    """A required capability is satisfied if waived, or counted in state['calls'], or in the tally."""
    if cap.get("removed_reason"):
        return True
    calls = state.get("calls")
    if isinstance(calls, dict) and calls.get(cap.get("id"), 0):
        return True
    if tally is not None and capability_called(cap, tally):
        return True
    return False


def lang_is_french(lang):
    return isinstance(lang, str) and lang.lower().startswith("fr")


def _criteria_list(state):
    ver = state.get("verification") if isinstance(state, dict) else None
    crits = ver.get("criteria") if isinstance(ver, dict) else None
    out = []
    for c in crits if isinstance(crits, list) else []:
        if isinstance(c, dict):
            out.append({"id": str(c.get("id")), "text": str(c.get("text")), "source": str(c.get("source"))})
    return sorted(out, key=lambda x: x["id"])


def _sha(obj):
    import hashlib
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def criteria_digest(state):
    """SHA-256 of the canonical JSON of the criteria (id, text, source), sorted by id: same input, same output."""
    return _sha(_criteria_list(state))


def criteria_fingerprints(state):
    """Per-criterion SHA-256 (first 16 hex digits), so a change can be traced to the criterion that moved."""
    return {c["id"]: _sha(c)[:16] for c in _criteria_list(state)}


def criteria_changes(state):
    """Ids of criteria modified, added or removed since `mission.py ready`; [] when unchanged.
    None when the state has no recorded digest (older missions: nothing to compare)."""
    want = state.get("criteria_sha256") if isinstance(state, dict) else None
    if not isinstance(want, str) or not want:
        return None
    if criteria_digest(state) == want:
        return []
    old = state.get("criteria_fingerprints")
    now = criteria_fingerprints(state)
    if not isinstance(old, dict):
        return ["(criteria changed; no per-criterion record)"]
    changed = sorted({k for k in now if old.get(k) != now[k]} | {k for k in old if k not in now})
    return changed or ["(criteria order or formatting changed)"]


def criteria_report(state):
    """Split of the criteria: (checked by test source, self-reported, open) as lists of ids."""
    ver = state.get("verification") if isinstance(state, dict) else None
    crits = ver.get("criteria") if isinstance(ver, dict) else None
    tested, own, open_ = [], [], []
    for c in crits if isinstance(crits, list) else []:
        if not isinstance(c, dict):
            continue
        if not c.get("passes"):
            open_.append(c.get("id"))
        elif c.get("self_reported"):
            own.append(c.get("id"))
        else:
            tested.append(c.get("id"))
    return tested, own, open_
