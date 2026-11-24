# -*- coding: utf-8 -*-
"""compile_plan.py : P3 du cycle V3.1 (lot 2). ORDRE.md + STATE.json valides -> PLAN.json executable.
Bibliotheque standard, AUCUN reseau, AUCUN appel de modele : le decoupage semantique est fait au cadrage (STATE.tasks,
redige par le super-manager en P4) ; ce script ne fait que le rendre executable et verifiable.

  - Taches : STATE.tasks si present, sinon une tache par exigence (T-<R>) + une tache de verification (T-VERIF) qui
    depend de toutes les autres et couvre tous les criteres. IDs stables : recompiler donne les memes IDs.
  - Chaque tache recoit statut (ready sans dependance, proposed sinon), criteres de sortie, commande de preuve
    (un id V<n> est resolu vers sa commande), et `source_order_hash` = SHA-256 de ORDRE.md.
  - Validation stricte (contracts.validate plan strict) + couverture : toute exigence et tout critere couverts.
  - Recompiler : meme structure -> rien ne change (statuts conserves) ; structure differente alors qu'une tache a
    demarre -> refus (un avenant signe est requis) ; avant tout demarrage -> recompile.
  - `--seal` : appelle `guard.py seal` (options lues dans STATE.seal) ; le scelle porte alors `plan_sha256`.

CLI : compile_plan.py <slug> [--project P] [--seal]   -> 0 ok, 1 refus (erreurs nommees)
Appele automatiquement par `mission.py ready` (P7 -> P2/P3 sans etape manuelle).
"""
import argparse
import hashlib
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contracts as C  # noqa: E402

STRUCT_KEYS = ("title", "crochets", "deps", "covers", "files", "acceptance_criteria", "preuve", "phase", "model", "effort",
               "volume_tokens", "type", "mecanique", "isolement", "regard_neuf", "domaine", "privacy_class", "estimated_duration")
STARTED = ("running", "review", "done", "failed", "blocked")


def _mdir(project, slug):
    return os.path.join(os.path.abspath(project), ".super-reprompt", slug)


def _sha_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _commands(state):
    return {str(c.get("id")): str(c.get("cmd")) for c in (state.get("verification") or {}).get("commands", [])
            if isinstance(c, dict) and c.get("cmd")}


def _resolve_proof(v, cmds, errs, tid):
    if isinstance(v, list) and v:
        return v, None
    if isinstance(v, str) and v.strip():
        if v in cmds:
            return cmds[v], "%s : %s" % (v, cmds[v])
        return v, None
    errs.append("%s : aucune commande de preuve (preuve absente et aucune commande V<n> dans STATE.verification)" % tid)
    return None, None


def _capabilities(tasks, extra):
    """P4 (lot 4 V3.1): one capability plan per task, all types, from the universal Scout. Deterministic (catalogue on
    disk, no network): recompiling gives the same plan. The per-task context budget is explicit and measured."""
    import catalog
    import eclaireur
    els = catalog.load_catalog()
    worst = total = 0
    for t in tasks:
        r = eclaireur.capacites(t, els)
        t["capabilities"] = [{"id": x["id"], "type": x["type"], "cout_tokens": x["cout_tokens"], "cout_source": x["cout_source"]}
                             for x in r["retenues"]]
        worst, total = max(worst, r["contexte_tokens"]), total + r["contexte_tokens"]
    extra["context_budget"] = {"tokens": worst, "budget": eclaireur.BUDGET_CONTEXTE, "total": total,
                               "unite": "tokens de capacites chargees par tache (max sur les taches)", "source": "mesure (taille des fichiers)"}


def build(state, order_sha):
    errs = []
    cmds = _commands(state)
    reqs = [str(r.get("id")) for r in state.get("requirements", []) if isinstance(r, dict) and r.get("id")]
    crits = [c for c in (state.get("verification") or {}).get("criteria", []) if isinstance(c, dict) and c.get("id")]
    all_cmds = " && ".join(cmds[k] for k in sorted(cmds)) if cmds else None
    raw = state.get("tasks")
    tasks = []
    if raw is not None:
        if not isinstance(raw, list) or not raw:
            errs.append("STATE.tasks doit etre une liste non vide (ou absent pour le decoupage par exigence)")
            raw = []
        for i, t in enumerate(raw):
            if not isinstance(t, dict) or not isinstance(t.get("id"), str):
                errs.append("STATE.tasks[%d] : objet avec un id attendu" % i)
                continue
            out = {"id": t["id"], "title": str(t.get("title") or t["id"]), "deps": list(t.get("deps") or []),
                   "covers": list(t.get("covers") or []), "files": list(t.get("files") or [])}
            proof, crit = _resolve_proof(t.get("preuve", all_cmds), cmds, errs, t["id"])
            out["preuve"] = proof
            ac = list(t.get("acceptance_criteria") or [])
            if not ac and crit:
                ac = [crit]
            if not ac and proof:
                ac = ["la commande de preuve sort avec le code 0"]
            out["acceptance_criteria"] = ac
            for k in STRUCT_KEYS:
                if k in t and k not in out:
                    out[k] = t[k]
            tasks.append(out)
    else:
        for r in reqs:
            proof, crit = _resolve_proof(all_cmds, cmds, errs, "T-" + r)
            tasks.append({"id": "T-" + r, "title": next((str(x.get("text")) for x in state["requirements"] if x.get("id") == r), r)[:120],
                          "deps": [], "covers": [r], "files": [], "preuve": proof,
                          "acceptance_criteria": ["%s satisfaite ; la commande de preuve sort avec le code 0" % r]})
        if crits:
            proof, _ = _resolve_proof(all_cmds, cmds, errs, "T-VERIF")
            tasks.append({"id": "T-VERIF", "title": "Verification finale des criteres d'acceptation",
                          "deps": [t["id"] for t in tasks], "covers": [str(c["id"]) for c in crits], "files": [],
                          "preuve": proof, "acceptance_criteria": ["%s : %s" % (c["id"], c.get("text", "")) for c in crits]})
    for t in tasks:
        t["status"] = "ready" if not t["deps"] else "proposed"
        t["attempt"] = 1
    _capabilities(tasks, plan_extra := {})
    covered = {c for t in tasks for c in t.get("covers", [])}
    for rid in reqs + [str(c["id"]) for c in crits]:
        if rid not in covered:
            errs.append("%s couvert par aucune tache" % rid)
    plan = {"schema": C.SCHEMA_VERSIONS["plan"], "slug": state.get("slug"), "source_order_hash": order_sha,
            "compiled_at": C.now_utc(), "tasks": tasks}
    plan.update(plan_extra)
    if isinstance(state.get("phases"), dict):
        plan["phases"] = state["phases"]
    if isinstance(state.get("interdits"), list):
        plan["interdits"] = state["interdits"]
    errs += C.validate("plan", plan, strict=True)
    return plan, errs


def compile_plan(project, slug):
    """-> (plan, report). Raises ContractError (nothing written) when the order cannot become a valid plan."""
    md = _mdir(project, slug)
    order = os.path.join(md, "ORDRE.md")
    if not os.path.isfile(order):
        raise C.ContractError("ORDRE.md absent : rien a compiler (%s)" % order)
    state = C.read_json(os.path.join(md, "STATE.json"))
    plan, errs = build(state, _sha_file(order))
    if errs:
        raise C.ContractError("compilation refusee, %d probleme(s) : %s" % (len(errs), " ; ".join(errs)))
    p = os.path.join(md, "PLAN.json")
    old = C.read_json(p, default=None)
    if old is not None:
        same = C.plan_structure_sha(old) == C.plan_structure_sha(plan) and old.get("source_order_hash") == plan["source_order_hash"]
        if same:
            return old, {"action": "inchange", "tasks": len(old.get("tasks", []))}
        started = [t["id"] for t in old.get("tasks", []) if C.normalize_status(t.get("status")) in STARTED]
        if started:
            raise C.ContractError("replanification refusee : %s deja demarree(s) ; un avenant signe par l'utilisateur est requis "
                                  "(guard.py avenant), puis recompiler apres l'avoir integre" % ", ".join(started))
    C.save_checked(p, plan, "plan", strict=True)
    C.emit(md, "plan.compiled", "core", {"tasks": len(plan["tasks"]), "source_order_hash": plan["source_order_hash"],
                                         "plan_sha256": C.plan_structure_sha(plan)}, mission_id=slug,
           dedup_key="compiled|" + C.plan_structure_sha(plan) + "|" + plan["source_order_hash"])
    return plan, {"action": "compile" if old is None else "recompile", "tasks": len(plan["tasks"])}


def seal(project, slug):
    """P2: seal through guard.py (same code path as by hand). Options come from STATE.seal; the budget from the estimate."""
    md = _mdir(project, slug)
    if os.path.isfile(os.path.join(md, "SCELLE.json")):
        return 0, "deja scelle (seul un avenant peut le changer)"
    st = C.read_json(os.path.join(md, "STATE.json"))
    so = st.get("seal") if isinstance(st.get("seal"), dict) else {}
    args = [sys.executable, os.path.join(HERE, "guard.py"), "seal", "--project", os.path.abspath(project), "--slug", slug]
    for k in ("perimeter", "protect", "unprotect", "tests", "hosts", "forbid", "red"):
        v = so.get(k)
        if isinstance(v, list) and v:
            args += ["--" + k, ",".join(str(x) for x in v)]
    if so.get("color") in ("vert", "orange", "rouge"):
        args += ["--color", so["color"]]
    est = (st.get("budget") or {}).get("exec_estimate_k")
    if isinstance(so.get("budget"), int):
        args += ["--budget", str(so["budget"])]
    elif isinstance(est, list) and len(est) == 2 and isinstance(est[1], (int, float)):
        args += ["--budget", str(int(est[1] * 1000))]
    p = subprocess.run(args, cwd=os.path.abspath(project), capture_output=True, text=True, timeout=120)
    out = (p.stdout + p.stderr).strip()
    if p.returncode == 0:
        C.emit(md, "seal.written", "core", {"plan_sha256": C.read_json(os.path.join(md, "SCELLE.json")).get("plan_sha256")},
               mission_id=slug, dedup_key="seal")
    return p.returncode, out


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="compile_plan.py")
    ap.add_argument("slug")
    ap.add_argument("--project", default=os.getcwd())
    ap.add_argument("--seal", action="store_true", help="sceller ensuite (guard.py seal, empreinte du plan incluse)")
    a = ap.parse_args(argv)
    try:
        plan, rep = compile_plan(a.project, a.slug)
    except C.ContractError as e:
        print("REFUS : %s" % e)
        return 1
    print("PLAN %s : %d tache(s), %s ; pretes : %s" % (rep["action"], rep["tasks"], plan["source_order_hash"][:12],
                                                        ", ".join(t["id"] for t in plan["tasks"] if t["status"] == "ready") or "aucune"))
    if a.seal:
        rc, out = seal(a.project, a.slug)
        print(out)
        return 0 if rc == 0 else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
