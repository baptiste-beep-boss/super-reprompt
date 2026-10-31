# -*- coding: utf-8 -*-
"""Create and drive a super-reprompt mission folder (<project>/.super-reprompt/<slug>/).

Subcommands:
  init <slug> --class C --tier T --lang L [--level N] [--project DIR]   create STATE.json + NOTES.md
  ready <slug>                           validate, then framing -> ready          (addition to the contract)
  start <slug> [--session-id ID]         ready -> executing, records exec_session_id
  status <slug> [--json]                 one-screen summary
  spent <slug> <k>                       add k thousand tokens to budget.spent_est_k
  check <slug>                           machine summary of what is still open (JSON)
  waive <slug> <capability-id> --reason TEXT   set removed_reason on a capability  (addition)
  verify <slug> <command-id> --state S [--reason TEXT]   record a verification state (addition)
  criterion <slug> <criterion-id> --passes yes|no [--evidence TEXT]   record a criterion result; evidence is
                                         required for "yes" when the criterion source is not "test"
  close <slug> [--report FILE] [--transcript FILE] [--abort]   executing -> done
  path <slug> [--file ORDRE|STATE|NOTES|REPORT]

Exit codes: 0 success, 2 invalid input (message names the field and the valid values), 3 fallback.
"""
import argparse
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
import validate_order as V  # noqa: E402

LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


def new_state(slug, cls, tier, lang, level, session_id):
    return {
        "schema": L.SCHEMA,
        "slug": slug,
        "created": L.now_iso(),
        "lang": lang,
        "level": level,
        "class": cls,
        "tier": tier,
        "status": "framing",
        "framing_session_id": session_id or None,
        "exec_session_id": None,
        "budget": {"announced_k": 0, "spent_est_k": 0, "cap_k": 100, "exec_estimate_k": [0, 0]},
        "requirements": [],
        "assumptions": [],
        "out_of_scope": [],
        "permissions": {"allow": [], "deny": list(L.DEFAULT_DENY)},
        "capabilities": [],
        "verification": {"commands": [], "criteria": []},
        "agents": [],
        "launch": {"model": "sonnet", "effort": "medium", "permission_mode": "default", "name": slug, "unattended": False},
        "stop_blocks": 0,
    }


def _choice(field, value, valid):
    if value not in valid:
        raise L.UsageError("%s: %r is invalid. Valid: %s" % (field, value, ", ".join(valid)))
    return value


def cmd_init(a, project):
    L.check_slug(a.slug)
    _choice("--class", a.cls, L.CLASSES)
    _choice("--tier", a.tier, L.TIERS)
    _choice("--level", a.level, L.LEVELS)
    if not LANG_RE.match(a.lang or ""):
        raise L.UsageError("--lang: %r is invalid. Valid: a language code such as fr, en, es, de, pt-BR" % (a.lang,))
    d = L.mission_dir(project, a.slug)
    if L.state_path(project, a.slug).exists():
        raise L.UsageError("slug: mission %r already exists at %s. Valid: a new slug; existing: %s" % (
            a.slug, d, ", ".join(L.list_slugs(project))))
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "").strip()
    st = new_state(a.slug, a.cls, a.tier, a.lang, a.level, sid)
    L.save_state(project, a.slug, st)
    notes = d / "NOTES.md"
    if not notes.exists():
        L.write_text(notes, "# NOTES - %s\n\nFree-form log kept by the session that works on this mission.\nIt survives context compaction: re-read it after one.\n\n" % a.slug)
    print(str(d))
    return 0


def cmd_ready(a, project):
    st = L.load_state(project, a.slug)
    if st.get("status") != "framing":
        raise L.UsageError("status: %r cannot become ready. Valid: the mission must be in status framing" % st.get("status"))
    st["status"] = "ready"  # validated in its ready form
    errs = V.validate_state(st, a.slug)
    op = L.mission_dir(project, a.slug) / "ORDRE.md"
    if not op.is_file():
        errs.append("ORDRE.md: missing at %s. Valid: the mission order file written during framing (phase P7)" % op)
    if errs:
        raise L.UsageError("cannot mark ready, %d problem(s):\n  - %s" % (len(errs), "\n  - ".join(errs)))
    st["criteria_sha256"] = L.criteria_digest(st)
    st["criteria_fingerprints"] = L.criteria_fingerprints(st)
    L.save_state(project, a.slug, st)
    print("ready: %s (criteria_sha256=%s)" % (a.slug, st["criteria_sha256"][:12]))
    return 0


def cmd_start(a, project):
    st = L.load_state(project, a.slug)
    sid = (a.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "")).strip()
    if not sid:
        raise L.UsageError("--session-id: missing and CLAUDE_CODE_SESSION_ID is not set. Valid: the current session id (run this command through the Bash tool, which sets CLAUDE_CODE_SESSION_ID, or pass --session-id ID)")
    if st.get("status") == "executing" and st.get("exec_session_id") == sid:
        print("already executing in this session: %s" % a.slug)
        return 0
    if st.get("status") == "executing" and a.reattach:
        st["exec_session_id"] = sid
        L.save_state(project, a.slug, st)
        print("re-attached: %s now belongs to session %s" % (a.slug, sid))
        return 0
    if st.get("status") != "ready":
        raise L.UsageError("status: %r cannot start. Valid: ready (run 'mission.py ready %s' after validate_order.py passes); "
                           "for a mission already executing whose session id changed (for example after /clear) use --reattach" % (st.get("status"), a.slug))
    errs = V.validate_state(st, a.slug)
    if errs:
        raise L.UsageError("cannot start, STATE.json is not valid (%d problem(s)):\n  - %s" % (len(errs), "\n  - ".join(errs)))
    st["status"] = "executing"
    st["exec_session_id"] = sid
    st["stop_blocks"] = 0
    L.save_state(project, a.slug, st)
    print("executing: %s (session %s)" % (a.slug, sid))
    return 0


def _remaining(st):
    caps = [c for c in st.get("capabilities", []) if isinstance(c, dict) and c.get("required") and not c.get("removed_reason")
            and not (isinstance(st.get("calls"), dict) and st["calls"].get(c.get("id"), 0))]
    ver = st.get("verification", {}) if isinstance(st.get("verification"), dict) else {}
    cmds = [c for c in ver.get("commands", []) if isinstance(c, dict) and c.get("state") in ("pending",)]
    crits = [c for c in ver.get("criteria", []) if isinstance(c, dict) and not c.get("passes")]
    return caps, cmds, crits


def cmd_status(a, project):
    st = L.load_state(project, a.slug)
    b = st.get("budget", {})
    caps, cmds, crits = _remaining(st)
    info = {
        "slug": a.slug, "status": st.get("status"), "class": st.get("class"), "tier": st.get("tier"),
        "lang": st.get("lang"), "level": st.get("level"),
        "budget_k": {"announced": b.get("announced_k"), "spent_est": b.get("spent_est_k"), "cap": b.get("cap_k")},
        "open": {"capabilities": len(caps), "verification_commands": len(cmds), "criteria": len(crits)},
        "exec_session_id": st.get("exec_session_id"), "stop_blocks": st.get("stop_blocks", 0),
        "dir": str(L.mission_dir(project, a.slug)),
    }
    if a.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
    else:
        print("%(slug)s: status=%(status)s class=%(class)s tier=%(tier)s lang=%(lang)s" % info)
        print("budget (k tokens): announced=%s spent~%s cap=%s" % (b.get("announced_k"), b.get("spent_est_k"), b.get("cap_k")))
        print("open: %d required capability(ies) not yet called, %d pending verification command(s), %d unmet criterion(a)" % (len(caps), len(cmds), len(crits)))
    return 0


def cmd_spent(a, project):
    st = L.load_state(project, a.slug)
    try:
        k = float(a.k)
    except ValueError:
        raise L.UsageError("k: %r is invalid. Valid: a number >= 0 (thousands of tokens)" % a.k)
    if k < 0 or k != k:
        raise L.UsageError("k: %r is invalid. Valid: a number >= 0 (thousands of tokens)" % a.k)
    b = st.setdefault("budget", {})
    cur = b.get("spent_est_k", 0) or 0
    new = round(cur + k, 3)
    b["spent_est_k"] = int(new) if new == int(new) else new
    L.save_state(project, a.slug, st)
    cap = b.get("cap_k")
    print("spent_est_k=%s cap_k=%s" % (b["spent_est_k"], cap))
    if isinstance(cap, (int, float)) and b["spent_est_k"] > cap:
        print("WARNING: estimated spend exceeds the cap; stop, report what is done and what remains.")
    return 0


def cmd_check(a, project):
    st = L.load_state(project, a.slug)
    caps, cmds, crits = _remaining(st)
    out = {
        "slug": a.slug,
        "status": st.get("status"),
        "ok": not (caps or cmds or crits),
        "capabilities_not_called": [{"id": c.get("id"), "name": c.get("name"), "call": c.get("call")} for c in caps],
        "verification_pending": [{"id": c.get("id"), "cmd": c.get("cmd"), "plan_b": c.get("plan_b")} for c in cmds],
        "criteria_unmet": [{"id": c.get("id"), "text": c.get("text")} for c in crits],
        "criteria_checked_by_test": L.criteria_report(st)[0],
        "criteria_self_reported": L.criteria_report(st)[1],
        "criteria_changed_since_ready": L.criteria_changes(st) or [],
        "report_present": (L.mission_dir(project, a.slug) / "REPORT.md").is_file(),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_waive(a, project):
    st = L.load_state(project, a.slug)
    reason = (a.reason or "").strip()
    if not reason:
        raise L.UsageError("--reason: empty. Valid: a sentence saying why the capability is dropped")
    for c in st.get("capabilities", []):
        if isinstance(c, dict) and c.get("id") == a.cap_id:
            c["removed_reason"] = reason
            L.save_state(project, a.slug, st)
            print("waived %s: %s" % (a.cap_id, reason))
            return 0
    ids = [c.get("id") for c in st.get("capabilities", []) if isinstance(c, dict)]
    raise L.UsageError("capability-id: %r not found. Valid: %s" % (a.cap_id, ", ".join(map(str, ids)) or "(no capabilities)"))


def cmd_verify(a, project):
    st = L.load_state(project, a.slug)
    _choice("--state", a.state, L.VERIF_STATES)
    if a.state in ("not_executable", "not_run") and not (a.reason or "").strip():
        raise L.UsageError("--reason: required when --state is not_executable or not_run. Valid: a sentence saying why")
    for c in st.get("verification", {}).get("commands", []):
        if isinstance(c, dict) and c.get("id") == a.cmd_id:
            c["state"] = a.state
            c["reason"] = (a.reason or "").strip() or None
            L.save_state(project, a.slug, st)
            print("%s -> %s" % (a.cmd_id, a.state))
            return 0
    ids = [c.get("id") for c in st.get("verification", {}).get("commands", []) if isinstance(c, dict)]
    raise L.UsageError("command-id: %r not found. Valid: %s" % (a.cmd_id, ", ".join(map(str, ids)) or "(no commands)"))


def cmd_criterion(a, project):
    st = L.load_state(project, a.slug)
    _choice("--passes", a.passes, ("yes", "no"))
    evidence = (a.evidence or "").strip()
    for c in st.get("verification", {}).get("criteria", []):
        if isinstance(c, dict) and c.get("id") == a.crit_id:
            if a.passes == "yes" and c.get("source") != "test" and not evidence:
                raise L.UsageError("--evidence: required when passing %s, whose source is %r (not test). Valid: one sentence "
                                   "naming the artifact, output or person that shows it passes" % (a.crit_id, c.get("source")))
            c["passes"] = a.passes == "yes"
            if c["passes"]:
                c["self_reported"] = c.get("source") != "test"
                if evidence:
                    c["evidence"] = evidence
            else:
                c["self_reported"] = False
            L.save_state(project, a.slug, st)
            print("%s passes=%s%s" % (a.crit_id, c["passes"], " (self-reported)" if c.get("self_reported") else ""))
            return 0
    ids = [c.get("id") for c in st.get("verification", {}).get("criteria", []) if isinstance(c, dict)]
    raise L.UsageError("criterion-id: %r not found. Valid: %s" % (a.crit_id, ", ".join(map(str, ids)) or "(no criteria)"))


def cmd_close(a, project):
    st = L.load_state(project, a.slug)
    d = L.mission_dir(project, a.slug)
    if a.abort:
        st["status"] = "aborted"
        L.save_state(project, a.slug, st)
        print("aborted: %s" % a.slug)
        return 0
    if st.get("status") != "executing":
        raise L.UsageError("status: %r cannot be closed. Valid: executing (use --abort to abandon any mission)" % st.get("status"))
    changed = L.criteria_changes(st)
    if changed:
        raise L.UsageError(
            "close refused: the acceptance criteria changed after approval (%s). Valid: restore the approved text from ORDRE.md, "
            "or run 'mission.py close %s --abort' and tell the user, who can approve a new order" % (", ".join(changed), a.slug))
    tally = L.count_tool_calls(a.transcript) if a.transcript else None
    missing = []
    for c in st.get("capabilities", []):
        if isinstance(c, dict) and c.get("required") and not L.cap_satisfied(c, st, tally):
            missing.append(c)
    if missing:
        lines = ["%s (%s): not called and no removed_reason" % (c.get("id"), c.get("name")) for c in missing]
        raise L.UsageError(
            "close refused, %d required capability(ies) neither called nor waived:\n  - %s\n"
            "Valid: call them, or run 'mission.py waive %s <id> --reason TEXT', or pass --transcript FILE so calls can be counted"
            % (len(missing), "\n  - ".join(lines), a.slug))
    if a.report:
        src = os.path.abspath(a.report)
        if not os.path.isfile(src):
            raise L.UsageError("--report: file %r not found. Valid: a path to the final report file" % a.report)
        dst = d / "REPORT.md"
        if os.path.abspath(str(dst)) != src:
            shutil.copyfile(src, str(dst))
    st["status"] = "done"
    L.save_state(project, a.slug, st)
    print("done: %s" % a.slug)
    tested, own, open_ = L.criteria_report(st)
    print("criteria: %d passed with a test source, %d self-reported (%s), %d open" % (len(tested), len(own), ", ".join(map(str, own)) or "-", len(open_)))
    if not (d / "REPORT.md").is_file():
        print("note: no REPORT.md in %s; pass --report FILE next time" % d)
    return 0


def cmd_path(a, project):
    L.check_slug(a.slug)
    d = L.mission_dir(project, a.slug)
    names = {"ORDRE": "ORDRE.md", "STATE": "STATE.json", "NOTES": "NOTES.md", "REPORT": "REPORT.md"}
    if a.file:
        print(str(d / names[a.file]))
    else:
        print(str(d))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(prog="mission.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", help="project directory (default: nearest ancestor containing .super-reprompt, else the current directory)")
    sub = ap.add_subparsers(dest="cmd")

    def add(name, fn, help_):
        p = sub.add_parser(name, help=help_)
        p.add_argument("slug")
        p.add_argument("--project", dest="project_sub", help=argparse.SUPPRESS)
        p.set_defaults(fn=fn)
        return p

    p = add("init", cmd_init, "create a mission")
    p.add_argument("--class", dest="cls", required=True, help="one of: " + ", ".join(L.CLASSES))
    p.add_argument("--tier", required=True, help="one of: " + ", ".join(L.TIERS))
    p.add_argument("--lang", required=True, help="user language code, e.g. fr, en")
    p.add_argument("--level", default="mixed", help="one of: " + ", ".join(L.LEVELS) + " (default mixed)")
    add("ready", cmd_ready, "validate then framing -> ready")
    p = add("start", cmd_start, "ready -> executing")
    p.add_argument("--session-id", help="session id (default: $CLAUDE_CODE_SESSION_ID)")
    p.add_argument("--reattach", action="store_true", help="for a mission already executing: move it to the current session id")
    p = add("status", cmd_status, "summary")
    p.add_argument("--json", action="store_true")
    p = add("spent", cmd_spent, "add spent thousands of tokens")
    p.add_argument("k", help="thousands of tokens to add (number >= 0)")
    add("check", cmd_check, "what is still open (JSON)")
    p = add("waive", cmd_waive, "drop a capability with a reason")
    p.add_argument("cap_id")
    p.add_argument("--reason", required=True)
    p = add("verify", cmd_verify, "record a verification state")
    p.add_argument("cmd_id")
    p.add_argument("--state", required=True, help="one of: " + ", ".join(L.VERIF_STATES))
    p.add_argument("--reason")
    p = add("criterion", cmd_criterion, "record a criterion result")
    p.add_argument("crit_id")
    p.add_argument("--passes", required=True, help="yes or no")
    p.add_argument("--evidence", help="required with --passes yes when the criterion source is not test")
    p = add("close", cmd_close, "executing -> done")
    p.add_argument("--report", help="final report file, copied to REPORT.md")
    p.add_argument("--transcript", help="transcript JSONL used to count capability calls")
    p.add_argument("--abort", action="store_true", help="mark the mission aborted instead of done")
    p = add("path", cmd_path, "print the mission folder (or one file)")
    p.add_argument("--file", choices=["ORDRE", "STATE", "NOTES", "REPORT"])
    return ap


def main(argv=None):
    L.setup_stdio()
    ap = build_parser()
    a = ap.parse_args(argv)
    if not getattr(a, "cmd", None):
        ap.print_help()
        return 2
    project = L.project_for_cli(getattr(a, "project_sub", None) or a.project)
    try:
        return a.fn(a, project)
    except L.UsageError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
