# -*- coding: utf-8 -*-
"""memoire.py : P8 du cycle V3.1 (lot 7). Bibliotheque standard, AUCUN reseau, AUCUN appel de modele.

La partie mecanique du rangement est faite par script (0 token) ; l'agent sr-archiviste n'est lance que pour ce qui
demande un jugement (tableau, consolidation), sr-synthese pour la synthese de cloture.

  memoire.py archive <dossier de mission> <slug> [--vault V]   decisions, lecons (evenements log.*) et risques ouverts
      (recus) -> notes du projet ; dedupliques, sans secret, ecrits SEULEMENT dans le dossier du projet ; idempotent.
  memoire.py reprise <dossier de mission> <slug> [--vault V]   REPRISE.md (< 1 200 tokens) : objectif, etat, reste,
      decisions, risques, budget, prochaine action. Ecrit a la cloture, relu par `manager.py status`.

Vault : --vault, sinon SR_VAULT_PATH, sinon CLAUDE_PLUGIN_OPTION_VAULT_PATH ; sans vault, mode degrade explicite :
<dossier de mission>/memoire/. Le journal operationnel reste events.ndjson ; le vault n'est qu'une projection.
Etancheite : ce script ne lit que la mission donnee et ne lit/ecrit que projets/<slug>/ ; aucune autre note n'est ouverte.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contracts as C  # noqa: E402
import vault as V  # noqa: E402

REPRISE_MAX_TOKENS = 1200
CHARS_PER_TOKEN = 3.7


def _ctx(mdir, vault):
    v = vault if vault is not None else (os.environ.get("SR_VAULT_PATH") or os.environ.get("CLAUDE_PLUGIN_OPTION_VAULT_PATH") or None)
    if v and os.path.isdir(v):
        return V.Ctx(os.path.abspath(v), True), "vault"
    return V.Ctx(os.path.dirname(os.path.abspath(mdir)), False), "local (aucun vault configure)"


def _risks(mdir):
    out = []
    rd = os.path.join(mdir, "receipts")
    for dp, _, fs in sorted(os.walk(rd)):
        for f in sorted(fs):
            if f.endswith(".json"):
                try:
                    r = C.read_json(os.path.join(dp, f))
                except C.ContractError:
                    continue
                for x in r.get("unresolved_risks") or []:
                    out.append((r.get("task_id"), str(x)))
    return out


def _items(mdir):
    dec, lec = [], []
    for e in C.read_events(mdir):
        t = (e.get("payload") or {}).get("text")
        if not t:
            continue
        if e["event_type"] == "log.decision":
            dec.append(" ".join(str(t).split()))
        elif e["event_type"] in ("log.lecon", "log.lesson"):
            lec.append(" ".join(str(t).split()))
    return dec, lec


def archive(mdir, slug, vault=None):
    """Deterministic part of the archivist. Returns the counts; writes nothing twice (exact-line dedup)."""
    V.check_slug(slug)
    ctx, mode = _ctx(mdir, vault)
    V.ensure_project(ctx, slug)
    d = ctx.project_dir(slug)
    day = V.today()
    dec, lec = _items(mdir)
    rep = {"decisions": 0, "lecons": 0, "risques": 0, "refuses": 0, "mode": mode, "dossier": d}
    targets = (("decisions", "%s-decisions.md" % slug, dec, "- %s · %s [mission]\n"),
               ("lecons", "%s-lecons.md" % slug, lec, "- %s · %s\n"),
               ("risques", "%s-decisions.md" % slug, ["risque ouvert (%s) : %s" % r for r in _risks(mdir)], "- %s · %s\n"))
    with V.Lock(V.lock_path(ctx, slug)):
        for key, fn, items, fmt in targets:
            p = os.path.join(d, fn)
            have = V.read_text(p) if os.path.exists(p) else ""
            seen = set()
            for it in items:
                if it in seen:
                    continue
                seen.add(it)
                if V.looks_secret(it):
                    rep["refuses"] += 1
                    continue
                if (" · %s" % it) in have:
                    continue
                line = fmt % (day, it)
                V.append(p, line)
                have += line
                rep[key] += 1
    C.emit(mdir, "memory.archived", "core", {k: rep[k] for k in ("decisions", "lecons", "risques", "refuses", "mode")}, mission_id=slug)
    return rep


def reprise(mdir, slug, vault=None):
    """Compact resume brief from THIS mission's canonical files only (plan, receipts, events, ledger) + its own notes."""
    V.check_slug(slug)
    ctx, mode = _ctx(mdir, vault)
    plan = C.read_json(os.path.join(mdir, "PLAN.json"), default=None) or {}
    st = C.read_json(os.path.join(mdir, "STATE.json"), default=None) or {}
    tasks = plan.get("tasks", [])
    done = [t for t in tasks if t.get("status") == "done"]
    rest = [t for t in tasks if t.get("status") not in ("done", "skipped", "cancelled")]
    dec, lec = _items(mdir)
    L = ["# Reprise : mission %s (%s)" % (slug, C.now_utc()), ""]
    reqs = [r.get("text") for r in st.get("requirements", []) if isinstance(r, dict)]
    if reqs:
        L.append("Objectif : " + " ; ".join(str(x)[:90] for x in reqs[:5]))
    L.append("Etat : %d/%d taches done%s" % (len(done), len(tasks), " ; mission close" if os.path.exists(os.path.join(mdir, "FERME")) else ""))
    if done:
        L.append("Fait : " + ", ".join("%s (recu %s)" % (t["id"], t.get("receipt")) for t in done[:12]))
    if rest:
        L.append("Reste : " + ", ".join("%s %s [%s]" % (t["id"], str(t.get("title", ""))[:40], t.get("status")) for t in rest[:12]))
    if dec:
        L += ["", "## Decisions"] + ["- " + x[:160] for x in list(dict.fromkeys(dec))[-6:] if not V.looks_secret(x)]
    if lec:
        L += ["", "## Lecons"] + ["- " + x[:160] for x in list(dict.fromkeys(lec))[-4:] if not V.looks_secret(x)]
    rk = _risks(mdir)
    if rk:
        L += ["", "## Risques ouverts"] + ["- %s : %s" % (t, x[:160]) for t, x in rk[-6:] if not V.looks_secret(x)]
    try:
        import econ
        r = econ.rapport(mdir, plan, C.read_json(os.path.join(mdir, "SCELLE.json"), default=None) or {})
        L += ["", "Budget : actual %d, estimated %d, projected %d (jamais additionnes sans le dire)" % (r["actual"], r["estimated"], r["projected"])]
    except Exception as e:                        # degraded, said: the brief stays useful without the ledger
        L += ["", "Budget : indisponible (%s)" % type(e).__name__]
    running = next((t for t in rest if t.get("status") == "running"), None)
    if running:
        action = "`manager.py done %s` des que sa remontee arrive" % running["id"]
    elif rest:
        action = "`manager.py next`"
    else:
        action = "cloture : synthese puis `mission.py close`"
    L += ["", "Prochaine action : " + action, "Memoire du projet : %s (%s)" % (ctx.project_dir(slug), mode)]
    txt = "\n".join(L) + "\n"
    cap = int(REPRISE_MAX_TOKENS * CHARS_PER_TOKEN)
    if len(txt) > cap:
        txt = txt[:cap - 2] + "…\n"
    C.atomic_write_text(os.path.join(mdir, "REPRISE.md"), txt)
    C.emit(mdir, "memory.resume_written", "core", {"chars": len(txt)}, mission_id=slug)
    return txt


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="memoire.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("archive", "reprise"):
        s = sub.add_parser(n)
        s.add_argument("mission_dir")
        s.add_argument("slug")
        s.add_argument("--vault")
    a = ap.parse_args(argv)
    if a.cmd == "archive":
        r = archive(a.mission_dir, a.slug, a.vault)
        print("archive %s : %d decision(s), %d lecon(s), %d risque(s), %d refus (secret) -> %s [%s]"
              % (a.slug, r["decisions"], r["lecons"], r["risques"], r["refuses"], r["dossier"], r["mode"]))
    else:
        print(reprise(a.mission_dir, a.slug, a.vault), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
