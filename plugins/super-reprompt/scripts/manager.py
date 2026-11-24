# -*- coding: utf-8 -*-
"""manager.py : la boucle du super-manager (lot L8, CDC §9.2). Bibliotheque standard, AUCUN reseau.

Le super-manager ne lit ni le code ni les documents : il lit des recus. Un tour de boucle :
  manager.py next  --project P --slug S [--relais relais.json]
      budget (bilan econ : arret a 150 % -> code 3, question a l'utilisateur) -> brief vault (vault.py brief)
      -> frontiere de PLAN.json -> econ.decide par tache -> briefs ecrits dans .super-reprompt/S/briefs/ -> qui lancer
  (le super-manager lance alors lui-meme : script, `relais run`, la session, ou l'outil Agent avec le modele indique)
  manager.py done  <tache> --report F [--tokens N] --project P --slug S
      remontee conforme (6 champs, <= 1 500 tokens) -> PREUVE PAR SCRIPT (la commande de la tache, jamais le recit)
      -> Vigie (guard.py drift) -> PLAN.json (done | echec) -> depense par poste (econ.ndjson) -> journal (vault.py log)
Codes : 0 ok, 1 preuve en echec, 2 refus (remontee, tache inconnue), 3 arret budget.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contracts  # noqa: E402
import econ  # noqa: E402


def _run(args, cwd, timeout=600):
    try:
        p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except OSError as e:
        return 127, type(e).__name__
    return p.returncode, p.stdout.decode("utf-8", "replace")


def journal(project, slug, kind, text):
    """One line, by script, through vault.py (journal.ndjson of the mission + the vault journal when configured)."""
    rc, out = _run([sys.executable, os.path.join(HERE, "vault.py"), "log", slug, "--kind", kind, text], project, timeout=60)
    return rc == 0


def _plan_path(a):
    return os.path.join(a.project, ".super-reprompt", a.slug, "PLAN.json")


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _save(p, plan):
    contracts.save_checked(p, plan, "plan")


def cmd_next(a):
    mdir = os.path.join(a.project, ".super-reprompt", a.slug)
    plan = _load(_plan_path(a))
    bil = econ.bilan(mdir, plan)
    for ph, b in sorted(bil.items()):
        if b["statut"] == "arret":
            journal(a.project, a.slug, "budget", "ARRET phase %s : %d / %s tokens" % (ph, b["total"], b["budget"]))
            print("ARRET budget : phase %s a %d / %s tokens (>= 150 %%) : question a l'utilisateur avant toute suite" % (ph, b["total"], b["budget"]))
            return 3
        if b["statut"] == "alerte":
            print("ALERTE budget : phase %s a %d / %s tokens (>= 80 %%)" % (ph, b["total"], b["budget"]))
    rc, vb = _run([sys.executable, os.path.join(HERE, "vault.py"), "brief", a.slug], a.project, timeout=60)
    print("brief vault : " + (" | ".join(vb.strip().splitlines()[:6]) if rc == 0 and vb.strip() else "aucun"))
    fr = econ.frontier(plan)
    if not fr:
        print("FIN : aucune tache prete (%s)" % ", ".join("%s=%s" % (t["id"], t.get("status")) for t in plan.get("tasks", [])))
        return 0
    rel = _load(a.relais) if a.relais else {}
    os.makedirs(os.path.join(mdir, "briefs"), exist_ok=True)
    try:
        for t in fr:
            d = econ.decide(t, rel)
            line = "%s %s" % (t["id"], d["level"])
            if d["level"] in ("specialiste", "relais"):
                bp = os.path.join(mdir, "briefs", t["id"] + ".md")
                with open(bp, "w", encoding="utf-8", newline="\n") as f:
                    f.write(econ.brief(t, {"slug": a.slug, "interdits": plan.get("interdits")}))
                line += " %s effort %s brief %s" % (d["model"] or "", d["effort"] or "-", os.path.relpath(bp, a.project))
            print(line + " - " + d["reason"])
        g = econ.group(fr, rel)
    except econ.EconError as e:
        print("REFUS : %s" % e)
        return 2
    print("lancer maintenant (<= %d en parallele) : %s ; en attente : %d ; sous-managers : %d"
          % (econ.MAX_PARALLEL, g["lancer"] or "rien (script / relais / session)", len(g["en_attente"]), len(g["sous_managers"])))
    return 0


def cmd_done(a):
    p = _plan_path(a)
    plan = _load(p)
    t = next((x for x in plan.get("tasks", []) if x["id"] == a.tache), None)
    if t is None:
        print("REFUS : tache inconnue %s" % a.tache)
        return 2
    with open(a.report, encoding="utf-8") as f:
        ok, miss = econ.check_report(f.read())
    if not ok:
        print("REFUS : remontee non conforme (%s) ; la tache reste %s" % (", ".join(miss), t.get("status", "todo")))
        return 2
    # the report is a claim; the task's own command is the proof
    rc, out = _run(t["preuve"], a.project) if t.get("preuve") else (1, "aucune commande de preuve")
    tail = " ".join(out.strip().splitlines()[-1:])[:120]
    verdict = "done" if rc == 0 else "echec"
    vrc, vout = _run([sys.executable, os.path.join(HERE, "guard.py"), "drift", "--project", a.project, "--slug", a.slug], a.project, timeout=120)
    vig = " ".join(vout.strip().splitlines()[:2])[:160] or "aucun ecart"
    journal(a.project, a.slug, "vigie", "%s : drift code %d : %s" % (a.tache, vrc, vig))
    t["status"] = verdict
    _save(p, plan)
    level = econ.decide(dict(t, status="todo"), {}).get("level", "session")
    econ.spend(os.path.dirname(p), t.get("phase", "P1"), level, a.tokens or 0, estimated=a.tokens is None)
    journal(a.project, a.slug, "tache", "%s %s (%s) preuve code %d : %s" % (a.tache, verdict, level, rc, tail))
    print("%s : preuve %s (code %d) ; vigie code %d : %s" % (a.tache, "OK" if rc == 0 else "ECHEC", rc, vrc, vig))
    if vrc == 4:
        print("QUESTION : la Vigie signale une deuxieme derive : question a l'utilisateur")
    return 0 if rc == 0 else 1


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="manager.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("next", "done"):
        s = sub.add_parser(name)
        if name == "done":
            s.add_argument("tache")
            s.add_argument("--report", required=True)
            s.add_argument("--tokens", type=int, help="tokens reels de l'agent (sinon depense marquee estimee)")
        else:
            s.add_argument("--relais", help="sortie de `relais plan --json`")
        s.add_argument("--project", required=True)
        s.add_argument("--slug", required=True)
    a = ap.parse_args(argv)
    a.project = os.path.abspath(a.project)
    return cmd_next(a) if a.cmd == "next" else cmd_done(a)


if __name__ == "__main__":
    sys.exit(main())
