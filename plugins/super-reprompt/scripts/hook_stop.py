# -*- coding: utf-8 -*-
"""Stop hook (H3): completion gate for an EXECUTING mission. Silent for every other session.

Acts only when a mission under the project has status "executing" and exec_session_id equal to this session's id.
Then it checks, in order:
  1. the verification commands declared in STATE.json (those still "pending", or that failed last time) are run
     (120 s each, 240 s in total, refused if they look destructive or networked) and their state is recorded;
  2. every required capability was called (counted from the transcript) or has a removed_reason;
  3. REPORT.md exists in the mission folder.
If something is missing it blocks the stop with {"decision": "block", "reason": "..."} (exit code 0, at most 80
words), at most 3 times (STATE.json stop_blocks). After that it lets Claude stop and appends a line
"non executable : <reason>" to NOTES.md. It does nothing when the last assistant message ends with a question
(Claude is waiting for the user). Any internal error exits 0. SUPER_REPROMPT_HOOKS=0 turns the hook off.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

MAX_BLOCKS = 3
CMD_TIMEOUT_S = 120
TOTAL_BUDGET_S = 240
MAX_WORDS = 80

# A verification command is a test or a check, not a deployment. Refuse anything that looks destructive or networked.
REFUSED_RX = re.compile(
    r"(\bgit\s+push\b|\brm\s+-[a-z]*r|\brmdir\b|\bdel\s+/|\bformat\s+[a-z]:|\bmkfs\b|\bshutdown\b|\breboot\b|\bsudo\b|"
    r"\bcurl\b|\bwget\b|\binvoke-webrequest\b|\biwr\b|\bssh\b|\bscp\b|\bnc\s|\bftp\b|\bgit\s+(reset\s+--hard|clean)\b|\|\s*(sh|bash|zsh|iex)\b)",
    re.IGNORECASE)
NOT_FOUND_RX = re.compile(r"(is not recognized as an internal or external command|command not found|not found$|No such file or directory|"
                          r"is not recognized as the name of a cmdlet|cannot find the path)", re.IGNORECASE | re.MULTILINE)


SHELL_WORDS = {"exit", "echo", "cd", "set", "type", "dir", "ls", "cat", "true", "false", "test", "[", "export", "pushd", "popd",
               "call", "if", "for", "rem", "cls", "pwd", "source", ".", ":", "exec", "eval", "command", "time", "env", "start", "pause"}


def first_token_missing(cmd, project):
    """True if the first word of a command line is neither a shell word nor an executable we can find.

    Error messages for unknown commands are localised (and cmd.exe exits 1), so exit codes and text are not
    reliable; looking the program up first is."""
    try:
        tokens = shlex.split(cmd.strip(), posix=(os.name != "nt"))
    except ValueError:
        return False
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return False
    tok = tokens[0].strip("\"'")
    if not tok or tok.lower() in SHELL_WORDS or tok.startswith(("(", "@", "%", "$")):
        return False
    if "/" in tok or "\\" in tok or tok.startswith("."):
        return not (os.path.exists(tok) or os.path.exists(os.path.join(str(project), tok)))
    return shutil.which(tok) is None


def waiting_for_user(last):
    if not isinstance(last, str):
        return False
    lines = [ln.strip() for ln in last.strip().splitlines() if ln.strip()]
    return bool(lines) and lines[-1].endswith(("?", "？"))


def tail(text, n=160):
    text = " ".join((text or "").split())
    return text[-n:]


def run_verifications(project, st, notes):
    """Run pending/failed verification commands; update their state in place. Returns problems (list of str)."""
    problems = []
    cmds = st.get("verification", {}).get("commands", []) if isinstance(st.get("verification"), dict) else []
    t0 = time.time()
    for c in cmds:
        if not isinstance(c, dict) or not c.get("cmd"):
            continue
        state = c.get("state")
        failed_before = state == "executed" and isinstance(c.get("exit_code"), int) and c.get("exit_code") != 0
        if state not in ("pending",) and not failed_before:
            continue
        cid = c.get("id")
        cmd = str(c["cmd"])
        if REFUSED_RX.search(cmd):
            c["state"] = "not_executable"
            c["reason"] = "refused by the stop hook: the command looks destructive or networked"
            notes.append("%s refused (%s)" % (cid, c["reason"]))
            continue
        if time.time() - t0 > TOTAL_BUDGET_S:
            problems.append("%s not run yet (hook time budget used up); run it yourself or record not_run with a reason" % cid)
            continue
        if first_token_missing(cmd, project):
            c["state"] = "not_executable"
            c["reason"] = "program not found on this machine: %s" % cmd.split()[0][:40]
            notes.append("%s not executable: %s" % (cid, c["reason"]))
            continue
        try:
            r = subprocess.run(cmd, shell=True, cwd=str(project), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               timeout=CMD_TIMEOUT_S, universal_newlines=True, encoding="utf-8", errors="replace")
            out = r.stdout or ""
            if r.returncode in (127, 9009) or (r.returncode != 0 and NOT_FOUND_RX.search(out[:400] or "")):
                c["state"] = "not_executable"
                c["reason"] = "command not found or not runnable here (exit %d)" % r.returncode
                notes.append("%s not executable: %s" % (cid, c["reason"]))
            else:
                c["state"] = "executed"
                c["exit_code"] = r.returncode
                c["reason"] = None
                if r.returncode != 0:
                    problems.append("%s failed (exit %d): %s" % (cid, r.returncode, tail(out)))
        except subprocess.TimeoutExpired:
            c["state"] = "not_executable"
            c["reason"] = "timed out after %d s" % CMD_TIMEOUT_S
            notes.append("%s not executable: %s" % (cid, c["reason"]))
        except Exception as exc:
            c["state"] = "not_executable"
            c["reason"] = "could not start: %s" % type(exc).__name__
            notes.append("%s not executable: %s" % (cid, c["reason"]))
    return problems


def clip_words(text, n=MAX_WORDS):
    words = text.split()
    return text if len(words) <= n else " ".join(words[:n]) + " ..."


def body():
    data = L.read_stdin_json()
    sid = data.get("session_id")
    if not sid:
        return
    cwd = data.get("cwd") or os.getcwd()
    project = L.find_project(cwd)
    if project is None:
        env = os.environ.get("CLAUDE_PROJECT_DIR", "")
        project = L.find_project(env) if env else None
    if project is None:
        return
    found = None
    for slug, st in L.iter_missions(project):
        if st.get("status") == "executing" and st.get("exec_session_id") == sid:
            found = (slug, st)
            break
    if found is None:
        return
    slug, st = found
    if waiting_for_user(data.get("last_assistant_message")):
        L.log("hook_stop", "%s: last message is a question, not gating" % slug)
        return

    d = L.mission_dir(project, slug)
    fr = L.lang_is_french(st.get("lang"))
    notes = []
    problems = run_verifications(project, st, notes)

    tpath = data.get("transcript_path")
    if isinstance(tpath, str) and tpath:
        tally = L.count_tool_calls(tpath)
        calls = st.get("calls") if isinstance(st.get("calls"), dict) else {}
        for cap in st.get("capabilities", []):
            if isinstance(cap, dict) and cap.get("id") and L.capability_called(cap, tally):
                calls[cap["id"]] = max(1, calls.get(cap["id"], 0))
        if calls:
            st["calls"] = calls
        for cap in st.get("capabilities", []):
            if isinstance(cap, dict) and cap.get("required") and not L.cap_satisfied(cap, st, tally):
                problems.append("required capability %s (%s) was never called" % (cap.get("id"), cap.get("name")))
    else:
        L.log("hook_stop", "%s: no transcript_path, capability check skipped" % slug)

    try:
        changed = L.criteria_changes(st)
        if changed and not st.get("criteria_warned"):
            st["criteria_warned"] = True
            problems.append("acceptance criteria changed after approval (%s); restore the approved text or report the change" % ", ".join(changed))
    except Exception:
        pass

    rp = d / "REPORT.md"
    try:
        has_report = rp.is_file() and rp.stat().st_size > 0
    except Exception:
        has_report = False
    if not has_report:
        problems.append("final report missing (write REPORT.md in the mission folder)")

    blocks = st.get("stop_blocks", 0) if isinstance(st.get("stop_blocks"), int) else 0
    if not problems:
        L.save_state(project, slug, st)
        L.log("hook_stop", "%s: gate passed" % slug)
        return
    if blocks >= MAX_BLOCKS:
        line = ("non exécutable : %s" if fr else "not executable: %s") % "; ".join(problems)
        try:
            with open(str(d / "NOTES.md"), "a", encoding="utf-8", newline="\n") as f:
                f.write("\n%s - %s\n" % (L.now_iso(), line))
        except Exception:
            pass
        L.save_state(project, slug, st)
        L.log("hook_stop", "%s: %d blocks reached, letting the session stop" % (slug, blocks))
        return
    st["stop_blocks"] = blocks + 1
    L.save_state(project, slug, st)
    if fr:
        reason = ("Mission %s inachevée (blocage %d/%d) : %s. Corrige, ou si c'est impossible enregistre-le "
                  "(mission.py waive / verify --state not_executable --reason) et dis-le dans REPORT.md."
                  % (slug, blocks + 1, MAX_BLOCKS, "; ".join(problems)))
    else:
        reason = ("Mission %s is not finished (block %d/%d): %s. Fix it, or if impossible record it "
                  "(mission.py waive / verify --state not_executable --reason) and say so in REPORT.md."
                  % (slug, blocks + 1, MAX_BLOCKS, "; ".join(problems)))
    L.emit(json.dumps({"decision": "block", "reason": clip_words(reason)}, ensure_ascii=False))
    L.log("hook_stop", "%s: blocked %d/%d (%d problem(s))" % (slug, blocks + 1, MAX_BLOCKS, len(problems)))


def main():
    return L.run_hook("hook_stop", body, __doc__)


if __name__ == "__main__":
    sys.exit(main())
