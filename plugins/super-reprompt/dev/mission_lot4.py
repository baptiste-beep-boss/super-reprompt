# -*- coding: utf-8 -*-
"""Mission reelle du lot 4 V3.1 : cadrage avec 3 taches de natures differentes -> mission.py ready -> plan de capacites
par tache (tous types) dans PLAN.json -> eclaireur.py capacites (raisons) -> manager next : le brief du specialiste porte
les capacites retenues et rien d'autre. Mesure du contexte charge vs le catalogue complet.
Usage : py -3 dev/mission_lot4.py -> 0 si tout passe."""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "scripts")
sys.path.insert(0, S)
import catalog as CAT  # noqa: E402
import contracts as C  # noqa: E402

OK = []


def run(args, cwd, env):
    p = subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True, env=env, timeout=300)
    print("$ %s -> code %d" % (" ".join(os.path.basename(a) if a.endswith(".py") else a for a in args[:3]), p.returncode))
    for ln in (p.stdout + p.stderr).strip().splitlines()[:14]:
        print("    " + ln[:170])
    return p


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot4 é ")
    proj = os.path.join(tmp, "projet démo")
    slug = "durcir-api"
    md = os.path.join(proj, ".super-reprompt", slug)
    os.makedirs(os.path.join(proj, "src"))
    env = dict(os.environ, SR_VAULT_PATH="", CLAUDE_PLUGIN_OPTION_VAULT_PATH="", PYTHONUTF8="1")
    try:
        subprocess.run(["git", "init", "-q", proj], check=True)
        st = C.read_json(os.path.join(ROOT, "schemas", "examples", "valid", "state-minimal.json"))
        st.update(slug=slug, status="framing", seal={"perimeter": ["src"]},
                  requirements=[{"id": "R1", "text": "revue securite", "kind": "unguessable"}, {"id": "R2", "text": "accessibilite", "kind": "guessable"},
                                {"id": "R3", "text": "sante serveur mcp", "kind": "guessable"}],
                  tasks=[{"id": "T1", "title": "Revue securite de l'API", "covers": ["R1"], "files": ["src/api.py"], "volume_tokens": 90000,
                          "model": "sonnet", "crochets": {"domaine": "security", "acte": "review", "langage": "python"}, "preuve": "V1"},
                         {"id": "T2", "title": "Audit accessibilite", "covers": ["R2"], "files": ["src/ui.tsx"], "volume_tokens": 90000,
                          "model": "haiku", "crochets": {"domaine": "accessibility", "acte": "audit", "livrable": "ui"}, "preuve": "V1"},
                         {"id": "T3", "title": "Surveiller le serveur MCP", "deps": ["T1"], "covers": ["R3", "C1"], "mecanique": True,
                          "crochets": {"domaine": "mcp", "livrable": "server"}, "preuve": "V1"}])
        C.atomic_write_json(os.path.join(md, "STATE.json"), st)
        C.atomic_write_text(os.path.join(md, "ORDRE.md"), "".join("## %d Section\ntexte\n" % i for i in range(1, 12)))

        r = run([os.path.join(S, "mission.py"), "ready", slug, "--project", proj], proj, env)
        check("ready : plan compile avec plan de capacites", r.returncode == 0)
        plan = C.read_json(os.path.join(md, "PLAN.json"))
        caps = {t["id"]: t.get("capabilities", []) for t in plan["tasks"]}
        for tid, cs in caps.items():
            print("  %s : %s" % (tid, ", ".join("%s[%s,%d]" % (c["id"], c["type"], c["cout_tokens"]) for c in cs)))
        types = {c["type"] for cs in caps.values() for c in cs}
        check("A13 : types non-skill selectionnes (%s)" % ", ".join(sorted(types)), types - {"skill"} and "skill" in types)
        check("T3 (serveur MCP) recoit un hook", any(c["type"] == "hook" for c in caps["T3"]))
        cb = plan["context_budget"]
        els = CAT.load_catalog()
        full = sum(e.get("coût_tokens") or 0 for e in els if e["type"] in ("skill", "agent", "commande", "hook", "règle", "script", "schéma"))
        print("  contexte par tache : max %d / budget %d tokens (mesure) ; catalogue complet : %d tokens (estimation du catalogue) ; "
              "ratio %.2f %%" % (cb["tokens"], cb["budget"], full, 100.0 * cb["tokens"] / full))
        check("A14 : contexte charge limite et mesure (<= budget, < 1 %% du catalogue)", cb["tokens"] <= cb["budget"] and cb["tokens"] < full / 100)
        r = run([os.path.join(S, "eclaireur.py"), "capacites", os.path.join(md, "PLAN.json"), "--budget", "3000"], proj, env)
        check("eclaireur capacites explique retenues (+) et ecarts (-)", r.returncode == 0 and "   + " in r.stdout and "   - " in r.stdout)
        r = run([os.path.join(S, "manager.py"), "next", "--project", proj, "--slug", slug], proj, env)
        with open(os.path.join(md, "briefs", "T1.md"), encoding="utf-8") as f:
            b = f.read()
        check("brief du specialiste T1 : porte exactement ses capacites", all(c["id"] in b for c in caps["T1"]) and
              not any(c["id"] in b for c in caps["T2"] if c["id"] not in [x["id"] for x in caps["T1"]]))
        check("plan scelle reste coherent (aucune derive)", "PLAN_MODIFIE" not in run([os.path.join(S, "guard.py"), "drift", "--project", proj, "--slug", slug], proj, env).stdout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
