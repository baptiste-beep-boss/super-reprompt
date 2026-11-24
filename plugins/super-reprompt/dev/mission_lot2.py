# -*- coding: utf-8 -*-
"""Mission reelle du lot 2 V3.1 : cadrage -> ordre -> `mission.py ready` -> PLAN.json + SCELLE.json lies par empreinte
-> manager next / done sur le plan compile -> derive detectee si le plan est restructure. Sous-processus reels, projet
jetable (espaces, accents). Usage : py -3 dev/mission_lot2.py  -> 0 si toutes les verifications passent."""
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

OK = []


def run(args, cwd, env=None):
    p = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True, env=env, timeout=300)
    tail = (p.stdout + p.stderr).strip().splitlines()
    print("$ %s -> code %d" % (" ".join(os.path.basename(a) if a.endswith(".py") else a for a in args[:3]), p.returncode))
    for ln in tail[-4:]:
        print("    " + ln[:200])
    return p


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot2 é ")
    proj = os.path.join(tmp, "projet démo")
    md = os.path.join(proj, ".super-reprompt", "page-remboursement")
    os.makedirs(os.path.join(proj, "site"))
    env = dict(os.environ, SR_VAULT_PATH=os.path.join(tmp, "vault"), SR_VAULT_DB=os.path.join(tmp, "idx.sqlite"), PYTHONUTF8="1")
    os.makedirs(env["SR_VAULT_PATH"])
    try:
        subprocess.run(["git", "init", "-q", proj], check=True)
        st = C.read_json(os.path.join(ROOT, "schemas", "examples", "valid", "state-minimal.json"))
        st.update(slug="page-remboursement", status="framing", seal={"perimeter": ["site"], "color": "orange"},
                  verification={"commands": [{"id": "V1", "cmd": '"%s" -c ' % sys.executable + "\"import os,sys;sys.exit(0 if os.path.isfile('site/index.html') else 1)\"",
                                              "state": "pending", "reason": None, "plan_b": "ouvrir la page a la main"}],
                                "criteria": [{"id": "C1", "text": "site/index.html existe", "source": "test", "proof": "V1", "passes": False, "unsourced": False}]},
                  tasks=[{"id": "T1", "title": "Ecrire la page", "covers": ["R1"], "files": ["site/*"], "mecanique": True,
                          "preuve": "V1"},
                         {"id": "T2", "title": "Verifier", "deps": ["T1"], "covers": ["C1"], "mecanique": True, "preuve": "V1"}])
        C.atomic_write_json(os.path.join(md, "STATE.json"), st)
        C.atomic_write_text(os.path.join(md, "ORDRE.md"), "".join("## %d Section\ntexte\n" % i for i in range(1, 12)))

        r = run([os.path.join(S, "validate_order.py"), "page-remboursement", "--project", proj], proj, env)
        check("ordre valide (validate_order)", r.returncode == 0)
        r = run([os.path.join(S, "mission.py"), "ready", "page-remboursement", "--project", proj], proj, env)
        check("mission.py ready : compile + scelle sans etape manuelle", r.returncode == 0)
        plan = C.read_json(os.path.join(md, "PLAN.json"))
        seal = C.read_json(os.path.join(md, "SCELLE.json"))
        check("PLAN.json strict valide", not C.validate("plan", plan, strict=True))
        check("lien ordre -> plan -> scelle par empreintes",
              plan["source_order_hash"] == seal["order_sha256"] and seal["plan_sha256"] == C.plan_structure_sha(plan))
        check("preuve V1 resolue en commande", sys.executable in plan["tasks"][0]["preuve"])
        r = run([os.path.join(S, "guard.py"), "drift", "--project", proj, "--slug", "page-remboursement"], proj, env)
        check("Vigie : aucune derive sur le plan compile", "PLAN_MODIFIE" not in r.stdout)

        r = run([os.path.join(S, "manager.py"), "next", "--project", proj, "--slug", "page-remboursement"], proj, env)
        check("manager next charge le plan compile (T1 prete, T2 en attente)", r.returncode == 0 and "T1 script" in r.stdout and "T2" not in r.stdout.split("lancer")[0])
        C.atomic_write_text(os.path.join(proj, "site", "index.html"), "<h1>Remboursement</h1>\n")
        rep = os.path.join(tmp, "r.txt")
        C.atomic_write_text(rep, "statut: OK\npreuve: V1\nfichiers: site/index.html\ndelegue/garde: garde\nincertitudes: aucune\nsuite: T2\n")
        r = run([os.path.join(S, "manager.py"), "done", "T1", "--report", rep, "--tokens", "800", "--project", proj, "--slug", "page-remboursement"], proj, env)
        check("manager done T1 : preuve compilee executee (code 0)", r.returncode == 0 and "preuve OK" in r.stdout)
        r = run([os.path.join(S, "guard.py"), "drift", "--project", proj, "--slug", "page-remboursement"], proj, env)
        check("progression n'est pas une derive (statut change, empreinte stable)", "PLAN_MODIFIE" not in r.stdout)

        plan = C.read_json(os.path.join(md, "PLAN.json"))
        plan["tasks"].append({"id": "T9", "title": "ajout en douce", "status": "ready", "deps": [], "covers": [], "files": ["*"],
                              "acceptance_criteria": ["x"], "preuve": "exit 0"})
        C.atomic_write_json(os.path.join(md, "PLAN.json"), plan)
        r = run([os.path.join(S, "guard.py"), "drift", "--project", proj, "--slug", "page-remboursement"], proj, env)
        check("plan restructure hors avenant : PLAN_MODIFIE et code non nul", "PLAN_MODIFIE" in r.stdout and r.returncode != 0)
        r = run([os.path.join(S, "compile_plan.py"), "page-remboursement", "--project", proj], proj, env)
        check("recompiler apres demarrage sans avenant : refus", r.returncode == 1 and "avenant" in r.stdout)
        types = [e["event_type"] for e in C.read_events(md)]
        print("evenements :", ", ".join(types))
        check("plan.compiled et seal.written journalises", "plan.compiled" in types and "seal.written" in types)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
