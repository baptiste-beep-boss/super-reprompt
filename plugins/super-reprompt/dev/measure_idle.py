# -*- coding: utf-8 -*-
"""Critere A4 : cout AU REPOS du plugin <= 1 500 tokens (lot L9).

Au repos, une session ne voit de ce plugin que le nom et la description du skill et de chaque agent (les corps ne se chargent qu'a
l'appel) ; les hooks sont silencieux hors mission (I7). On compte donc (nom + description) / 3,7 pour le skill et chaque agent, et on
MESURE la sortie des hooks sur une invite triviale dans un dossier vide.

Run:  py -3 dev/measure_idle.py [--check] [--json]       --check : code 1 si > 1 500.
Limite : c'est un compte de caracteres / 3,7 (convention du depot), pas la mesure `/context` de l'application, qui reste a faire en
session reelle (avant / apres l'activation du plugin).
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIV = 3.7
LIMIT = 1500


def front(path):
    with open(path, encoding="utf-8") as fh:
        t = fh.read()
    m = re.match(r"---\r?\n(.*?)\r?\n---", t, re.S)
    f = m.group(1) if m else ""
    n = re.search(r"(?m)^name:\s*(.+)$", f)
    d = re.search(r"(?ms)^description:\s*(.+?)(?=^[A-Za-z_-]+:|\Z)", f)
    return (n.group(1).strip() if n else os.path.basename(path)), (d.group(1).strip() if d else "")


def hooks_at_rest(root):
    """Tokens ecrits sur stdout par les hooks d'invite, de session et de fin pour une invite triviale, hors mission."""
    total = 0
    with tempfile.TemporaryDirectory() as proj:
        for script, event in (("hook_suggest.py", "UserPromptSubmit"), ("hook_compact.py", "SessionStart"), ("hook_stop.py", "Stop")):
            p = os.path.join(root, "scripts", script)
            if not os.path.isfile(p):
                continue
            payload = json.dumps({"session_id": "idle", "cwd": proj, "hook_event_name": event, "prompt": "ok merci", "source": "resume", "stop_hook_active": False})
            r = subprocess.run([sys.executable, p], input=payload.encode("utf-8"), capture_output=True, timeout=30,
                               env=dict(os.environ, SUPER_REPROMPT_HOME=os.path.join(proj, "h")))
            total += len(r.stdout)
    return int(round(total / DIV))


def idle(root=ROOT, with_hooks=True):
    items = []
    paths = [os.path.join(root, "skills", d, "SKILL.md") for d in sorted(os.listdir(os.path.join(root, "skills")))] if os.path.isdir(os.path.join(root, "skills")) else []
    ad = os.path.join(root, "agents")
    if os.path.isdir(ad):
        paths += [os.path.join(ad, f) for f in sorted(os.listdir(ad)) if f.endswith(".md")]
    for p in paths:
        if not os.path.isfile(p):
            continue
        n, d = front(p)
        items.append({"name": n, "kind": "skill" if p.endswith("SKILL.md") else "agent", "tokens": int(round((len(n) + len(d) + 4) / DIV))})
    hooks = hooks_at_rest(root) if with_hooks else 0
    return {"items": items, "hooks_at_rest_tokens": hooks, "total": sum(i["tokens"] for i in items) + hooks, "limit": LIMIT}


def main(argv):
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    r = idle()
    if "--json" in argv:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        for i in sorted(r["items"], key=lambda x: -x["tokens"]):
            print("  %-22s %-6s %5d tokens" % (i["name"], i["kind"], i["tokens"]))
        print("  hooks au repos        : %d tokens" % r["hooks_at_rest_tokens"])
        print("A4 cout au repos du plugin : %d tokens (plafond %d) — %s" % (r["total"], r["limit"], "OK" if r["total"] <= r["limit"] else "DEPASSE"))
    return 0 if r["total"] <= r["limit"] or "--check" not in argv else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
