# -*- coding: utf-8 -*-
"""Validate a documentation library: every domain folder holds a manifest.csv that tells the truth about its files.

Usage:  validate_library.py <library-dir> [--max-files N] [--max-bytes N] [--notes DIR]
Exit:   0 = valid, 2 = invalid (each problem on stderr, naming the file and the row).

A library is a folder of domain folders (finance/, crypto/, ...). Each domain folder that holds files must hold a
manifest.csv whose header is exactly:

    file,url,date,sha256,licence,vault_note

One row per source. `file` is a path relative to the domain folder; it is empty for a source that was only linked,
not copied (licence `link-only`), in which case `sha256` is empty too. Fields must not contain a comma: the format
is deliberately comma-split, with no quoting, so that a manifest stays readable and diffable.

What is checked: the header and the field count; relative, non-personal paths (no drive letter, no leading slash,
no `~`, no `..`, no user-home segment); the file exists and its sha256 matches; the url is http(s); the date is
ISO 8601 (`YYYY-MM-DD`, or `YYYY-MM` when the source itself gives only a month) and not in the future; the licence
is one that allows a copy (or `link-only` with no file); a vault note is named; no file is listed twice; no file in
the folder is missing from the manifest; no secret-looking string; and the agreed caps on file count and total size.
With `--notes DIR`, every `vault_note` must match a `<name>.md` somewhere under DIR, so the manifest cannot point at
a note that was never written.
"""
import argparse
import hashlib
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402

COLUMNS = ["file", "url", "date", "sha256", "licence", "vault_note"]
MANIFEST = "manifest.csv"
DEFAULT_MAX_FILES = 40
DEFAULT_MAX_BYTES = 500 * 1000 * 1000          # 500 MB

# Licences that allow keeping a copy of the document, plus the marker for a source that was only linked.
COPY_LICENCES = ("public-domain", "cc0", "cc-by", "cc-by-sa", "cc-by-nd", "cc-by-nc", "open-access",
                 "oecd-licence", "eu-reuse", "etalab", "own-work")
LINK_ONLY = "link-only"

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
# A full day, or a month when the document itself is dated only by month (a report, a paper): a true month beats
# an invented day.
DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
URL_RE = re.compile(r"^https?://[^\s]+$")
# A path that points at somebody's machine rather than at the library.
PERSONAL_PATH = [
    (re.compile(r"^[A-Za-z]:[\\/]"), "a drive letter"),
    (re.compile(r"^[\\/]"), "an absolute path"),
    (re.compile(r"^~"), "a home shortcut"),
    (re.compile(r"(^|[\\/])\.\.($|[\\/])"), "a parent traversal"),
    (re.compile(r"(?i)(^|[\\/])(users|home|documents and settings)([\\/]|$)"), "a user-home segment"),
]


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def path_problem(value):
    for rx, label in PERSONAL_PATH:
        if rx.search(value):
            return label
    return None


def note_index(notes_dir):
    """Return the set of note names (file stems) under notes_dir, lowercased."""
    names = set()
    for dirpath, dirnames, filenames in os.walk(notes_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if fn.lower().endswith(".md"):
                names.add(fn[:-3].lower())
    return names


def check_row(errs, where, fields, domain_dir, seen, sizes, notes=None):
    row = dict(zip(COLUMNS, fields))
    name, url, date, digest, licence, note = (row[c].strip() for c in COLUMNS)

    if licence == LINK_ONLY:
        if name or digest:
            errs.append("%s: licence %s means nothing was copied, so file and sha256 must be empty" % (where, LINK_ONLY))
    elif licence not in COPY_LICENCES:
        errs.append("%s: licence=%r is invalid. Valid: %s, or %s for a source that was only linked"
                    % (where, licence, ", ".join(COPY_LICENCES), LINK_ONLY))

    if licence != LINK_ONLY:
        if not name:
            errs.append("%s: file is empty but the licence is not %s" % (where, LINK_ONLY))
        else:
            bad = path_problem(name)
            if bad:
                errs.append("%s: file=%r is not a library path (%s). Use a path relative to the domain folder"
                            % (where, name, bad))
            else:
                full = os.path.join(domain_dir, name.replace("/", os.sep))
                if not os.path.isfile(full):
                    errs.append("%s: file=%r is listed but does not exist" % (where, name))
                elif not SHA_RE.match(digest):
                    errs.append("%s: sha256=%r is not 64 lowercase hex digits" % (where, digest))
                else:
                    real = sha256_of(full)
                    if real != digest:
                        errs.append("%s: sha256 does not match %r (manifest %s..., file %s...)"
                                    % (where, name, digest[:12], real[:12]))
                    sizes.append(os.path.getsize(full))
                key = name.replace("\\", "/").lower()
                if key in seen:
                    errs.append("%s: file=%r is listed twice (first at %s)" % (where, name, seen[key]))
                else:
                    seen[key] = where

    if not URL_RE.match(url):
        errs.append("%s: url=%r must start with http:// or https://" % (where, url))
    if not DATE_RE.match(date):
        errs.append("%s: date=%r must be ISO 8601 (YYYY-MM-DD, or YYYY-MM if the source gives only a month)"
                    % (where, date))
    elif date > time.strftime("%Y-%m-%d")[:len(date)]:
        errs.append("%s: date=%r is in the future" % (where, date))
    if not note:
        errs.append("%s: vault_note is empty. Name the note that uses this source" % where)
    else:
        bad = path_problem(note)
        if bad:
            errs.append("%s: vault_note=%r looks like a personal path (%s). Name the note, not its location"
                        % (where, note, bad))
        elif notes is not None and note.lower() not in notes:
            errs.append("%s: vault_note=%r has no note of that name. Write the note or fix the name" % (where, note))


def check_domain(errs, domain_dir, rel, seen_all, sizes, notes=None):
    listed, files = {}, []
    for dirpath, dirnames, filenames in os.walk(domain_dir):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
        for fn in filenames:
            if fn == MANIFEST and dirpath == domain_dir:
                continue
            p = os.path.join(dirpath, fn)
            files.append(os.path.relpath(p, domain_dir).replace(os.sep, "/"))

    man = os.path.join(domain_dir, MANIFEST)
    if not os.path.isfile(man):
        if files:
            errs.append("%s: %s is missing, but the folder holds %d file(s)" % (rel, MANIFEST, len(files)))
        return
    with open(man, encoding="utf-8", errors="replace") as f:
        text = f.read()
    for rx, label in L.SECRET_PATTERNS:
        if rx.search(text):
            errs.append("%s/%s: looks like it contains a secret (%s). Remove it" % (rel, MANIFEST, label))

    lines = [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]
    if not lines:
        errs.append("%s/%s: the file is empty. The header line is required" % (rel, MANIFEST))
        return
    header = [c.strip() for c in lines[0].split(",")]
    if header != COLUMNS:
        errs.append("%s/%s: header must be exactly %r, got %r" % (rel, MANIFEST, ",".join(COLUMNS), lines[0].strip()))
        return
    for i, ln in enumerate(lines[1:], start=2):
        fields = ln.split(",")
        where = "%s/%s line %d" % (rel, MANIFEST, i)
        if len(fields) != len(COLUMNS):
            errs.append("%s: %d fields, expected %d. A field must not contain a comma"
                        % (where, len(fields), len(COLUMNS)))
            continue
        check_row(errs, where, fields, domain_dir, listed, sizes, notes)
    for fn in sorted(files):
        if fn.lower() not in listed:
            errs.append("%s: %s is in the folder but not in %s. Add a row or remove the file" % (rel, fn, MANIFEST))
    seen_all.update({"%s/%s" % (rel, k): v for k, v in listed.items()})


def main(argv=None):
    L.setup_stdio()
    ap = argparse.ArgumentParser(description="Validate a documentation library's manifests.")
    ap.add_argument("library", help="the library folder (holds one folder per domain)")
    ap.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES)
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    ap.add_argument("--notes", default=None,
                    help="folder of knowledge notes: every vault_note must match a <name>.md under it")
    a = ap.parse_args(argv)

    root = os.path.abspath(os.path.expanduser(a.library))
    if not os.path.isdir(root):
        sys.stderr.write("not a folder: %s\n" % a.library)
        return 2

    notes = None
    if a.notes:
        nd = os.path.abspath(os.path.expanduser(a.notes))
        if not os.path.isdir(nd):
            sys.stderr.write("not a folder: %s\n" % a.notes)
            return 2
        notes = note_index(nd)

    errs, seen_all, sizes = [], {}, []
    domains = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)) and not d.startswith("."))
    for d in domains:
        check_domain(errs, os.path.join(root, d), d, seen_all, sizes, notes)
    loose = [f for f in sorted(os.listdir(root)) if os.path.isfile(os.path.join(root, f)) and f != "README.md"]
    for f in loose:
        errs.append("%s: file at the library root. Put every document in a domain folder" % f)

    total = sum(sizes)
    if len(sizes) > a.max_files:
        errs.append("%d files, over the cap of %d. Raise --max-files on purpose or drop sources"
                    % (len(sizes), a.max_files))
    if total > a.max_bytes:
        errs.append("%d bytes, over the cap of %d. Raise --max-bytes on purpose or drop sources"
                    % (total, a.max_bytes))

    if errs:
        for e in errs:
            sys.stderr.write(e + "\n")
        sys.stderr.write("%d problem(s)\n" % len(errs))
        return 2
    print("valid: %d entries, %d file(s) (cap %d), %.1f MB (cap %d MB), %d domain(s)"
          % (len(seen_all), len(sizes), a.max_files, total / 1e6, a.max_bytes // 1000000, len(domains)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
