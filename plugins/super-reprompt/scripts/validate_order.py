# -*- coding: utf-8 -*-
"""Validate a mission's STATE.json (schema 1) and the presence of its ORDRE.md.

Usage:  validate_order.py <slug> [--project DIR]
Exit:   0 = valid, 2 = invalid input (each problem on stderr, naming the field and the valid values).
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402


def _strings(obj, path="$"):
    """Yield (path, string) for every string value in a JSON structure."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            for item in _strings(v, "%s.%s" % (path, k)):
                yield item
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            for item in _strings(v, "%s[%d]" % (path, i)):
                yield item


def scan_secrets(text):
    """Return a list of descriptions for secret-looking patterns in text."""
    hits = []
    for rx, label in L.SECRET_PATTERNS:
        if rx.search(text):
            hits.append(label)
    return hits


def _nonempty(v):
    return isinstance(v, str) and v.strip() != ""


def _oneof(errors, where, field, value, valid):
    if value not in valid:
        errors.append("%s: %s=%r is invalid. Valid: %s" % (where, field, value, ", ".join(valid)))


def _check_escalation(errs, esc, cmds):
    """Optional launch.escalation = {enabled, from, to, max_relaunches}."""
    where = "launch.escalation"
    if not isinstance(esc, dict):
        errs.append("%s: must be an object {enabled, from, to, max_relaunches}" % where)
        return
    en = esc.get("enabled")
    if not isinstance(en, bool):
        errs.append("%s.enabled=%r is invalid. Valid: true or false" % (where, en))
        return
    for key in ("from", "to"):
        if key in esc and esc.get(key) not in L.EFFORTS:
            errs.append("%s.%s=%r is invalid. Valid: %s" % (where, key, esc.get(key), ", ".join(L.EFFORTS)))
    mr = esc.get("max_relaunches", 0)
    if isinstance(mr, bool) or not isinstance(mr, int) or not 0 <= mr <= 2:
        errs.append("%s.max_relaunches=%r is invalid. Valid: an integer from 0 to 2 (1 or 2 when enabled is true)" % (where, mr))
    if en:
        if not cmds:
            errs.append("%s.enabled is true but verification.commands is empty. Valid: at least one executable verification command "
                        "in verification.commands, or set launch.escalation.enabled to false" % where)
        if esc.get("from") not in L.EFFORTS or esc.get("to") not in L.EFFORTS:
            errs.append("%s: from=%r and to=%r are required when enabled is true. Valid: efforts among %s" % (
                where, esc.get("from"), esc.get("to"), ", ".join(L.EFFORTS)))
        elif L.EFFORTS.index(esc["to"]) <= L.EFFORTS.index(esc["from"]):
            errs.append("%s: to=%r must be a higher effort than from=%r. Valid order: %s" % (where, esc["to"], esc["from"], " < ".join(L.EFFORTS)))
        if isinstance(mr, int) and not isinstance(mr, bool) and mr not in (1, 2):
            errs.append("%s.max_relaunches=%r is invalid when enabled is true. Valid: 1 or 2" % (where, mr))


def validate_state(state, slug=None):
    """Return a list of error strings (empty list = valid)."""
    errs = []
    w = "STATE.json"
    if not isinstance(state, dict):
        return ["%s: top level must be a JSON object" % w]

    if state.get("schema") != L.SCHEMA:
        errs.append("%s: schema=%r is invalid. Valid: %d" % (w, state.get("schema"), L.SCHEMA))
    sl = state.get("slug")
    if not isinstance(sl, str) or not L.SLUG_RE.match(sl):
        errs.append("%s: slug=%r is invalid. Valid: lowercase letters, digits, hyphens, at most 40 characters" % (w, sl))
    elif slug is not None and sl != slug:
        errs.append("%s: slug=%r does not match the folder name %r. Valid: the same value" % (w, sl, slug))
    if not _nonempty(state.get("lang")):
        errs.append("%s: lang is empty. Valid: a language code such as fr, en, es, de" % w)
    _oneof(errs, w, "level", state.get("level"), L.LEVELS)
    _oneof(errs, w, "class", state.get("class"), L.CLASSES)
    _oneof(errs, w, "tier", state.get("tier"), L.TIERS)
    _oneof(errs, w, "status", state.get("status"), L.STATUSES)

    # requirements
    reqs = state.get("requirements")
    if not isinstance(reqs, list):
        errs.append("%s: requirements must be a list (at most 10 items)" % w)
        reqs = []
    if len(reqs) > 10:
        errs.append("%s: requirements has %d items. Valid: at most 10 major requirements" % (w, len(reqs)))
    for i, r in enumerate(reqs):
        where = "requirements[%d]" % i
        if not isinstance(r, dict):
            errs.append("%s: must be an object with id, text, kind" % where)
            continue
        if not _nonempty(r.get("id")):
            errs.append("%s: id is empty. Valid: a short id such as R1" % where)
        if not _nonempty(r.get("text")):
            errs.append("%s: text is empty" % where)
        _oneof(errs, where, "kind", r.get("kind"), L.REQ_KINDS)

    # budget
    b = state.get("budget")
    if not isinstance(b, dict):
        errs.append("%s: budget must be an object with announced_k, spent_est_k, cap_k, exec_estimate_k" % w)
    else:
        nums = {}
        for key in ("announced_k", "spent_est_k", "cap_k"):
            v = b.get(key)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
                errs.append("budget: %s=%r is invalid. Valid: a number >= 0 (thousands of tokens)" % (key, v))
            else:
                nums[key] = v
        if "announced_k" in nums and "cap_k" in nums:
            if nums["announced_k"] > nums["cap_k"]:
                errs.append("budget: announced_k=%s exceeds cap_k=%s. Valid: announced_k <= cap_k" % (nums["announced_k"], nums["cap_k"]))
        if "cap_k" in nums and nums["cap_k"] > 100:
            errs.append("budget: cap_k=%s is invalid. Valid: cap_k <= 100" % nums["cap_k"])
        est = b.get("exec_estimate_k")
        if not (isinstance(est, list) and len(est) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in est)):
            errs.append("budget: exec_estimate_k=%r is invalid. Valid: a [low, high] pair of numbers, e.g. [150, 400]" % (est,))

    # permissions
    p = state.get("permissions")
    if not isinstance(p, dict):
        errs.append("%s: permissions must be an object with allow and deny lists" % w)
    else:
        deny = p.get("deny")
        if not (isinstance(deny, list) and len(deny) > 0 and all(_nonempty(x) for x in deny)):
            errs.append("permissions: deny=%r is invalid. Valid: a non-empty list of strings, e.g. %s" % (deny, json.dumps(L.DEFAULT_DENY)))
        if not isinstance(p.get("allow", []), list):
            errs.append("permissions: allow must be a list of strings")

    # capabilities
    caps = state.get("capabilities")
    if not isinstance(caps, list):
        errs.append("%s: capabilities must be a list" % w)
        caps = []
    per_phase = {}
    for i, c in enumerate(caps):
        where = "capabilities[%d]" % i
        if not isinstance(c, dict):
            errs.append("%s: must be an object" % where)
            continue
        label = "%s (%s %r)" % (where, c.get("id"), c.get("name"))
        if not _nonempty(c.get("id")):
            errs.append("%s: id is empty. Valid: a short id such as K1" % where)
        if not _nonempty(c.get("name")):
            errs.append("%s: name is empty" % label)
        _oneof(errs, label, "kind", c.get("kind"), L.CAP_KINDS)
        ph = c.get("phase")
        if ph not in L.PHASES:
            errs.append("%s: phase=%r is invalid. Valid: %s" % (label, ph, ", ".join(L.PHASES)))
        if not isinstance(c.get("required"), bool):
            errs.append("%s: required=%r is invalid. Valid: true or false" % (label, c.get("required")))
        if c.get("required") is True and not c.get("removed_reason"):
            for key in ("call", "proof", "plan_b"):
                if not _nonempty(c.get(key)):
                    errs.append("%s: required capability has no %r. Valid: a non-empty string (call = how it is invoked, proof = what shows it was called, plan_b = what to do if it cannot be called)" % (label, key))
        if not c.get("removed_reason"):
            per_phase[ph] = per_phase.get(ph, 0) + 1
    for ph, n in sorted(per_phase.items(), key=lambda kv: str(kv[0])):
        if n > 2:
            errs.append("capabilities: phase %s has %d active capabilities. Valid: at most 2 per phase" % (ph, n))

    # verification
    v = state.get("verification")
    cmds, crits = [], []
    if not isinstance(v, dict):
        errs.append("%s: verification must be an object with commands and criteria lists" % w)
    else:
        cmds = v.get("commands") if isinstance(v.get("commands"), list) else None
        crits = v.get("criteria") if isinstance(v.get("criteria"), list) else None
        if cmds is None:
            errs.append("verification: commands must be a list"); cmds = []
        if crits is None:
            errs.append("verification: criteria must be a list"); crits = []
    if state.get("class") == "CODE" and len(cmds) < 1:
        errs.append("verification: class CODE has no verification command. Valid: at least one entry in verification.commands (id, cmd, state, plan_b)")
    for i, cmd in enumerate(cmds):
        where = "verification.commands[%d]" % i
        if not isinstance(cmd, dict):
            errs.append("%s: must be an object" % where)
            continue
        label = "%s (%s)" % (where, cmd.get("id"))
        if not _nonempty(cmd.get("id")):
            errs.append("%s: id is empty. Valid: a short id such as V1" % where)
        if not _nonempty(cmd.get("cmd")):
            errs.append("%s: cmd is empty. Valid: the command line to run" % label)
        _oneof(errs, label, "state", cmd.get("state"), L.VERIF_STATES)
        if not _nonempty(cmd.get("plan_b")):
            errs.append("%s: verification without plan B (plan_b is empty). Valid: what to do or to declare if the command cannot run (state not_executable) or is not run (not_run)" % label)
    for i, cr in enumerate(crits):
        where = "verification.criteria[%d]" % i
        if not isinstance(cr, dict):
            errs.append("%s: must be an object" % where)
            continue
        label = "%s (%s)" % (where, cr.get("id"))
        if not _nonempty(cr.get("id")):
            errs.append("%s: id is empty. Valid: a short id such as C1" % where)
        if not _nonempty(cr.get("text")):
            errs.append("%s: text is empty. Valid: a yes/no statement a stranger can decide" % label)
        if cr.get("unsourced") is True:
            continue
        if cr.get("source") not in L.CRIT_SOURCES:
            errs.append("%s: source=%r is invalid and unsourced is not true. Valid: %s, or set unsourced=true" % (label, cr.get("source"), ", ".join(L.CRIT_SOURCES)))
        if not _nonempty(cr.get("proof")):
            errs.append("%s: proof is empty and unsourced is not true. Valid: what evidence shows the criterion passes, or set unsourced=true" % label)

    # agents
    ags = state.get("agents", [])
    if not isinstance(ags, list):
        errs.append("%s: agents must be a list" % w)
        ags = []
    for i, a in enumerate(ags):
        where = "agents[%d]" % i
        if not isinstance(a, dict):
            errs.append("%s: must be an object" % where)
            continue
        if not _nonempty(a.get("name")):
            errs.append("%s: name is empty" % where)
        if not _nonempty(a.get("model")):
            errs.append("%s: model is empty. Valid: an alias such as sonnet, opus, haiku or a full model id" % where)
        if a.get("effort") not in L.EFFORTS:
            errs.append("%s: effort=%r is invalid. Valid: %s" % (where, a.get("effort"), ", ".join(L.EFFORTS)))
        mt = a.get("max_turns")
        if isinstance(mt, bool) or not isinstance(mt, int) or mt < 1:
            errs.append("%s: max_turns=%r is invalid. Valid: an integer >= 1" % (where, mt))
        if a.get("isolation", "none") not in L.ISOLATIONS:
            errs.append("%s: isolation=%r is invalid. Valid: %s" % (where, a.get("isolation"), ", ".join(L.ISOLATIONS)))
        rm = a.get("report_max_tokens")
        if isinstance(rm, bool) or not isinstance(rm, int) or rm < 1:
            errs.append("%s: report_max_tokens=%r is invalid. Valid: an integer >= 1" % (where, rm))

    # launch
    la = state.get("launch")
    if not isinstance(la, dict):
        errs.append("%s: launch must be an object with model, effort, permission_mode, name, unattended" % w)
    else:
        if not _nonempty(la.get("model")):
            errs.append("launch: model is empty. Valid: an alias such as sonnet, opus, haiku or a full model id")
        if la.get("effort") not in L.EFFORTS:
            errs.append("launch: effort=%r is invalid. Valid: %s" % (la.get("effort"), ", ".join(L.EFFORTS)))
        if la.get("permission_mode") not in L.PERMISSION_MODES:
            errs.append("launch: permission_mode=%r is invalid. Valid: %s" % (la.get("permission_mode"), ", ".join(L.PERMISSION_MODES)))
        if not _nonempty(la.get("name")):
            errs.append("launch: name is empty. Valid: the session name, normally the slug")
        if not isinstance(la.get("unattended"), bool):
            errs.append("launch: unattended=%r is invalid. Valid: true or false" % (la.get("unattended"),))
        if "escalation" in la:
            _check_escalation(errs, la.get("escalation"), cmds)

    cs = state.get("criteria_sha256")
    if cs is not None and not (isinstance(cs, str) and re.match(r"^[0-9a-f]{64}$", cs)):
        errs.append("%s: criteria_sha256=%r is invalid. Valid: a 64-character lowercase hex SHA-256 written by 'mission.py ready'" % (w, cs))
    cf = state.get("criteria_fingerprints")
    if cf is not None and not (isinstance(cf, dict) and all(isinstance(k, str) and isinstance(x, str) for k, x in cf.items())):
        errs.append("%s: criteria_fingerprints must be an object mapping criterion ids to strings (written by 'mission.py ready')" % w)
    for i, cr in enumerate(crits):
        if isinstance(cr, dict):
            if "self_reported" in cr and not isinstance(cr["self_reported"], bool):
                errs.append("verification.criteria[%d]: self_reported=%r is invalid. Valid: true or false" % (i, cr["self_reported"]))
            if "evidence" in cr and not isinstance(cr["evidence"], str):
                errs.append("verification.criteria[%d]: evidence must be a string" % i)

    sb = state.get("stop_blocks", 0)
    if isinstance(sb, bool) or not isinstance(sb, int) or sb < 0:
        errs.append("%s: stop_blocks=%r is invalid. Valid: an integer >= 0" % (w, sb))

    # secrets anywhere in the state
    for path, s in _strings(state):
        for label in scan_secrets(s):
            errs.append("%s: %s looks like a secret (%s). Remove it; the plugin never stores API keys or tokens" % (w, path, label))
    return errs


def validate_mission(project, slug):
    """Return (errors, warnings) for a mission folder."""
    errs, warns = [], []
    L.check_slug(slug)
    sp = L.state_path(project, slug)
    if not sp.is_file():
        raise L.UsageError("slug: no mission %r under %s. Existing missions: %s" % (
            slug, os.path.join(str(project), L.STATE_DIRNAME), ", ".join(L.list_slugs(project)) or "(none)"))
    try:
        with open(str(sp), "r", encoding="utf-8-sig") as f:
            state = json.load(f)
    except Exception as exc:
        return ["STATE.json: not valid JSON (%s). Valid: a JSON object following schema 1" % exc], warns
    errs.extend(validate_state(state, slug))
    op = L.mission_dir(project, slug) / "ORDRE.md"
    if not op.is_file():
        errs.append("ORDRE.md: missing at %s. Valid: the mission order file written during framing (phase P7)" % op)
    else:
        try:
            text = op.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            text = ""
            errs.append("ORDRE.md: cannot read (%s)" % exc)
        if text and not text.strip():
            errs.append("ORDRE.md: file is empty. Valid: the 11 sections of the mission order")
        for label in scan_secrets(text):
            errs.append("ORDRE.md: contains something that looks like a secret (%s). Remove it" % label)
        heads = len(re.findall(r"(?m)^#{1,3}\s+\S", text))
        if text.strip() and heads < 11:
            warns.append("ORDRE.md: only %d headings found; the order is expected to have 11 sections" % heads)
    return errs, warns


def main(argv=None):
    L.setup_stdio()
    ap = argparse.ArgumentParser(description="Validate a super-reprompt mission (STATE.json + ORDRE.md).")
    ap.add_argument("slug", help="mission slug (lowercase letters, digits, hyphens, at most 40 characters)")
    ap.add_argument("--project", help="project directory (default: nearest ancestor containing .super-reprompt, else the current directory)")
    args = ap.parse_args(argv)
    try:
        project = L.project_for_cli(args.project)
        errs, warns = validate_mission(project, args.slug)
    except L.UsageError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2
    for wmsg in warns:
        sys.stderr.write("warning: %s\n" % wmsg)
    if errs:
        for e in errs:
            sys.stderr.write("error: %s\n" % e)
        sys.stderr.write("validation failed: %d error(s)\n" % len(errs))
        return 2
    print("OK: mission %s is valid (%d warning(s))" % (args.slug, len(warns)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
