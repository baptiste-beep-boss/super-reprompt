# -*- coding: utf-8 -*-
"""Launch a ready mission as a background Claude Code session.

Usage:  launch.py <slug> [--project DIR] [--dry-run]

Builds and runs:
  claude --bg --name <slug> --model <m> --effort <e> --permission-mode <p> "<short prompt>"
where model, effort and permission mode come from STATE.json (launch.*). The short prompt tells the new
session to read .super-reprompt/<slug>/ORDRE.md in full and to run `mission.py start` first.

Never uses /fork or /bg. Starting `claude --bg` makes a session that consumes your Claude usage: use --dry-run
to see the exact command without running it.

Exit codes: 0 success, 2 invalid input, 3 fallback (claude missing or too old: manual instructions are printed).
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
import validate_order as V  # noqa: E402

MIN_VERSION = (2, 1, 212)  # value given by the contract; the docs do not state a minimum for --bg (UNVERIFIED)


def parse_version(text):
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else None


def run_quiet(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, universal_newlines=True,
                           encoding="utf-8", errors="replace")
        return r.returncode, r.stdout or ""
    except Exception as exc:
        return 127, str(exc)


def detect_claude():
    """Return (path, version_tuple_or_None, supports_bg) or (None, None, False)."""
    path = shutil.which("claude")
    if not path:
        return None, None, False
    _rc, out = run_quiet([path, "--version"])
    ver = parse_version(out)
    _rc, helptext = run_quiet([path, "--help"])
    supports_bg = bool(re.search(r"(^|\s)--bg\b", helptext))
    return path, ver, supports_bg


def build_command(claude_path, slug, state, mission_py):
    la = state["launch"]
    exe = sys.executable or "python3"
    prompt = (
        "Read .super-reprompt/%s/ORDRE.md in full, then execute it. "
        "First action: run \"%s\" \"%s\" start %s" % (slug, exe, mission_py.replace("\\", "/"), slug)
    )
    return [claude_path, "--bg", "--name", la.get("name") or slug, "--model", str(la["model"]),
            "--effort", str(la["effort"]), "--permission-mode", str(la["permission_mode"]), prompt]


def fallback_text(slug, state, project, reason):
    la = state.get("launch", {}) if isinstance(state, dict) else {}
    return (
        "%s\nManual fallback (no background launch):\n"
        "  1. Open a NEW Claude Code session in %s\n"
        "  2. Optionally set the model with /model %s and the effort with /effort %s\n"
        "  3. Paste: Read .super-reprompt/%s/ORDRE.md in full, then execute it. First action: run mission.py start %s\n"
        % (reason, project, la.get("model", "sonnet"), la.get("effort", "medium"), slug, slug)
    )


def main(argv=None):
    L.setup_stdio()
    ap = argparse.ArgumentParser(description="Launch a ready super-reprompt mission with `claude --bg`.")
    ap.add_argument("slug", help="mission slug")
    ap.add_argument("--project", help="project directory (default: nearest ancestor containing .super-reprompt, else the current directory)")
    ap.add_argument("--dry-run", action="store_true", help="print the command without running it")
    a = ap.parse_args(argv)
    try:
        project = L.project_for_cli(a.project)
        st = L.load_state(project, a.slug)
        if st.get("status") != "ready":
            raise L.UsageError("status: %r cannot be launched. Valid: ready (run validate_order.py then 'mission.py ready %s')" % (st.get("status"), a.slug))
        errs, _w = V.validate_mission(project, a.slug)
        if errs:
            raise L.UsageError("mission is not valid (%d problem(s)):\n  - %s" % (len(errs), "\n  - ".join(errs)))
    except L.UsageError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 2

    mission_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mission.py")
    path, ver, supports_bg = detect_claude()
    if not path:
        sys.stdout.write(fallback_text(a.slug, st, project, "`claude` was not found on PATH."))
        return 3
    if not supports_bg:
        sys.stdout.write(fallback_text(a.slug, st, project, "this `claude` (%s) does not list the --bg option." % (".".join(map(str, ver)) if ver else "unknown version")))
        return 3
    if ver and ver < MIN_VERSION:
        sys.stderr.write("warning: claude %s is older than %s (version floor from the contract); --bg is listed in --help so continuing\n" % (
            ".".join(map(str, ver)), ".".join(map(str, MIN_VERSION))))
    cmd = build_command(path, a.slug, st, mission_py)
    shown = " ".join('"%s"' % c if (" " in c or not c) else c for c in cmd)
    if a.dry_run:
        print("DRY RUN (nothing executed). cwd=%s" % project)
        print(shown)
        return 0
    try:
        r = subprocess.run(cmd, cwd=str(project), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
                           encoding="utf-8", errors="replace", timeout=120)
    except Exception as exc:
        sys.stdout.write(fallback_text(a.slug, st, project, "launching failed (%s)." % exc))
        return 3
    sys.stdout.write(r.stdout or "")
    if r.returncode != 0:
        sys.stdout.write(fallback_text(a.slug, st, project, "`claude --bg` exited with code %d." % r.returncode))
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
