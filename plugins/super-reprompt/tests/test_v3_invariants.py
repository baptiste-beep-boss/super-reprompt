# -*- coding: utf-8 -*-
"""v3 invariants I1-I7 and the D2 ceilings (lot L1). Standard library only, no network.

I1 manifest declares nothing from vendor/ · I2 network only in net/ · I3 standard library only ·
I4 no key / personal path · I5 no telemetry · I6 every vendored file has a SHA-256 and a licence ·
I7 hooks silent outside a mission.
"""
import glob
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from _t import ROOT

VENDOR = os.path.join(ROOT, "vendor")
NET_RX = re.compile(r"(?m)^\s*(?:import|from)\s+(socket|urllib|http|requests|ftplib|smtplib|ssl|xmlrpc|asyncio|aiohttp|httpx)\b")
IMPORT_RX = re.compile(r"(?m)^\s*(?:import|from)\s+([A-Za-z_][A-Za-z0-9_]*)")


def own_py(*subdirs):
    """Python files written by us (never vendor/, never tests/)."""
    out = []
    for sd in subdirs:
        out += glob.glob(os.path.join(ROOT, sd, "**", "*.py"), recursive=True)
    return sorted(p for p in out if "__pycache__" not in p)


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def load_sync():
    spec = importlib.util.spec_from_file_location("vendor_sync", os.path.join(ROOT, "dev", "vendor_sync.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class D2Ceilings(unittest.TestCase):
    def test_ceilings_are_the_v3_values(self):
        spec = importlib.util.spec_from_file_location("ml", os.path.join(ROOT, "dev", "measure_loading.py"))
        ml = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ml)
        self.assertEqual(ml.LIMITS, {"SKILL.md": 4950, "quick.md": 2660, "quick": 8680, "standard": 23800})


class I1Manifest(unittest.TestCase):
    def test_manifest_declares_only_the_skill(self):
        text = read(os.path.join(ROOT, ".claude-plugin", "plugin.json"))
        self.assertNotIn("vendor", text)
        m = json.loads(text)
        decl = m.get("skills", [])
        decl = [decl] if isinstance(decl, str) else decl
        for d in decl:
            self.assertIn(d.replace("\\", "/").strip("./").rstrip("/"), ("skills", "skills/super-reprompt"))
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "skills"))), ["super-reprompt"])

    def test_nothing_in_vendor_sits_at_a_discovery_path(self):
        # Claude discovers skills/, agents/, commands/, hooks/ at the plugin root only.
        for d in ("skills", "agents", "commands"):
            for p in glob.glob(os.path.join(ROOT, d, "**", "*"), recursive=True):
                self.assertNotIn("vendor", p.replace("\\", "/").split("/" + d + "/")[-1])
        self.assertTrue(os.path.isdir(VENDOR))


class I2Network(unittest.TestCase):
    def test_net_dir_exists_and_is_the_only_place_for_network(self):
        self.assertTrue(os.path.isdir(os.path.join(ROOT, "net")))
        for p in own_py("scripts", "dev", "hooks"):
            self.assertIsNone(NET_RX.search(read(p)), os.path.relpath(p, ROOT))

    def test_net_may_use_urllib_and_nothing_heavier(self):
        banned = re.compile(r"(?m)^\s*(?:import|from)\s+(requests|aiohttp|httpx|ftplib|smtplib)\b")
        for p in own_py("net"):
            self.assertIsNone(banned.search(read(p)), os.path.relpath(p, ROOT))
        # the rule lets urllib through in net/ and catches it everywhere else
        self.assertIsNone(banned.search("import urllib.request\n"))
        self.assertIsNotNone(NET_RX.search("import urllib.request\n"))
        self.assertIsNotNone(banned.search("import requests\n"))

    def test_no_hook_command_reaches_net(self):
        with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
            h = json.load(f)
        self.assertNotIn("net/", json.dumps(h))
        for name in ("hook_suggest.py", "hook_compact.py", "hook_stop.py"):
            self.assertNotRegex(read(os.path.join(ROOT, "scripts", name)), r"\bnet\b\s*(import|\.)")


class I3Stdlib(unittest.TestCase):
    def test_python_is_standard_library_only(self):
        std = set(sys.stdlib_module_names)
        local = {os.path.splitext(os.path.basename(p))[0] for p in own_py("scripts", "net", "dev")} | {"_lib", "net"}
        for p in own_py("scripts", "net", "dev", "hooks"):
            for m in IMPORT_RX.finditer(read(p)):
                self.assertTrue(m.group(1) in std or m.group(1) in local, "%s imports %s" % (os.path.relpath(p, ROOT), m.group(1)))


class I4Secrets(unittest.TestCase):
    def test_no_key_or_personal_path_in_our_files(self):
        rx = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[bp]-[A-Za-z0-9-]{10,}|C:\\Users\\(?!me\\|you\\|user\\)|/home/(?!me/|you/|user/)[a-z]+/|-----BEGIN [A-Z ]*PRIVATE KEY)")
        hits = []
        for dirpath, dirnames, files in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git", "vendor", "tests")]
            for fn in files:
                p = os.path.join(dirpath, fn)
                if fn.endswith((".pyc", ".png")):
                    continue
                if rx.search(read(p)):
                    hits.append(os.path.relpath(p, ROOT))
        self.assertEqual(hits, [])


class I5NoTelemetry(unittest.TestCase):
    TEL = re.compile("tele" + "metry", re.I)

    def test_zero_occurrence_in_our_files(self):
        hits = []
        for dirpath, dirnames, files in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git", "vendor", "tests")]
            for fn in files:
                if fn.endswith(".pyc"):
                    continue
                p = os.path.join(dirpath, fn)
                if self.TEL.search(read(p)) or self.TEL.search(fn):
                    hits.append(os.path.relpath(p, ROOT))
        self.assertEqual(hits, [])

    def test_zero_occurrence_in_the_vercel_copy(self):
        v = os.path.join(VENDOR, "vercel-skills")
        self.assertTrue(os.path.isdir(v))
        for dirpath, _d, files in os.walk(v):
            for fn in files:
                p = os.path.join(dirpath, fn)
                self.assertIsNone(self.TEL.search(fn), p)
                self.assertIsNone(self.TEL.search(read(p)), p)


class I6Lock(unittest.TestCase):
    def lock(self):
        with open(os.path.join(VENDOR, "LOCK.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_every_file_has_its_sha256_and_nothing_extra(self):
        lock = self.lock()
        on_disk = {}
        for dirpath, _d, files in os.walk(VENDOR):
            for fn in files:
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, VENDOR).replace("\\", "/")
                if rel in ("LOCK.json", "THIRD_PARTY_NOTICES.md"):
                    continue
                with open(p, "rb") as f:
                    on_disk[rel] = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual(on_disk, lock["files"])
        self.assertGreater(len(on_disk), 100)

    def test_every_source_has_a_licence_commit_and_notice(self):
        lock = self.lock()
        notices = read(os.path.join(VENDOR, "THIRD_PARTY_NOTICES.md"))
        self.assertEqual(sorted(lock["sources"]), ["ecc", "mattpocock", "ponytail", "vercel-skills"])
        want = {"ecc": "4adeee6", "mattpocock": "abeeaf9", "ponytail": "ebd8654", "vercel-skills": "57217cf"}
        for name, s in lock["sources"].items():
            self.assertTrue(s["commit"].startswith(want[name]), name)
            self.assertEqual(len(s["commit"]), 40)
            self.assertEqual(s["license"], "MIT")
            lic = os.path.join(VENDOR, name, "LICENSE")
            self.assertTrue(os.path.isfile(lic), name)
            self.assertIn(s["commit"], notices)
            self.assertIn(s["url"], notices)
            self.assertIn(read(lic).strip(), notices)
            self.assertGreater(s["files"], 0)


class VendorSync(unittest.TestCase):
    """dev/vendor_sync.py on a throwaway git repository: idempotent, filtered, fails on a bad commit."""

    def make_repo(self, root):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        def g(*a):
            return subprocess.run(["git", "-c", "core.autocrlf=false", "-C", root] + list(a), env=env, check=True, stdout=subprocess.PIPE).stdout.decode().strip()
        os.makedirs(os.path.join(root, "skills", "a"))
        os.makedirs(os.path.join(root, "src"))
        for rel, data in (("skills/a/SKILL.md", b"---\nname: a\n---\r\nbody\n"), ("skills/a/pic.png", b"\x89PNG"),
                          ("src/find.ts", b"export {}\n"), ("src/other.ts", b"x\n"),
                          ("LICENSE", b"MIT License\n\nCopyright (c) 2026 Foo\n")):
            with open(os.path.join(root, rel), "wb") as f:
                f.write(data)
        g("init", "-q"); g("add", "-A"); g("commit", "-q", "-m", "c1")
        return g("rev-parse", "HEAD")

    def snapshot(self, d):
        out = {}
        for dp, _x, fs in os.walk(d):
            for fn in fs:
                with open(os.path.join(dp, fn), "rb") as f:
                    out[os.path.relpath(os.path.join(dp, fn), d)] = f.read()
        return out

    def test_idempotent_filtered_and_clean(self):
        vs = load_sync()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src_root", "demo")
            os.makedirs(src)
            sha = self.make_repo(src)
            sources = [{"name": "demo", "url": "https://example.invalid/demo", "commit": sha, "license": "MIT",
                        "include": ["skills/", "src/find.ts"]}]
            out = os.path.join(tmp, "vendor")
            lock1 = vs.sync(sources, os.path.join(tmp, "src_root"), out)
            snap1 = self.snapshot(out)
            self.assertIn(os.path.join("demo", "skills", "a", "SKILL.md"), snap1)
            self.assertEqual(snap1[os.path.join("demo", "skills", "a", "SKILL.md")], b"---\nname: a\n---\r\nbody\n")  # bytes exact
            self.assertIn(os.path.join("demo", "src", "find.ts"), snap1)
            self.assertNotIn(os.path.join("demo", "src", "other.ts"), snap1)       # not in include
            self.assertNotIn(os.path.join("demo", "skills", "a", "pic.png"), snap1)  # binary dropped
            self.assertIn(os.path.join("demo", "LICENSE"), snap1)
            with open(os.path.join(out, "demo", "stale.txt"), "w") as f:
                f.write("stale")
            lock2 = vs.sync(sources, os.path.join(tmp, "src_root"), out)
            self.assertEqual(self.snapshot(out), snap1)        # stale file removed, rest identical
            self.assertEqual(lock1, lock2)
            self.assertEqual(lock1["files"]["demo/skills/a/SKILL.md"], hashlib.sha256(b"---\nname: a\n---\r\nbody\n").hexdigest())

    def test_unknown_commit_fails(self):
        vs = load_sync()
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "src_root", "demo")
            os.makedirs(src)
            self.make_repo(src)
            bad = [{"name": "demo", "url": "u", "commit": "0" * 40, "license": "MIT", "include": ["skills/"]}]
            with self.assertRaises(RuntimeError):
                vs.sync(bad, os.path.join(tmp, "src_root"), os.path.join(tmp, "vendor"))


class I7Silence(unittest.TestCase):
    def test_hooks_are_silent_outside_a_mission(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, payload in (("hook_suggest.py", {"prompt": "fix typo in README"}),
                                  ("hook_compact.py", {"source": "resume"}),
                                  ("hook_stop.py", {"stop_hook_active": False})):
                p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", name)], input=json.dumps(dict(payload, cwd=tmp)).encode(),
                                   cwd=tmp, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
                self.assertEqual(p.returncode, 0, name)
                self.assertEqual(p.stdout.decode().strip(), "", name)


class GuardNote(unittest.TestCase):
    def test_guard_doc_records_the_l0_latency_lesson(self):
        text = read(os.path.join(ROOT, "scripts", "guard.py"))
        self.assertIn("-I -S", text)
        self.assertRegex(text, r"json.*re|re.*json")


if __name__ == "__main__":
    unittest.main()
