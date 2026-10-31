# -*- coding: utf-8 -*-
"""UserPromptSubmit hook (H1): suggest framing a large request. Never blocks, never orders.

Reads the hook JSON on stdin. Prints at most ONE line (plain stdout of a UserPromptSubmit hook is added to
Claude's context) when the prompt scores at least THRESHOLD, otherwise prints nothing. Always exits 0.

Scoring (English and French, accents ignored): categories with a weight (project, breadth, deliverable,
architecture, money, multi-source, vagueness, decision, data) plus bonuses (long prompt, stacked wants, many
files, many links, long list). Suppressed for: slash/shell commands, very short prompts, bare
acknowledgements, short factual questions, waivers ("go direct", "sans cadrage", "no framing",
"don't ask me questions"), a framing already in progress, and for 15 minutes after a suggestion in the
same session. When a suggestion is emitted and the transcript file (size only, never its content) suggests a
long conversation, a short warning is appended to the same line. SUPER_REPROMPT_HOOKS=0 turns the hook off.
"""
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

THRESHOLD = 3
MIN_LEN = 60
COOLDOWN_S = 15 * 60
FACTUAL_MAX_LEN = 220
SKILL_COMMAND = "/super-reprompt:super-reprompt"

# Long-conversation warning: starting values, to be calibrated against /context readings.
# The estimate uses only the SIZE of the transcript file (os.path.getsize); its content is never read.
BYTES_PER_TOKEN = 16          # prudent starting value (an owner measurement gave about 19 bytes per token)
LONG_CONV_TOKENS = 60000      # at or above: short factual warning
VERY_LONG_CONV_TOKENS = 150000  # at or above: the same warning, worded "strongly"


def norm(s):
    """Lower-case, drop accents, unify quotes and whitespace."""
    s = s.replace("’", "'").replace("‘", "'").replace("«", '"').replace("»", '"')
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    return re.sub(r"[ \t\r\f\v]+", " ", s)


def _rx(p):
    return re.compile(p)


# Paths, quoted file mentions and URLs carry words ("analyse", "cahier des charges") that are names, not requests.
PATH_RX = re.compile(
    r"(@\"[^\"]*\"|@'[^']*'"                      # @"quoted mention" or @'quoted mention'
    r"|\"[a-z]:[\\/][^\"]*\""                     # "C:\quoted path"
    r"|[a-z]:[\\/][^\s\"']*"                      # C:\path\to\thing (up to the next space)
    r"|(?:~|\.{1,2})?(?:/[\w.@+-]+){2,}/?"        # /unix/like/path
    r"|https?://\S+"                              # URL
    r"|[\w.-]+\.(?:py|ts|tsx|js|jsx|md|json|ps1|sh|csv|xlsx|docx|pptx|pdf|ya?ml|toml))")  # bare file name


def strip_paths(t):
    return PATH_RX.sub(" ", t)


# (label, weight, regex on the normalised text)
CATEGORIES = [
    ("project", 2, _rx(r"\b(projets?|missions?|chantier|refonte|cahier des charges|mise en place|(met|mets|mettre|mette|mettons)\w* en place|roadmap|feuille de route|from scratch|de zero|overhaul|business plan|plan d'action|go-to-market|set ?up)\b")),
    ("breadth", 2, _rx(r"\b(approfondi\w*|en profondeur|complets?|completes?|exhaustif\w*|de bout en bout|end[- ]to[- ]end|comprehensive|thorough\w*|in[- ]depth|exhaustive|entire\w*|entierement|whole (project|codebase|repo)|tout le projet|full( [a-z-]+)? (audit|analysis|review|report|study|plan|refactor|rewrite|migration)|l'ensemble d(es|u|e)|every single)\b")),
    ("deliverable", 2, _rx(r"\b(analys\w*|etudes?|audit\w*|rapports?|memos?|dossier|livrables?|syntheses?|reports?|white ?papers?|deliverables?|studies|study|presentation|deck|slides|proposal)\b")),
    ("architecture", 2, _rx(r"\b(architectur\w*|refactor\w*|re-?factor\w*|restructur\w*|migrat\w*|migr(e|er|ons|ez)|redesign\w*|re-?architect\w*|reorganis\w*|reorganiz\w*|pipelines?|infrastructure|microservices?)\b")),
    ("money", 2, _rx(r"(€|\$\s?\d|\b\d+\s?(k|m)?\s?(euros?|eur|usd|dollars?)\b|\b(euros?|invest\w*|allocation|portefeuille\w*|portfolio\w*|budget\w*|valuation|valorisation|rentabilit\w*|profitab\w*|yield|rendement\w*|fiscal\w*|taxes|tax|etfs?|opcvm|sicav|scpi|assurance-vie|epargne|savings|pricing|revenue|funding|mortgage|dettes?|debts?|credits?)\b)")),
    ("multi-source", 1, _rx(r"\b(sources?|sur le web|on the web|etat de l'art|state of the art|veille|concurren\w*|competit\w*|benchmark\w*|compar\w*|literature review|market research|etude de marche)\b")),
    ("vagueness", 1, _rx(r"(\bje (ne )?sais pas (trop|vraiment|comment)\b|\bun truc\b|\bquelque chose comme\b|\ben gros\b|\bidealement\b|\bje verrai\b|\bpeut-etre\b|\bnot sure\b|\bkind of\b|\bsort of\b|\bsomething like\b|\bideally\b|\bmaybe\b|\bi guess\b|\bi don't know\b)")),
    ("decision", 1, _rx(r"\b(strateg\w*|faut-il|dois-je|devrais-je|vaut-il (le coup|mieux)|choisir entre|arbitrer|should (i|we)|which (one )?is better|choose between|trade-?offs?|pros and cons|buy or rent|rent or buy|acheter ou louer)\b")),
    ("data", 2, _rx(r"\b(scrap\w*|extrai\w*|extract\w*|collect\w*|tableaux?|colonnes?|datasets?|jeux? de donnees|consolid\w*|tracking|tracker|csv|spreadsheets?|tableur|database|base de donnees|etl|parse[rsd]?|track(s|er|ing)?)\b")),
]

WANTS_RX = _rx(r"(\bje veux\b|\bj'aimerais\b|\bje voudrais\b|\bil faut que\b|\bil faudrait\b|\bi want\b|\bi need\b|\bi'd like\b|\bi would like\b|\bwe need\b|\bplease also\b|\bet aussi\b)")
FILES_RX = _rx(r"\b[\w./\\-]*\w\.(py|ts|tsx|js|jsx|md|json|ps1|sh|csv|xlsx|docx|pptx|pdf|ya?ml|toml|rs|go|java|cpp|html|css|sql)\b")
URL_RX = _rx(r"https?://")
LIST_RX = _rx(r"(?m)^\s*(\d+[.)]|[-*•])\s+\S")

WAIVER_RX = _rx(r"(go direct|sans cadrage|sans reprompt|no framing|don't ask me (any )?questions|dont ask me (any )?questions|do not ask me (any )?questions|ne me pose pas de questions|sans me poser de questions|skip the framing|pas de cadrage)")
ACK_RX = _rx(r"^\s*(?:ok(?:ay)?|oui|yes|yep|yeah|non|no|nope|go|vas-y|allez|merci|thanks|thank you|thx|continue|stop|d'accord|c'est bon|parfait|nickel|perfect|great|annule|cancel|super|bien|good)\b[\s,.!;:—-]+(.*)$")
FACTUAL_RX = _rx(r"^\s*(c'est quoi|qu'est-ce (que|qui)|quest-ce|what is|what's|what are|what does|what do|how do i|how to|how can i|how does|how do you|ou (est|se trouve|sont)|where is|where are|combien|quelle? est|quels? sont|quelles? sont|which command|comment (faire|fait|on|puis-je|s'appelle|ca marche)|rappelle[- ]moi|explain|explique|why |pourquoi |who |qui est|when |quand |is there|y a-t-il|can you check|peux-tu verifier)")

FR_WORDS = set("le la les des un une et pour que je mon ma mes de du dans avec sur est faut veux fais tu ce cette qui ne pas plus ou au aux ses nos notre vos votre j'ai il elle nous vous sont etre avoir aussi mais donc comme".split())
EN_WORDS = set("the and for with that this my your you is are to of in i want need please a an it we our they be have also but so as at on by from not what how".split())


def detect_lang(t):
    words = re.findall(r"[a-z']+", t)
    fr = sum(1 for w in words if w in FR_WORDS)
    en = sum(1 for w in words if w in EN_WORDS)
    return "fr" if fr > en else "en"


def score_prompt(prompt):
    """Return (score, labels, suppressed_reason_or_None, lang). Pure function, no side effects."""
    if not isinstance(prompt, str):
        return 0, [], "no-prompt", "en"
    raw = prompt.strip()
    t = norm(raw)
    lang = detect_lang(t)
    if not raw:
        return 0, [], "empty", lang
    if raw[0] in "/!":
        return 0, [], "command", lang
    if "super-reprompt" in t:
        return 0, [], "mentions-skill", lang
    if WAIVER_RX.search(t):
        return 0, [], "waiver", lang
    if len(raw) < MIN_LEN:
        return 0, [], "short", lang
    m = ACK_RX.match(t)
    if m and len(m.group(1).strip()) < MIN_LEN:
        return 0, [], "ack", lang
    if len(raw) < FACTUAL_MAX_LEN and FACTUAL_RX.match(t):
        return 0, [], "factual", lang

    score, labels = 0, []
    ts = strip_paths(t)
    for label, weight, rx in CATEGORIES:
        if rx.search(ts):
            score += weight
            labels.append(label)
    n = len(raw)
    if n > 400:
        score += 1
        labels.append("long")
    if n > 900:
        score += 1
        labels.append("very-long")
    wants = len(WANTS_RX.findall(ts))
    if wants >= 3:
        score += 2 if wants >= 4 else 1
        labels.append("stacked-wants")
    if len(FILES_RX.findall(t)) >= 3:
        score += 1
        labels.append("many-files")
    if len(URL_RX.findall(t)) >= 3:
        score += 1
        labels.append("many-links")
    if len(LIST_RX.findall(raw)) >= 4:
        score += 1
        labels.append("long-list")
    return score, labels, None, lang


def suggestion_line(score, labels, lang):
    why = ", ".join(labels)
    if lang == "fr":
        return ("[super-reprompt] Cette demande ressemble à une mission en plusieurs volets (score %d/%d : %s). "
                "Si l'utilisateur souhaite la cadrer avant de commencer, il peut lancer %s ; "
                "il peut aussi dire « go direct » pour passer le cadrage." % (score, THRESHOLD, why, SKILL_COMMAND))
    return ("[super-reprompt] This request looks like a multi-part task (score %d/%d: %s). "
            "If the user wants it framed before work starts, they can run %s; "
            "they can also say \"go direct\" to skip framing." % (score, THRESHOLD, why, SKILL_COMMAND))


def estimate_conversation_tokens(transcript_path):
    """Rough token estimate from the transcript file size, or None. Never opens the file."""
    if not isinstance(transcript_path, str) or not transcript_path.strip():
        return None
    try:
        size = os.path.getsize(transcript_path)
    except Exception:
        return None
    if size <= 0:
        return None
    return size // BYTES_PER_TOKEN


def long_conversation_note(transcript_path, lang):
    """Return a short warning (str) when the conversation looks long, else ''. Fail-open: never raises."""
    try:
        tokens = estimate_conversation_tokens(transcript_path)
        if tokens is None or tokens < LONG_CONV_TOKENS:
            return ""
        k = int(round(tokens / 1000.0))
        strong = tokens >= VERY_LONG_CONV_TOKENS
        if lang == "fr":
            return (" Conversation déjà longue, environ %d k tokens estimés ; cadrer ici la relit à chaque tour ; "
                    "%s/clear ou une session neuve d'abord coûte moins cher." % (k, "fortement conseillé : " if strong else ""))
        return (" Conversation already long, about %d k tokens estimated; framing here re-reads it on every turn; "
                "%s/clear or a new session first is cheaper." % (k, "strongly: " if strong else ""))
    except Exception:
        return ""


def _safe_sid(sid):
    return re.sub(r"[^A-Za-z0-9_-]", "", str(sid or ""))[:80]


def _cooldown_file(sid):
    return L.home_dir() / "state" / ("cooldown-%s.txt" % _safe_sid(sid))


def in_cooldown(sid, now):
    if not _safe_sid(sid):
        return False
    try:
        with open(str(_cooldown_file(sid)), "r", encoding="utf-8") as f:
            last = float(f.read().strip() or 0)
        return (now - last) < COOLDOWN_S
    except Exception:
        return False


def set_cooldown(sid, now):
    if not _safe_sid(sid):
        return
    try:
        d = L.home_dir() / "state"
        d.mkdir(parents=True, exist_ok=True)
        with open(str(_cooldown_file(sid)), "w", encoding="utf-8") as f:
            f.write("%d" % now)
        # housekeeping: forget cooldown files older than one day
        for p in d.glob("cooldown-*.txt"):
            try:
                if now - p.stat().st_mtime > 86400:
                    p.unlink()
            except Exception:
                pass
    except Exception:
        pass


def framing_in_progress(cwd, sid):
    """True if a mission is being framed or executed by this very session."""
    if not sid:
        return False
    project = L.find_project(cwd) if cwd else None
    if project is None:
        env = os.environ.get("CLAUDE_PROJECT_DIR", "")
        project = L.find_project(env) if env else None
    if project is None:
        return False
    for _slug, st in L.iter_missions(project):
        if st.get("status") == "framing" and st.get("framing_session_id") == sid:
            return True
        if st.get("status") == "executing" and st.get("exec_session_id") == sid:
            return True
    return False


def body():
    data = L.read_stdin_json()
    prompt = data.get("prompt")
    if not isinstance(prompt, str):
        return
    score, labels, why, lang = score_prompt(prompt)
    if why is not None or score < THRESHOLD:
        return
    sid = data.get("session_id")
    now = time.time()
    if in_cooldown(sid, now):
        return
    if framing_in_progress(data.get("cwd") or os.getcwd(), sid):
        return
    set_cooldown(sid, now)
    L.emit(suggestion_line(score, labels, lang) + long_conversation_note(data.get("transcript_path"), lang))
    L.log("hook_suggest", "suggested score=%d labels=%s" % (score, ",".join(labels)))


def main():
    return L.run_hook("hook_suggest", body, __doc__)


if __name__ == "__main__":
    sys.exit(main())
