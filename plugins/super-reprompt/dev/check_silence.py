# -*- coding: utf-8 -*-
"""Check that a reply says nothing about the framing machinery (negative-control criterion).

Usage:  check_silence.py [FILE] [--max-lines N] [--list]
        (no FILE: the text is read from standard input)
Exit:   0 = silent (and within the line cap, if one is given)
        1 = a pattern was found, or the cap was exceeded (each hit named with its line)
        2 = usage error

Why a script and not a judge: on 2026-10-30 two blind judges read the same binary criterion in
opposite ways — one failed "Pas besoin de cadrage", the other called it a harmless aside. A binary
criterion must read the same way for every output, so it belongs in code. The judge keeps what needs
judgement (completeness, proportionality, fidelity).

The patterns are deliberately narrow: a criterion that fires on an innocent word ("entier" contains
"tier", "permission" contains "mission") is worse than no criterion, so every pattern is anchored on
word boundaries and tested against a list of innocent sentences.
"""
import argparse
import re
import sys
import unicodedata

# (label, pattern). Matched on text with accents stripped and lowercased, so "CADRAGÉ" still hits.
PATTERNS = [
    ("cadrage", r"\bcadrages?\b"),
    ("framing", r"\bframings?\b"),
    ("pass-through", r"\bpass[- ]through\b"),
    ("passe-plat", r"\bpasse[- ]plats?\b"),
    ("palier", r"\bpaliers?\b"),
    ("no framing needed", r"\bno framing (?:needed|required)\b"),
    ("ordre de mission", r"\bordres? de mission\b"),
    ("mission order", r"\bmission orders?\b"),
    ("nom du skill", r"\bsuper[- ]reprompt\b"),
    ("AskUserQuestion", r"\baskuserquestion\b"),
    ("cout en tokens", r"\b\d+(?:[.,]\d+)?\s*k?\s*tokens?\b"),
    ("classe de mission", r"\bmission\s*:\s*(?:code|document|research|recherche|data|decision|infra|other|autre)\b"),
]


def fold(text):
    """Lowercase and strip accents so a hit cannot hide behind an accent or a capital."""
    no_accent = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return no_accent.lower()


def hits(text):
    """Return [(label, line_number, matched_text)] for every pattern found."""
    found = []
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        folded = fold(line)
        for label, pat in PATTERNS:
            m = re.search(pat, folded)
            if m:
                found.append((label, n, m.group(0)))
    return found


def main(argv=None):
    # stdin too: a Windows console decodes it as cp1252 by default, which breaks an accented word
    # into bytes that no longer match the pattern (found by test_accents_and_case_do_not_hide_a_hit).
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Check a reply is silent about framing.")
    ap.add_argument("file", nargs="?", help="file to read; standard input when omitted")
    ap.add_argument("--max-lines", type=int, default=None,
                    help="also fail when the reply has more than N non-blank lines")
    ap.add_argument("--list", action="store_true", help="print the patterns and exit")
    a = ap.parse_args(argv)

    if a.list:
        for label, pat in PATTERNS:
            print("%-20s %s" % (label, pat))
        return 0

    if a.file:
        try:
            with open(a.file, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError as e:
            sys.stderr.write("cannot read %s: %s\n" % (a.file, e))
            return 2
    else:
        text = sys.stdin.read()

    problems = []
    for label, line, matched in hits(text):
        problems.append("line %d: %s (%r)" % (line, label, matched))
    if a.max_lines is not None:
        n = len([ln for ln in text.split("\n") if ln.strip()])
        if n > a.max_lines:
            problems.append("%d non-blank lines, over the cap of %d" % (n, a.max_lines))

    if problems:
        for p in problems:
            print(p)
        print("NOT silent: %d problem(s)" % len(problems))
        return 1
    print("silent: no framing pattern found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
