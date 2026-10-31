# -*- coding: utf-8 -*-
"""SessionStart hook (H2, matcher "compact|resume"): re-inject a short mission reminder.

When the session that just resumed or was compacted is the one working on a mission (framing_session_id or
exec_session_id equals the hook's session_id, status framing or executing), prints at most about 400 tokens of
plain text (a SessionStart hook's plain stdout is added to Claude's context): paths of ORDRE.md / NOTES.md,
status, tier, budget left, reply language, open items and six short rules. Otherwise prints nothing.
Always exits 0. SUPER_REPROMPT_HOOKS=0 turns the hook off.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

MAX_CHARS = 1600  # about 400 tokens


def _open_items(st):
    caps = [c for c in st.get("capabilities", []) if isinstance(c, dict) and c.get("required") and not c.get("removed_reason")
            and not (isinstance(st.get("calls"), dict) and st["calls"].get(c.get("id"), 0))]
    ver = st.get("verification", {}) if isinstance(st.get("verification"), dict) else {}
    cmds = [c for c in ver.get("commands", []) if isinstance(c, dict) and c.get("state") == "pending"]
    crits = [c for c in ver.get("criteria", []) if isinstance(c, dict) and not c.get("passes")]
    return len(caps), len(cmds), len(crits)


def build_reminder(project, slug, st, source):
    d = L.mission_dir(project, slug)
    b = st.get("budget", {}) if isinstance(st.get("budget"), dict) else {}
    cap = b.get("cap_k")
    spent = b.get("spent_est_k", 0) or 0
    left = ("%s k" % round(cap - spent, 1)) if isinstance(cap, (int, float)) else "unknown"
    nc, nv, nk = _open_items(st)
    status = st.get("status")
    lang = st.get("lang") or "en"
    if L.lang_is_french(lang):
        phase = ("EXÉCUTION en cours : relire l'ordre et la fin des notes avant de continuer." if status == "executing"
                 else "CADRAGE en cours (phases P0 à P7) : relire les notes pour les réponses déjà recueillies.")
        text = (
            "[super-reprompt] Mission en cours après %(source)s : \"%(slug)s\" (statut %(status)s, palier %(tier)s, langue de réponse %(lang)s).\n"
            "Fichiers : ordre %(order)s ; notes %(notes)s ; état %(state)s.\n"
            "%(phase)s\n"
            "Budget : %(spent)s k dépensés (estimation) sur un plafond de %(cap)s k ; reste %(left)s.\n"
            "À faire : %(nc)d capacité(s) requise(s) pas encore appelée(s), %(nv)d commande(s) de vérification en attente, %(nk)d critère(s) non satisfait(s).\n"
            "Règles de l'ordre : (1) lire ORDRE.md et NOTES.md avant d'agir ; (2) appeler réellement chaque capacité requise, ne jamais prétendre un appel qui n'a pas eu lieu ; "
            "(3) dire pour chaque vérification executed / not_executable / not_run et appliquer le plan B ; (4) rester dans le périmètre et la liste deny ; "
            "(5) suivre la dépense avec mission.py spent et s'arrêter au plafond ; (6) écrire REPORT.md puis lancer mission.py close."
        )
    else:
        phase = ("EXECUTION in progress: re-read the order and the end of the notes before continuing." if status == "executing"
                 else "FRAMING in progress (phases P0 to P7): re-read the notes for the answers collected so far.")
        text = (
            "[super-reprompt] Mission in progress after %(source)s: \"%(slug)s\" (status %(status)s, tier %(tier)s, reply language %(lang)s).\n"
            "Files: order %(order)s; notes %(notes)s; state %(state)s.\n"
            "%(phase)s\n"
            "Budget: %(spent)s k spent (estimate) of a %(cap)s k cap; %(left)s left.\n"
            "Open: %(nc)d required capability(ies) not yet called, %(nv)d pending verification command(s), %(nk)d unmet criterion(a).\n"
            "Rules recorded in the order: (1) read ORDRE.md and NOTES.md before acting; (2) call each required capability for real and never claim a call that did not happen; "
            "(3) report each verification as executed / not_executable / not_run and apply plan B; (4) stay inside scope and the deny list; "
            "(5) track spend with mission.py spent and stop at the cap; (6) write REPORT.md, then run mission.py close."
        )
    out = text % {
        "source": source, "slug": slug, "status": status, "tier": st.get("tier"), "lang": lang,
        "order": str(d / "ORDRE.md"), "notes": str(d / "NOTES.md"), "state": str(d / "STATE.json"),
        "phase": phase, "spent": spent, "cap": cap if cap is not None else "?", "left": left,
        "nc": nc, "nv": nv, "nk": nk,
    }
    return out if len(out) <= MAX_CHARS else out[: MAX_CHARS - 3] + "..."


def body():
    data = L.read_stdin_json()
    source = data.get("source")
    if source not in ("compact", "resume"):
        return
    sid = data.get("session_id")
    if not sid:
        return
    cwd = data.get("cwd") or os.getcwd()
    project = L.find_project(cwd)
    if project is None:
        env = os.environ.get("CLAUDE_PROJECT_DIR", "")
        project = L.find_project(env) if env else None
    if project is None:
        return
    for slug, st in L.iter_missions(project):
        status = st.get("status")
        mine = ((status == "executing" and st.get("exec_session_id") == sid)
                or (status == "framing" and st.get("framing_session_id") == sid))
        if mine:
            L.emit(build_reminder(project, slug, st, source))
            L.log("hook_compact", "reminder for %s (%s)" % (slug, source))
            return


def main():
    return L.run_hook("hook_compact", body, __doc__)


if __name__ == "__main__":
    sys.exit(main())
