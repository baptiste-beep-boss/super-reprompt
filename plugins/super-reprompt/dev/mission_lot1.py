# -*- coding: utf-8 -*-
"""Mission reelle du lot 1 V3.1 : traverse les vrais scripts (guard seal, pare-feu, vault log, manager done, contracts)
dans un projet jetable dont le chemin contient espaces et accents. Rien n'est simule : chaque etape est un sous-processus.
Usage : py -3 dev/mission_lot1.py   -> code 0 si toutes les verifications passent."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")
sys.path.insert(0, S)
import contracts as C  # noqa: E402

EX_STATE = os.path.join(ROOT, "schemas", "examples", "valid", "state-minimal.json")


def valid_state(slug):
    st = C.read_json(EX_STATE)
    st["slug"] = slug
    return st

OK = []


def run(args, cwd, stdin=None, env=None):
    p = subprocess.run([sys.executable] + args, cwd=cwd, input=stdin, capture_output=True, text=True, env=env, timeout=300)
    print("$ %s\n  -> code %d %s" % (" ".join(os.path.basename(a) if a.endswith(".py") else a for a in args), p.returncode,
                                     (p.stdout + p.stderr).strip().splitlines()[-1:] or ""))
    return p


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot1 é ")
    proj = os.path.join(tmp, "projet démo")
    mdir = os.path.join(proj, ".super-reprompt", "demo-mission")
    os.makedirs(os.path.join(proj, "site"))
    env = dict(os.environ, SR_VAULT_PATH=os.path.join(tmp, "vault"), SR_VAULT_DB=os.path.join(tmp, "idx.sqlite"), PYTHONUTF8="1")
    os.makedirs(env["SR_VAULT_PATH"])
    try:
        subprocess.run(["git", "init", "-q", proj], check=True)
        C.atomic_write_json(os.path.join(mdir, "STATE.json"), valid_state("demo-mission"))
        C.atomic_write_text(os.path.join(mdir, "ORDRE.md"), "# Ordre\nR1 : la page montre la politique.\n")
        legacy = ['{"ts":"2026-11-20T10:00:00Z","slug":"demo-mission","kind":"decision","text":"ancien journal"}',
                  '{"t":"2026-11-20T10:01:00","ev":"deny","rule":"F07","msg":"ancien refus"}']
        C.atomic_write_text(os.path.join(mdir, "journal.ndjson"), "\n".join(legacy) + "\n")

        r = run([os.path.join(S, "guard.py"), "seal", "--project", proj, "--slug", "demo-mission", "--perimeter", "site", "--budget", "300000"], proj)
        check("guard seal ecrit SCELLE.json (ecriture atomique unique)", r.returncode == 0)
        for kind, f in (("seal", "SCELLE.json"), ("state", "STATE.json")):
            r = run([os.path.join(S, "contracts.py"), "validate", kind, os.path.join(mdir, f)], proj)
            check("contrat %s valide" % kind, r.returncode == 0)

        hook_in = json.dumps({"tool_name": "Write", "tool_input": {"file_path": os.path.join(proj, "hors.txt"), "content": "x"}, "cwd": proj})
        # the firewall always allows the declared temp dir; this throwaway project lives in it, so the hook gets its own
        henv = dict(env, TEMP=os.path.join(tmp, "autre-temp"), TMP=os.path.join(tmp, "autre-temp"), TMPDIR=os.path.join(tmp, "autre-temp"))
        r = run([os.path.join(S, "guard.py")], proj, stdin=hook_in, env=henv)
        check("pare-feu refuse l'ecriture hors perimetre (code 2)", r.returncode == 2)
        r = run([os.path.join(S, "vault.py"), "log", "demo-mission", "--kind", "decision", "contrats", "du", "lot", "1"], proj, env=env)
        check("vault.py log ecrit dans le journal unique", r.returncode == 0)

        plan = {"schema": 2, "slug": "demo-mission", "source_order_hash": C.read_json(os.path.join(mdir, "SCELLE.json"))["order_sha256"],
                "tasks": [{"id": "T1", "title": "page", "status": "todo", "deps": [], "covers": ["R1", "C1"], "files": ["site/*"],
                           "acceptance_criteria": ["la commande sort 0"], "preuve": [sys.executable, "-c", "print('ok')"], "mecanique": True}]}
        C.save_checked(os.path.join(mdir, "PLAN.json"), plan, "plan")
        rep = os.path.join(tmp, "rapport.txt")
        C.atomic_write_text(rep, "statut: OK\npreuve: commande lancee\nfichiers: site/index.html\ndelegue/garde: garde\nincertitudes: aucune\nsuite: rien\n")
        r = run([os.path.join(S, "manager.py"), "done", "T1", "--report", rep, "--tokens", "1200", "--project", proj, "--slug", "demo-mission"], proj, env=env)
        check("manager done : preuve par script, PLAN reecrit par save_checked", r.returncode == 0 and C.read_json(os.path.join(mdir, "PLAN.json"))["tasks"][0]["status"] == "done")

        r = run([os.path.join(S, "contracts.py"), "migrate", mdir], proj)
        m1 = json.loads(r.stdout.strip().splitlines()[-1])
        r = run([os.path.join(S, "contracts.py"), "migrate", mdir], proj)
        m2 = json.loads(r.stdout.strip().splitlines()[-1])
        check("migration de l'ancien journal : 2 lignes, rejeu sans doublon", m1["migrated"] == 2 and m2["migrated"] == 0)

        evs = C.read_events(mdir)
        types = [e["event_type"] for e in evs]
        print("evenements :", ", ".join(types))
        check("tous les evenements valident le contrat event v1", evs and all(not C.validate("event", e) for e in evs))
        check("journal unique alimente par pare-feu + vault + manager + migration",
              {"guard.deny", "log.decision", "log.vigie", "log.tache"} <= set(types) and sum(1 for e in evs if e["payload"].get("legacy")) == 2)
        check("event_id uniques", len({e["event_id"] for e in evs}) == len(evs))
        check("aucun temporaire residuel dans la mission", not [f for f in os.listdir(mdir) if f.endswith(".tmp") or f.endswith(".lock")])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
