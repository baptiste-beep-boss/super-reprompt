# -*- coding: utf-8 -*-
"""accept.py : the A1-A24 acceptance table of super-reprompt v3 (CDC §12). Standard library only, no network.

Rule: nothing is green without an execution in THIS run. Each criterion is one of
  suite  the whole test suite ran and passed                                    (A1)
  tests  named test classes / tests ran in this run and all passed (skips do not count)
  cmd    a command ran here; its exit code decides (127 = tool missing -> not measured)
  func   a measurement done here (timing, file checks)
  none   cannot be executed here: the reason is printed (never green)

  py -3 dev/accept.py            runs the full suite once (about 6 min), then every command
  py -3 dev/accept.py --quick    skips the suite: every suite/tests criterion prints "non mesure"
Exit code 0 only if every criterion is green.
"""
import argparse
import os
import re
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.join(ROOT, "tests")
PY = sys.executable

CRITERIA = [
    {"id": "A1", "titre": "suite d'origine et tests v3 verts", "kind": "suite", "preuve": "py -3 -m unittest discover -s tests"},
    {"id": "A2", "titre": "plafonds v3, SKILL.md <= 4 950", "kind": "cmd", "cmd": [PY, "dev/measure_loading.py", "--check"],
     "preuve": "py -3 dev/measure_loading.py --check"},
    {"id": "A3", "titre": "silence sur demande triviale", "kind": "tests", "tests": ["test_silence"], "preuve": "unittest test_silence"},
    {"id": "A4", "titre": "cout au repos <= 1 500 tokens", "kind": "tests", "tests": ["test_l9_migration.A4CoutAuRepos"],
     "preuve": "unittest test_l9_migration.A4CoutAuRepos (mesure statique ; /context avant-apres non rejoue)"},
    {"id": "A5", "titre": "catalogue : 0 ecart, 0 non classe", "kind": "tests", "tests": ["test_catalog.A5"], "preuve": "unittest test_catalog.A5"},
    {"id": "A6", "titre": "atteignabilite >= 95 %", "kind": "tests", "tests": ["test_catalog.A6"], "preuve": "unittest test_catalog.A6"},
    {"id": "A7", "titre": "40 elements executes >= 95 %", "kind": "tests", "tests": ["test_catalog.A7"],
     "preuve": "unittest test_catalog.A7 (relit catalog/a7-executions.json, executions reelles du lot L5)"},
    {"id": "A8", "titre": "barre conforme a la photo, 7 etats", "kind": "none", "preuve": "captures dans l'app",
     "raison": "barre en pause sur decision de l'utilisateur (23/11/2026) ; rendu dans l'app non capture"},
    {"id": "A9", "titre": "avancement monotone, erreur de temps", "kind": "tests", "tests": ["test_bar"], "preuve": "unittest test_bar"},
    {"id": "A10", "titre": "recherche vault < 150 ms a froid (-I -S)", "kind": "func", "func": "a10", "preuve": "5 x py -3 -I -S scripts/vault.py search, mediane"},
    {"id": "A11", "titre": "vault.py lint : 0 orpheline creee", "kind": "tests", "tests": ["test_vault.TestLint"], "preuve": "unittest test_vault.TestLint"},
    {"id": "A12", "titre": "Relais : 18 types, deux sens", "kind": "tests", "tests": ["test_relais_verify.A12Verifiers"], "preuve": "unittest test_relais_verify"},
    {"id": "A13", "titre": "50 tentatives : 0 secret sorti", "kind": "tests", "tests": ["test_relais.A13NoExfiltration"], "preuve": "unittest test_relais.A13NoExfiltration"},
    {"id": "A14", "titre": "panne d'un puis de tous", "kind": "tests",
     "tests": ["test_relais.EndToEnd.test_a14_one_provider_down_mission_continues", "test_relais.EndToEnd.test_a14_all_providers_down_falls_back_to_haiku_then_sonnet"],
     "preuve": "unittest test_relais.EndToEnd.test_a14_*"},
    {"id": "A15", "titre": "aucun fournisseur exclu joignable", "kind": "tests",
     "tests": ["test_relais.Providers.test_a15_no_excluded_provider_is_listed_or_reachable", "test_relais.EndToEnd.test_redirects_are_never_followed"],
     "preuve": "unittest test_relais.Providers.test_a15_*"},
    {"id": "A16", "titre": "cle invisible (logs, arguments, depot)", "kind": "tests",
     "tests": ["test_relais.KeyStoreDPAPI.test_a16_key_invisible_in_logs_args_ledger_and_repo"], "preuve": "unittest test_relais.KeyStoreDPAPI (Windows)"},
    {"id": "A17", "titre": "40 attaques : 100 % bloquees ou detectees", "kind": "tests",
     "tests": ["test_guard.Guard.test_a17_attacks_blocked_or_detected", "test_guard.Guard.test_a17_red_data_and_relais_blocked"], "preuve": "unittest test_guard (A17)"},
    {"id": "A18", "titre": "<= 3 faux positifs sur 100", "kind": "tests", "tests": ["test_guard.Guard.test_a18_legitimate_actions_pass"], "preuve": "unittest test_guard (A18)"},
    {"id": "A19", "titre": "Eclaireur >= 85 % et pieges arretes", "kind": "tests", "tests": ["test_eclaireur.A19Besoins", "test_skillscan.Pieges"],
     "preuve": "unittest test_eclaireur.A19Besoins test_skillscan.Pieges"},
    {"id": "A20", "titre": "hook < 120 ms en mediane", "kind": "func", "func": "a20", "preuve": "py -3 dev/bench_guard.py (mediane du hook dans une mission)"},
    {"id": "A21", "titre": "licences et empreintes completes", "kind": "tests", "tests": ["test_catalog.A21", "test_v3_invariants.I6Lock"], "preuve": "unittest test_catalog.A21 test_v3_invariants.I6Lock"},
    {"id": "A22", "titre": "Windows et Linux verts (CI GitHub)", "kind": "func", "func": "a22",
     "preuve": "workflow .github/workflows/ci.yml relu par script ; CI reelle = apres push (accord requis)"},
    {"id": "A23", "titre": "desinstallation sans trace", "kind": "tests", "tests": ["test_uninstall"], "preuve": "unittest test_uninstall"},
    {"id": "A24", "titre": "comparaison a 4 bras", "kind": "none", "preuve": "evals/v3-a24/PROTOCOLE.md ; py -3 dev/a24_manifest.py --check",
     "raison": "banc prepare, NON lance : cout eleve, accord ecrit de l'utilisateur requis (CDC §12)"},
]


# ------------------------------------------------------------------ suite
_VERBOSE = re.compile(r"^(\w+) \(([\w.]+)\)(?:\n.*?)?\s\.\.\. (ok|FAIL|ERROR|skipped|expected failure|unexpected success)", re.M)
_STATE = {"ok": "ok", "FAIL": "fail", "ERROR": "error", "skipped": "skip", "expected failure": "ok", "unexpected success": "fail"}


def parse_verbose(err):
    """unittest -v writes one result line per test on stderr: 'name (module.Class.name) ... ok'."""
    out = {}
    for m in _VERBOSE.finditer(err):
        tid = m.group(2) if m.group(2).endswith("." + m.group(1)) else m.group(2) + "." + m.group(1)
        out.setdefault(tid, _STATE[m.group(3)])
    return out


def run_suite(timeout=3600):
    """-> {test_id: ok|fail|error|skip}. The suite runs in a CHILD process (an in-process run hung once: L10, 24/11/2026)."""
    try:
        p = subprocess.run([PY, "-m", "unittest", "discover", "-s", TESTS, "-v"], cwd=TESTS, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {}
    return parse_verbose(p.stderr.decode("utf-8", "replace"))


def run_cmd(cmd, timeout=900):
    try:
        p = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except FileNotFoundError:
        return 127, "commande introuvable"
    except subprocess.TimeoutExpired:
        return 124, "delai depasse"
    return p.returncode, p.stdout.decode("utf-8", "replace")


# ------------------------------------------------------------------ measurements
def f_a10(run):
    idx = os.environ.get("SR_VAULT_DB") or os.path.join(os.path.expanduser("~"), ".claude", "super-reprompt", "vault-index")
    if not os.path.exists(idx):
        return "non mesure", "index du vault absent (lancer vault.py index sur le vrai vault, hors depot)"
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        rc, _o = run([PY, "-I", "-S", "scripts/vault.py", "search", "relais"])
        times.append((time.perf_counter() - t0) * 1000)
        if rc == 3:
            return "non mesure", "index du vault absent sur cette machine (vault.py index, hors depot)"
        if rc not in (0, 1):
            return "rouge", "vault.py search code %d" % rc
    med = statistics.median(times)
    return ("vert" if med < 150 else "rouge"), "mediane %.0f ms sur 5 commandes froides" % med


def f_a20(run):
    rc, out = run([PY, "dev/bench_guard.py"])
    m = re.search(r"A20 (?:FAIL|OK|PASS): median (\d+) ms", out)          # the bench's own verdict line (rc 1 = FAIL)
    floor = re.search(r"interpreter floor.*?median (\d+) ms", out)
    if not m or rc not in (0, 1):
        return "non mesure", "bench_guard.py code %d, pas de ligne de verdict" % rc
    med = int(m.group(1))
    return ("vert" if med < 120 else "rouge"), "mediane %d ms (plancher interpreteur %s ms ; machine chargee)" % (med, floor.group(1) if floor else "?")


def f_a22(run):
    wf = os.path.join(os.path.dirname(os.path.dirname(ROOT)), ".github", "workflows", "ci.yml")
    if not os.path.isfile(wf):
        return "rouge", "workflow CI absent"
    with open(wf, encoding="utf-8") as f:
        t = f.read()
    need = ("windows-latest", "ubuntu-latest", "unittest discover", "actions/checkout", "actions/setup-python")
    miss = [n for n in need if n not in t]
    if miss or "\t" in t:
        return "rouge", "workflow incomplet : %s" % ", ".join(miss or ["tabulation"])
    return "non mesure", "workflow Windows + Linux pret et relu ; CI reelle jamais executee (push = accord requis) ; Linux local : python3 absent de WSL"


FUNCS = {"a10": f_a10, "a20": f_a20, "a22": f_a22}


# ------------------------------------------------------------------ evaluation
def evaluate(c, results, run):
    """-> {id, titre, etat, detail, preuve}. results: dict from run_suite(), or None when the suite did not run."""
    row = {"id": c["id"], "titre": c.get("titre", ""), "preuve": c["preuve"]}
    k = c["kind"]
    if k == "none":
        return dict(row, etat="non mesure", detail=c["raison"])
    if k == "suite":
        if not results:
            return dict(row, etat="non mesure", detail="suite non lancee (--quick)")
        bad = sorted(t for t, s in results.items() if s in ("fail", "error"))
        if bad:
            return dict(row, etat="rouge", detail="%d/%d en echec : %s" % (len(bad), len(results), ", ".join(bad)[:300]))
        return dict(row, etat="vert", detail="%d tests, 0 echec (%d sautes)" % (len(results), sum(1 for s in results.values() if s == "skip")))
    if k == "tests":
        if not results:
            return dict(row, etat="non mesure", detail="suite non lancee (--quick)")
        hit = {t: s for t, s in results.items() if any(t == p or t.startswith(p + ".") for p in c["tests"])}
        ran = {t: s for t, s in hit.items() if s != "skip"}
        if not ran:
            return dict(row, etat="non mesure", detail="aucun test execute (%d sautes)" % len(hit))
        bad = sorted(t for t, s in ran.items() if s != "ok")
        if bad:
            return dict(row, etat="rouge", detail="en echec : " + ", ".join(bad)[:300])
        return dict(row, etat="vert", detail="%d tests OK%s" % (len(ran), " (%d sautes)" % (len(hit) - len(ran)) if len(hit) > len(ran) else ""))
    if k == "cmd":
        rc, out = run(c["cmd"])
        if rc in (124, 127):
            return dict(row, etat="non mesure", detail=out[:120])
        last = " ".join(out.strip().splitlines()[-1:])[:120]
        return dict(row, etat="vert" if rc == 0 else "rouge", detail="code %d : %s" % (rc, last))
    etat, detail = FUNCS[c["func"]](run)
    return dict(row, etat=etat, detail=detail)


def render(rows):
    out = ["| Critere | Intitule | Etat | Detail | Preuve |", "|---|---|---|---|---|"]
    for r in rows:
        out.append("| %s | %s | %s | %s | `%s` |" % (r["id"], r["titre"], r["etat"].upper() if r["etat"] == "rouge" else r["etat"],
                                                    r["detail"].replace("|", "/"), r["preuve"]))
    n = {e: sum(1 for r in rows if r["etat"] == e) for e in ("vert", "rouge", "non mesure")}
    out.append("")
    out.append("Bilan : vert %d, rouge %d, non mesure %d (sur %d)" % (n["vert"], n["rouge"], n["non mesure"], len(rows)))
    return "\n".join(out)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="accept.py")
    ap.add_argument("--quick", action="store_true", help="ne lance pas la suite (criteres de tests : non mesure)")
    ap.add_argument("--out", help="ecrit aussi le tableau dans ce fichier Markdown")
    a = ap.parse_args(argv)
    results = None if a.quick else run_suite()
    rows = [evaluate(c, results, run_cmd) for c in CRITERIA]
    text = render(rows)
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Acceptation super-reprompt v3 (dev/accept.py)\n\nGenere le %s.\n\n%s\n" % (time.strftime("%Y-%m-%d %H:%M"), text))
    return 0 if all(r["etat"] == "vert" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
