# -*- coding: utf-8 -*-
"""budget.py : releve le cout reel d'une mission et calibre l'estimateur (lot L9, port generique de budget.ps1 du skill v1).
Bibliotheque standard, AUCUN reseau.

POURQUOI EN POINTS DE QUOTA ET NON EN TOKENS : l'outil get_usage ne donne pas la consommation cumulee. Il donne le quota des fenetres
(5 h, hebdomadaire) en POURCENT ENTIER, et l'OCCUPATION du contexte, qui redescend apres un compactage et ne mesure donc pas la depense.
Le seul cout observable est le delta de pourcentage de quota : c'est aussi l'unite de la vraie contrainte.

  budget.py start <slug> --usage FILE [--estime N] [--mesure complete|partielle]   ligne 0 du plan : pose la reference
  budget.py end   <slug> --usage FILE [--library DIR]                                deltas, reinitialisation de fenetre, report dans la note
  budget.py calibrate                                                                 facteur median (>= 3 missions completes)
  budget.py journal                                                                   liste le journal

FILE = la sortie JSON de get_usage ecrite dans un fichier. Journal : <home>/budget-journal.json, ou home = ~/.claude/super-reprompt
(SUPER_REPROMPT_HOME le remplace) ; aucun chemin personnel dans ce script. Codes : 0 succes · 2 usage/erreur · 3 delta invalide
(les deux fenetres reinitialisees).
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

TOLERANCE_S = 120      # resetsAt oscille de quelques ms d'un appel a l'autre : une egalite stricte declarait a tort une reinitialisation


class UsageError(Exception):
    pass


def ledger_path():
    return os.path.join(str(L.home_dir()), "budget-journal.json")


def read_ledger(path):
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def write_ledger(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def parse_usage(path):
    if not os.path.isfile(path):
        raise UsageError("Fichier get_usage introuvable : %s" % path)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            u = json.load(fh)
    except ValueError:
        raise UsageError("JSON get_usage illisible : %s" % path)
    plan = u.get("plan") if isinstance(u, dict) else None
    if not isinstance(plan, dict):
        raise UsageError("Ce JSON ne ressemble pas a une sortie get_usage (champ 'plan' absent).")
    if plan.get("status") != "ok":
        raise UsageError("plan.status = '%s' : les limites de plan ne sont pas lisibles ici, le cout reel n'est pas mesurable." % plan.get("status"))
    wins = plan.get("windows") or []
    w5 = next((w for w in wins if re.search(r"5-hour|5 h", str(w.get("label")))), None)
    wk = next((w for w in wins if "Weekly" in str(w.get("label")) and not re.search(r"Opus|Sonnet|Haiku", str(w.get("label")))), None)
    ctx = u.get("context") or {}
    return {"pct5h": int(w5["percentUsed"]) if w5 else None, "reset5h": w5.get("resetsAt") if w5 else None,
            "pctweek": int(wk["percentUsed"]) if wk else None, "resetweek": wk.get("resetsAt") if wk else None,
            "context": int(ctx["tokensUsed"]) if ctx.get("status") == "ok" and "tokensUsed" in ctx else None,
            "ts": time.strftime("%Y-%m-%d %H:%M")}


def _epoch(s):
    from datetime import datetime
    return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()


def _reset(a, b):
    if not a or not b:
        return False
    try:
        return abs(_epoch(a) - _epoch(b)) > TOLERANCE_S
    except ValueError:
        return a != b


def _fx(x):
    return ("%.2f" % x).replace(".", ",")


def cmd_start(a, ledger, out):
    u = parse_usage(a.usage)
    led = read_ledger(ledger)
    led[a.slug] = {"slug": a.slug, "estime": a.estime, "mesure": a.mesure, "debut": u["ts"], "start_5h": u["pct5h"], "start_hebdo": u["pctweek"],
                   "start_contexte": u["context"], "reset_5h": u["reset5h"], "reset_hebdo": u["resetweek"], "reel_5h": None, "reel_hebdo": None}
    write_ledger(ledger, led)
    out.append("Reference posee pour '%s' : 5h=%s%% hebdo=%s%% contexte=%s" % (a.slug, u["pct5h"], u["pctweek"], u["context"]))
    if a.estime < 1:
        out.append("  (aucune estimation fournie : passer --estime <points hebdo> pour permettre la calibration)")
    return 0


def _note_report(lib, slug, e, out):
    note = os.path.join(lib, "om-%s.md" % slug)
    if not os.path.isfile(note):
        out.append("  (pas d'entree om-%s.md en bibliotheque ; mesure gardee au journal)" % slug)
        return
    with open(note, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    done = 0
    for i, ln in enumerate(lines):
        if i > 0 and ln.strip() == "---":
            break
        for key, val in (("cout_reel_hebdo", e["reel_hebdo"]), ("cout_reel_5h", e["reel_5h"])):
            if re.match(r"^%s\s*:" % key, ln):
                lines[i] = "%s: %s" % (key, "" if val is None else val)
                done += 1
    if done:
        with open(note, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines))
        out.append("  reporte dans om-%s.md" % slug)
    else:
        out.append("  om-%s.md n'a pas les champs cout_reel_hebdo / cout_reel_5h : a ajouter a la main." % slug)


def cmd_end(a, ledger, out):
    u = parse_usage(a.usage)
    led = read_ledger(ledger)
    if a.slug not in led:
        led[a.slug] = {"slug": a.slug, "estime": -1, "mesure": "sans_reference", "fin": u["ts"], "fin_5h": u["pct5h"], "fin_hebdo": u["pctweek"],
                       "reel_5h": None, "reel_hebdo": None}
        write_ledger(ledger, led)
        out.append("Aucune reference de debut pour '%s' : le cout de cette mission est DEFINITIVEMENT non mesurable." % a.slug)
        out.append("Lecture de fin gardee a titre d'ancrage : 5h=%s%% hebdo=%s%%. Exclue du facteur de calibration." % (u["pct5h"], u["pctweek"]))
        out.append("Pour la prochaine mission : `start` est la LIGNE 0 du plan, avant toute autre action.")
        return 2
    e = led[a.slug]
    r5 = _reset(e.get("reset_5h"), u["reset5h"])
    rw = _reset(e.get("reset_hebdo"), u["resetweek"])
    d5 = u["pct5h"] - e["start_5h"] if u["pct5h"] is not None and e.get("start_5h") is not None else None
    dw = u["pctweek"] - e["start_hebdo"] if u["pctweek"] is not None and e.get("start_hebdo") is not None else None
    dc = u["context"] - e["start_contexte"] if u["context"] is not None and e.get("start_contexte") is not None else None
    out.append("Mission '%s' — %s -> %s" % (a.slug, e.get("debut"), u["ts"]))
    out.append("")
    if r5:
        out.append("  fenetre 5h REINITIALISEE pendant la mission : delta 5h non exploitable")
    if rw:
        out.append("  fenetre HEBDO REINITIALISEE pendant la mission : delta hebdo non exploitable")
    if not rw and dw is not None:
        out.append("  cout hebdomadaire : %3d point(s)  (%s%% -> %s%%)" % (dw, e["start_hebdo"], u["pctweek"]))
    if not r5 and d5 is not None:
        out.append("  cout fenetre 5h   : %3d point(s)  (%s%% -> %s%%)" % (d5, e["start_5h"], u["pct5h"]))
    if dc is not None:
        out.append("  contexte          : %s%d tokens (occupation, PAS la depense)" % ("+" if dc >= 0 else "", dc))
    if e.get("estime", -1) >= 1 and not rw and dw is not None:
        ratio = (dw / e["estime"]) if dw > 0 else 0.0
        out.append("")
        out.append("  estime %s pt -> reel %s pt   ecart x%s" % (e["estime"], dw, _fx(ratio)))
        if dw == 0:
            out.append("  (0 point : sous la resolution du pourcentage entier hebdo — se fier au delta 5h pour les petites missions)")
    e["reel_5h"] = None if r5 else d5
    e["reel_hebdo"] = None if rw else dw
    e["delta_contexte"] = dc
    e["fin"] = u["ts"]
    led[a.slug] = e
    write_ledger(ledger, led)
    if a.library:
        out.append("")
        _note_report(a.library, a.slug, e, out)
    return 3 if (r5 and rw) else 0


def cmd_calibrate(ledger, out):
    led = read_ledger(ledger)
    done = [e for e in led.values() if e.get("reel_hebdo") is not None and e.get("estime", -1) >= 1 and e.get("mesure") == "complete"]
    out.append("Calibration de l'estimateur (points de quota hebdomadaire)")
    out.append("---------------------------------------------------------")
    part = sum(1 for e in led.values() if e.get("mesure") == "partielle")
    if part:
        out.append("  (%d mesure(s) partielle(s) exclue(s) du facteur)" % part)
    if len(done) < 3:
        out.append("")
        out.append("  %d mission(s) mesuree(s) completement sur les 3 requises." % len(done))
        out.append("  AUCUN facteur emis : un facteur tire de moins de 3 points est du bruit,")
        out.append("  et un mauvais facteur est pire qu'aucun facteur. Continuer a mesurer.")
        return 0
    ratios = sorted(e["reel_hebdo"] / e["estime"] for e in done)
    n = len(ratios)
    med = ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2
    out.append("")
    out.append("  n = %d missions · facteur median = %s · etendue %s a %s" % (n, _fx(med), _fx(ratios[0]), _fx(ratios[-1])))
    out.append("")
    if med > 1.15:
        out.append("  L'estimateur SOUS-ESTIME : multiplier les estimations par %s." % _fx(med))
    elif med < 0.85:
        out.append("  L'estimateur SUR-ESTIME : multiplier les estimations par %s." % _fx(med))
    else:
        out.append("  L'estimateur est calibre (facteur entre 0,85 et 1,15). Ne rien changer.")
    if ratios[-1] - ratios[0] > 1.5:
        out.append("  ATTENTION : etendue large, le facteur median cache des formes de mission tres differentes. Calibrer par CLASSE.")
    out.append("")
    out.append("  Detail :")
    for e in done:
        out.append("    %-26s estime %4s -> reel %4s  (x%s)" % (e["slug"], e["estime"], e["reel_hebdo"], _fx(e["reel_hebdo"] / e["estime"])))
    return 0


def cmd_journal(ledger, out):
    led = read_ledger(ledger)
    if not led:
        out.append("Journal vide.")
        return 0
    out.append("Journal des budgets (%d entree(s)) :" % len(led))
    for k in sorted(led):
        e = led[k]
        r = ("reel %s pt hebdo / %s pt 5h" % (e["reel_hebdo"], e["reel_5h"])) if e.get("reel_hebdo") is not None else "en cours"
        x = ("estime %s pt" % e["estime"]) if e.get("estime", -1) >= 0 else "sans estimation"
        out.append("  %-26s %-20s %-34s %s" % (k, x, r, e.get("mesure", "")))
    return 0


def run(argv, ledger=None):
    """Retourne (code, texte). `ledger` remplace le journal par defaut (tests)."""
    ap = argparse.ArgumentParser(prog="budget.py", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    for name in ("start", "end"):
        p = sub.add_parser(name)
        p.add_argument("slug")
        p.add_argument("--usage", required=True)
        if name == "start":
            p.add_argument("--estime", type=int, default=-1)
            p.add_argument("--mesure", choices=("complete", "partielle"), default="complete")
        else:
            p.add_argument("--library", default=None)
    sub.add_parser("calibrate")
    sub.add_parser("journal")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return (0 if e.code in (0, None) else 2), ""
    if not a.cmd:
        return 2, __doc__
    ledger = ledger or ledger_path()
    out = []
    try:
        if a.cmd == "start":
            code = cmd_start(a, ledger, out)
        elif a.cmd == "end":
            code = cmd_end(a, ledger, out)
        elif a.cmd == "calibrate":
            code = cmd_calibrate(ledger, out)
        else:
            code = cmd_journal(ledger, out)
    except UsageError as e:
        return 2, str(e)
    return code, "\n".join(out)


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    code, text = run(argv)
    stream = sys.stdout if code in (0, 3) else sys.stderr
    if text:
        print(text, file=stream)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
