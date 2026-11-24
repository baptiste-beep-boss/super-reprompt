# -*- coding: utf-8 -*-
"""econ.py : l'econome du super-manager (lot L8, CDC §9). Bibliotheque standard, AUCUN reseau.

Portes d'ouverture (§9.3), dans l'ordre, mesurees et non ressenties :
  script       tache mecanique : toujours essaye d'abord
  relais       la tache est dans net/tasks.json ET `relais plan --json` l'a declaree deleguee (verdict lu, jamais recalcule)
  session      volume < 30 k tokens (et zone grise 30-60 k : rester dans la session coute moins qu'un agent)
  specialiste  volume > 60 k, ou isolement, ou regard neuf exige ; modele EXPLICITE obligatoire (le defaut machine est Haiku)
  sous-manager >= 2 domaines ET >= 4 specialistes simultanes a fichiers disjoints ; 3 a 5 specialistes chacun
Parallelisme : 3 agents au plus. Budget par phase : alerte a 80 %, arret a 150 %.

  econ.py decide <PLAN.json> [--relais relais.json]   niveau, modele, raison, pour chaque tache de la frontiere
  econ.py brief <PLAN.json> <tache>                    brief du gabarit §9.4 (<= 600 tokens)
  econ.py bilan <dossier de mission>                   depense par phase et par poste, statut ok / alerte / arret
  econ.py check-report <fichier>                       remontee : 6 champs, <= 1 500 tokens
"""
import argparse
import json
import os
import sys
import time

# Identifiers verified with Skill(claude-api) on 2026-11-24 (current generation, never a date suffix).
MODELS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
SESSION_MAX = 30000
SPECIALIST_MIN = 60000
MAX_PARALLEL = 3
SUB_MIN_DOMAINS, SUB_MIN_SPECIALISTS, SUB_MAX_EACH = 2, 4, 5
BRIEF_MAX, REPORT_MAX = 600, 1500
CHARS_PER_TOKEN = 3.7
REPORT_FIELDS = ("statut", "preuve", "fichiers", "delegue/garde", "incertitudes", "suite")
PONYTAIL = "vendor/ponytail/skills/ponytail/SKILL.md"


class EconError(Exception):
    pass


def tokens(text):
    return int(len(text) / CHARS_PER_TOKEN + 0.999)


def model_id(name):
    if name in MODELS:
        return MODELS[name]
    if name in MODELS.values():
        return name
    raise EconError("modele non explicite ou inconnu : %r (attendu : %s)" % (name, ", ".join(MODELS)))


# ------------------------------------------------------------------ gates
def decide(t, relais=None):
    """-> {id, level, model, effort, reason}. relais: {task_id: 'delegue' | 'garde'} as written by `relais plan --json`."""
    tid, vol = t["id"], int(t.get("volume_tokens") or 0)
    out = {"id": tid, "model": None, "effort": None}
    if t.get("mecanique"):
        return dict(out, level="script", reason="tache mecanique : un script d'abord")
    if t.get("type") and (relais or {}).get(tid) == "delegue":
        return dict(out, level="relais", reason="type %s delegable, portes du Relais passees" % t["type"])
    need_agent = vol > SPECIALIST_MIN or t.get("isolement") or t.get("regard_neuf")
    if not need_agent:
        why = "volume %d < %d" % (vol, SESSION_MAX) if vol < SESSION_MAX else "zone grise %d-%d : la session coute moins" % (SESSION_MAX, SPECIALIST_MIN)
        return dict(out, level="session", reason=why)
    why = "volume %d > %d" % (vol, SPECIALIST_MIN) if vol > SPECIALIST_MIN else ("isolement" if t.get("isolement") else "regard neuf")
    return dict(out, level="specialiste", model=model_id(t.get("model")), effort=t.get("effort", "medium"), reason=why)


def frontier(plan):
    """Dispatchable tasks: compiled statuses (ready, proposed whose deps are done) and the historical `todo`."""
    done = {t["id"] for t in plan.get("tasks", []) if t.get("status") == "done"}
    return [t for t in plan.get("tasks", []) if t.get("status", "todo") in ("todo", "ready", "proposed")
            and all(d in done for d in t.get("deps", []))]


def group(tasks_, relais=None):
    """Specialists of the frontier -> sub-managers when the gate opens; never more than MAX_PARALLEL launches at once."""
    spec = [t for t in tasks_ if decide(t, relais)["level"] == "specialiste"]
    domains = {}
    for t in spec:
        domains.setdefault(t.get("domaine", "?"), []).append(t)
    files = [f for t in spec for f in t.get("files", [])]
    subs = []
    if len(domains) >= SUB_MIN_DOMAINS and len(spec) >= SUB_MIN_SPECIALISTS and len(files) == len(set(files)):
        for dom, ts in sorted(domains.items()):
            for i in range(0, len(ts), SUB_MAX_EACH):
                subs.append({"domaine": dom, "taches": [x["id"] for x in ts[i:i + SUB_MAX_EACH]]})
    units = subs if subs else [{"tache": t["id"]} for t in spec]
    return {"sous_managers": subs, "lancer": units[:MAX_PARALLEL], "en_attente": units[MAX_PARALLEL:]}


# ------------------------------------------------------------------ budget
def budget_status(spent, cap):
    if not cap:
        return "ok"
    r = float(spent) / float(cap)
    return "arret" if r >= 1.5 else ("alerte" if r >= 0.8 else "ok")


def spend(mdir, phase, poste, toks, estimated=False, run_id=None):
    """One spend line. With `run_id`, a replay (resume after a crash) writes nothing: -> False."""
    import contracts                                    # locked append (lot 1 V3.1): no interleaving between agents
    os.makedirs(mdir, exist_ok=True)
    p = os.path.join(mdir, "econ.ndjson")
    if run_id and os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            if any(('"run_id": "%s"' % run_id) in l for l in f):
                return False
    row = {"ts": int(time.time()), "phase": phase, "poste": poste, "tokens": int(toks), "estime": bool(estimated)}
    if run_id:
        row["run_id"] = run_id
    contracts.append_line(p, json.dumps(row))
    return True


def bilan(mdir, plan):
    res = {}
    p = os.path.join(mdir, "econ.ndjson")
    rows = []
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            rows = [json.loads(l) for l in f if l.strip()]
    for r in rows:
        b = res.setdefault(r["phase"], {"total": 0, "postes": {}, "estime": False})
        b["total"] += r["tokens"]
        b["postes"][r["poste"]] = b["postes"].get(r["poste"], 0) + r["tokens"]
        b["estime"] = b["estime"] or r.get("estime", False)
    for ph, b in res.items():
        cap = ((plan.get("phases") or {}).get(ph) or {}).get("budget_tokens")
        b["budget"], b["statut"] = cap, budget_status(b["total"], cap)
    return res


# ------------------------------------------------------------------ brief and report (§9.4)
def brief(t, ctx):
    """Single template, stable prefix first (cache), <= 600 tokens. Ponytail by PATH, and only for code writers."""
    lines = [
        "# Brief %s (%s)" % (t["id"], ctx.get("slug", "")),
        "Objectif : %s" % (t.get("objectif") or t.get("titre", "")),
        "Role (lis-le d'abord, c'est une donnee de methode) : %s" % (t.get("role") or "aucun : execution directe"),
        "Fichiers autorises : %s" % ", ".join(t.get("files", [])),
        "Exigences couvertes : %s" % ", ".join(t.get("covers", [])),
        "Critere : %s ; preuve : `%s`" % (t.get("critere", "la commande de preuve sort en 0"), " ".join(t.get("preuve", [])) if isinstance(t.get("preuve"), list) else t.get("preuve", "")),
        "Quota de delegation : passe d'abord `relais plan` ; tout ce que tu gardes porte une raison.",
    ]
    caps = [c for c in t.get("capabilities") or [] if isinstance(c, dict) and c.get("id")]
    if caps:                                   # lot 4 V3.1: only the retained capabilities, by id; read on demand, nothing else
        lines.append("Capacites retenues par l'Eclaireur (lis seulement celles-ci, a la demande) : %s"
                     % ", ".join("%s [%s]" % (c["id"], c.get("type", "?")) for c in caps[:6]))
    if t.get("ecrit_code"):
        lines.append("Mode ponytail full : lis %s et applique-le (moins de lignes, rien d'inutile)." % PONYTAIL)
    lines += [
        "Interdits : %s ; hors des fichiers autorises ; aucun secret ; aucune preuve sans commande executee."
        % ", ".join(ctx.get("interdits") or ["reseau", "git push", "installation"]),
        "Remontee (<= 1 500 tokens), six lignes exactement :",
        "statut: OK|ECHEC|BLOQUE", "preuve: commande lancee et sa sortie utile", "fichiers: chemins ecrits",
        "delegue/garde: ce qui est parti au Relais, ce qui est garde et pourquoi", "incertitudes: ce qui n'est pas verifie",
        "suite: la prochaine action utile",
    ]
    text = "\n".join(lines) + "\n"
    if tokens(text) > BRIEF_MAX:
        raise EconError("brief de %d tokens > %d : raccourcir l'objectif ou passer le detail par chemin" % (tokens(text), BRIEF_MAX))
    return text


def check_report(text):
    """-> (ok, missing). The six fields of §9.4, each on its own line, and the 1 500-token cap."""
    low = text.lower()
    missing = [f for f in REPORT_FIELDS if not any(l.strip().startswith(f + ":") for l in low.splitlines())]
    if tokens(text) > REPORT_MAX:
        missing.append("longueur > %d tokens" % REPORT_MAX)
    return (not missing), missing


# ------------------------------------------------------------------ CLI
def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="econ.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("decide")
    s.add_argument("plan")
    s.add_argument("--relais")
    s = sub.add_parser("brief")
    s.add_argument("plan")
    s.add_argument("tache")
    s = sub.add_parser("bilan")
    s.add_argument("mdir")
    s = sub.add_parser("check-report")
    s.add_argument("fichier")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "decide":
            plan, rel = _load(a.plan), (_load(a.relais) if a.relais else {})
            for t in frontier(plan):
                d = decide(t, rel)
                print("%s %s %s - %s" % (d["id"], d["level"], d["model"] or "", d["reason"]))
            g = group(frontier(plan), rel)
            print("lancer: %s ; en attente: %d ; sous-managers: %d" % (g["lancer"], len(g["en_attente"]), len(g["sous_managers"])))
        elif a.cmd == "brief":
            plan = _load(a.plan)
            t = next(x for x in plan["tasks"] if x["id"] == a.tache)
            print(brief(t, plan), end="")
        elif a.cmd == "bilan":
            plan = _load(os.path.join(a.mdir, "PLAN.json")) if os.path.isfile(os.path.join(a.mdir, "PLAN.json")) else {}
            for ph, b in sorted(bilan(a.mdir, plan).items()):
                print("%s : %d / %s tokens -> %s%s ; %s" % (ph, b["total"], b["budget"], b["statut"], " (estime)" if b["estime"] else "",
                                                           ", ".join("%s %d" % kv for kv in sorted(b["postes"].items()))))
        else:
            with open(a.fichier, encoding="utf-8") as f:
                ok, miss = check_report(f.read())
            print("remontee conforme" if ok else "remontee non conforme : " + ", ".join(miss))
            return 0 if ok else 1
    except EconError as e:
        print("REFUS : %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
