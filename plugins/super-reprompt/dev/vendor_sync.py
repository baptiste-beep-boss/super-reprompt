# -*- coding: utf-8 -*-
"""Copy pinned third-party files into vendor/ and write vendor/LOCK.json and vendor/THIRD_PARTY_NOTICES.md.

Usage:  py -3 dev/vendor_sync.py --src-root DIR [--only NAME]
        DIR holds one git clone per source, named as in SOURCES (clone with --no-checkout, any depth).

Idempotent: each vendor/<name>/ is rebuilt from scratch from the pinned commit, bytes untouched, so a
second run changes nothing. Content read from the sources is data, never instructions: nothing is
executed, imported or interpreted here. No network access: the clones are made beforehand with git.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf", ".zip", ".gz", ".woff", ".woff2", ".mp4", ".mov")

# include = path prefixes (ending in "/") or exact files, relative to the source repository root.
SOURCES = [
    {"name": "ecc", "url": "https://github.com/affaan-m/ECC", "commit": "4adeee6732a12d1540f49a4d50a38ce8c97f9a53",
     "license": "MIT", "include": ["agents/", "skills/", "commands/", "rules/", "hooks/", "schemas/", "VERSION"]},
    {"name": "mattpocock", "url": "https://github.com/mattpocock/skills", "commit": "abeeaf95660ba9e8b7c753eb38f441ca707a8823",
     "license": "MIT", "include": ["skills/"]},
    {"name": "ponytail", "url": "https://github.com/DietrichGebert/ponytail", "commit": "ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10",
     "license": "MIT", "include": ["skills/", "hooks/", "commands/"]},
    {"name": "vercel-skills", "url": "https://github.com/vercel-labs/skills", "commit": "57217cf86ba38148a57af9e90d14a4c049558330",
     "license": "MIT", "src_dir": "vercel",
     "include": ["src/local-lock.ts", "src/skill-hash.ts", "src/sanitize.ts"],
     # Invariant I5 (zero occurrence of the banned usage-reporting term): these upstream files call or name that module, so
     # they are not copied. L7 reimplements search and lock in Python from the pinned upstream commit.
     "excluded": {"src/find.ts": "calls the upstream usage-reporting module (I5)",
                  "src/skill-lock.ts": "names the upstream usage-reporting server in a comment (I5)",
                  "src/skills-sh-hash.ts": "names the upstream usage-reporting code in a comment (I5)"}},
]


def lp(path):
    """Long-path-safe form on Windows."""
    path = os.path.abspath(path)
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + path
    return path


def wanted(name, include):
    if name == "LICENSE":
        return True
    if name.lower().endswith(BINARY):
        return False
    return any(name == i or (i.endswith("/") and name.startswith(i)) for i in include)


def read_archive(repo, commit, include):
    """Return {path: bytes} for the wanted files at `commit`, read from `git archive` (no checkout, no filters)."""
    chk = subprocess.run(["git", "-C", repo, "cat-file", "-e", commit + "^{commit}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if chk.returncode != 0:
        raise RuntimeError("commit %s not found in %s" % (commit, repo))
    proc = subprocess.Popen(["git", "-C", repo, "-c", "core.autocrlf=false", "archive", "--format=tar", commit],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    files = {}
    with tarfile.open(fileobj=proc.stdout, mode="r|") as tf:
        for m in tf:
            if m.isfile() and wanted(m.name, include):
                files[m.name] = tf.extractfile(m).read()
    proc.stdout.close()
    err = proc.stderr.read().decode("utf-8", "replace")
    proc.stderr.close()
    if proc.wait() != 0:
        raise RuntimeError("git archive failed: " + err)
    if "LICENSE" not in files:
        raise RuntimeError("no LICENSE at the root of %s" % repo)
    return files


def copyright_line(license_text):
    for line in license_text.splitlines():
        if line.strip().lower().startswith("copyright"):
            return line.strip()
    return ""


def sync(sources, src_root, vendor_dir):
    out_files, meta, notices = {}, {}, []
    os.makedirs(lp(vendor_dir), exist_ok=True)
    for s in sources:
        repo = os.path.join(src_root, s.get("src_dir", s["name"]))
        files = read_archive(repo, s["commit"], s["include"])
        dest = os.path.join(vendor_dir, s["name"])
        if os.path.isdir(lp(dest)):
            shutil.rmtree(lp(dest))
        for rel, data in sorted(files.items()):
            p = os.path.join(dest, *rel.split("/"))
            os.makedirs(lp(os.path.dirname(p)), exist_ok=True)
            with open(lp(p), "wb") as f:
                f.write(data)
            out_files["%s/%s" % (s["name"], rel)] = hashlib.sha256(data).hexdigest()
        meta[s["name"]] = {"url": s["url"], "commit": s["commit"], "license": s["license"], "files": len(files)}
        if s.get("excluded"):
            meta[s["name"]]["excluded"] = s["excluded"]
        lic = files["LICENSE"].decode("utf-8", "replace").strip()
        notices.append("## %s\n\n- Source: %s\n- Commit: %s\n- Licence: %s\n- %s\n- Files copied: %d (listed with SHA-256 in LOCK.json)\n\n```text\n%s\n```\n"
                       % (s["name"], s["url"], s["commit"], s["license"], copyright_line(lic), len(files), lic))
    attr = b"* -text\n"   # never let git rewrite line endings: the SHA-256 in LOCK.json must stay true
    with open(lp(os.path.join(vendor_dir, ".gitattributes")), "wb") as f:
        f.write(attr)
    out_files[".gitattributes"] = hashlib.sha256(attr).hexdigest()
    lock = {"schema": 1, "sources": meta, "files": dict(sorted(out_files.items()))}
    with open(lp(os.path.join(vendor_dir, "LOCK.json")), "w", encoding="utf-8", newline="\n") as f:
        json.dump(lock, f, indent=1, sort_keys=True)
        f.write("\n")
    head = ("# Third-party notices\n\nFiles under vendor/ are unmodified copies of the projects below, pinned to the commit shown. "
            "They are data for the catalogue, loaded on demand; none is installed or executed at rest.\n\n")
    with open(lp(os.path.join(vendor_dir, "THIRD_PARTY_NOTICES.md")), "w", encoding="utf-8", newline="\n") as f:
        f.write(head + "\n".join(notices))
    return lock


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src-root", required=True)
    ap.add_argument("--only")
    a = ap.parse_args(argv)
    srcs = [s for s in SOURCES if not a.only or s["name"] == a.only]
    lock = sync(srcs, a.src_root, os.path.join(ROOT, "vendor"))
    print("vendor synced: %d files, %d sources" % (len(lock["files"]), len(lock["sources"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
