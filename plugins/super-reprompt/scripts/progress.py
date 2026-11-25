# -*- coding: utf-8 -*-
"""progress.py : pole PROGRESS de V3.1 (lot 9). Bibliotheque standard, AUCUN reseau, AUCUN appel de modele.

BAR.json est une PROJECTION de PLAN.json + events.ndjson, recalculee par `manager.py next` et `done` ; la barre de
l'app (hooks/bar/register.tsx) la lit telle quelle. Personne ne la saisit a la main.

  - Avancement : seules les taches VALIDEES (done, skipped, cancelled) comptent ; percent_tasks (nombre) et percent_work
    (pondere par estimated_duration, sinon volume_tokens, sinon 1) sont donnes separement.
  - Temps actif : intervalles entre evenements successifs de la mission, chaque intervalle plafonne a IDLE_GAP_MIN
    (regle explicite : au-dela, c'est une pause, pas du travail).
  - ETA : effort restant estime (estimated_duration des taches non terminees) x rapport observe / estime des taches
    terminees (mediane, quartiles) ; fourchette basse-haute et confiance (faible n < 3, moyenne 3-5, bonne >= 6).
    Sans historique : fourchette large x0,5 - x2, confiance « faible (n = 0) ».
  - Precision : arrondi a 5 min sous l'heure, au quart d'heure au-dessus ; jamais une heure a la minute.

CLI : progress.py <dossier de mission>   -> ecrit BAR.json et l'affiche
"""
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contracts as C  # noqa: E402

IDLE_GAP_MIN = 20
TOKENS_PER_MIN = 2000          # repli quand une tache n'a pas d'estimated_duration (hypothese, non calibree)
DONE = ("done", "skipped", "cancelled")


def _t(s):
    try:
        return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return None


def _est(t):
    if isinstance(t.get("estimated_duration"), (int, float)):
        return float(t["estimated_duration"])
    if isinstance(t.get("volume_tokens"), (int, float)) and t["volume_tokens"] > 0:
        return float(t["volume_tokens"]) / TOKENS_PER_MIN
    return None


def _weight(t):
    return _est(t) or 1.0


def _round(m):
    if m < 60:
        return int(5 * max(1, round(m / 5.0)))
    return int(15 * round(m / 15.0))


def _fmt(m):
    m = _round(m)
    return "%d min" % m if m < 60 else "%d h %02d" % (m // 60, m % 60)


def _active(times, gap):
    times = sorted(x for x in times if x is not None)
    return sum(min(b - a, gap) for a, b in zip(times, times[1:]))


def projection(mdir):
    plan = C.read_json(os.path.join(mdir, "PLAN.json"), default=None) or {}
    tasks = plan.get("tasks", [])
    evs = C.read_events(mdir)
    gap = IDLE_GAP_MIN * 60
    all_t = [_t(e.get("timestamp")) for e in evs]
    # observed active duration per task: from its dispatch to its result, only the active slices of the mission clock
    start, obs = {}, {}
    for e in evs:
        pl, tt = e.get("payload") or {}, _t(e.get("timestamp"))
        if e["event_type"] == "task.dispatched":
            start[pl.get("task")] = tt
        elif e["event_type"] == "task.done" and pl.get("task") in start:
            a = start[pl["task"]]
            inside = [x for x in all_t if x is not None and a is not None and tt is not None and a <= x <= tt]
            obs[pl["task"]] = _active(inside + [a, tt], gap) / 60.0
    done = [t for t in tasks if t.get("status") in DONE]
    tot_w = sum(_weight(t) for t in tasks) or 1.0
    pct_work = int(100 * sum(_weight(t) for t in done) / tot_w) if tasks else 0
    pct_tasks = int(100 * len(done) / len(tasks)) if tasks else 0
    ratios = [obs[t["id"]] / _est(t) for t in done if t["id"] in obs and _est(t)]
    remaining = sum(_est(t) or 0 for t in tasks if t.get("status") not in DONE)
    n = len(ratios)
    if n == 0:
        lo_r, med, hi_r, conf = 0.5, 1.0, 2.0, "faible (n = 0)"
        basis = "estimations du cadrage seules (aucune duree observee)"
    else:
        s = sorted(ratios)
        med = statistics.median(s)
        lo_r = s[int(0.25 * (n - 1))] if n >= 3 else min(s) * 0.75
        hi_r = s[int(round(0.75 * (n - 1)))] if n >= 3 else max(s) * 1.5
        conf = "faible" if n < 3 else ("moyenne" if n < 6 else "bonne")
        basis = "%d duree(s) observee(s), rapport observe / estime median %.2f" % (n, med)
    lo, hi = remaining * min(lo_r, med), remaining * max(hi_r, med)
    if not tasks or remaining == 0 and len(done) == len(tasks):
        text = "termine" if tasks else ""
    elif remaining == 0:
        text = "duree inconnue (aucune estimation)"
    else:
        text = ("%s - %s" % (_fmt(lo), _fmt(hi)) if _round(lo) != _round(hi) else "~ %s" % _fmt(lo)) + " (confiance %s)" % conf.split(" ")[0]
    return {"source": "PLAN.json + events.ndjson", "mission": plan.get("slug"), "updated": C.now_utc(),
            "done": len(done), "total": len(tasks), "percent_tasks": pct_tasks, "percent_work": pct_work,
            "running": [t["id"] for t in tasks if t.get("status") == "running"],
            "blocked": [t["id"] for t in tasks if t.get("status") == "blocked"],
            "elapsed_active_min": round(_active(all_t, gap) / 60.0, 1),
            "eta": {"remaining_min_low": round(lo, 1), "remaining_min_high": round(hi, 1), "ratio_median": round(med, 3),
                    "confidence": conf, "observed_tasks": n, "basis": basis,
                    "rule_idle": "tout intervalle sans evenement de plus de %d min compte comme une pause (%d min retenues)" % (IDLE_GAP_MIN, IDLE_GAP_MIN)},
            "display": {"percent": pct_work, "text": text}}


def write(mdir):
    b = projection(mdir)
    C.atomic_write_json(os.path.join(mdir, "BAR.json"), b)
    return b


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    print(json.dumps(write(argv[0]), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
