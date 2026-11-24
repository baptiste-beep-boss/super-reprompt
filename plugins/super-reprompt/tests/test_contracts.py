# -*- coding: utf-8 -*-
"""Lot 1 V3.1 : contrats versionnes, ecriture atomique, journal d'evenements unique, statuts, recus, migration."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from _t import ROOT, SCRIPTS

import contracts as C

EX = os.path.join(ROOT, "schemas", "examples")


def _plan(**over):
    p = {"schema": 2, "slug": "demo", "source_order_hash": "a" * 64, "compiled_at": "2026-11-24T10:00:00Z",
         "tasks": [{"id": "T1", "title": "a", "status": "ready", "deps": [], "acceptance_criteria": ["exit 0"], "preuve": ["python", "-c", "0"]},
                   {"id": "T2", "title": "b", "status": "proposed", "deps": ["T1"], "acceptance_criteria": ["ok"], "preuve": ["python", "-c", "0"]}]}
    p.update(over)
    return p


class Atomic(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sr ctr é ")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_write_then_read_leaves_no_temp(self):
        p = os.path.join(self.d, "x.json")
        C.atomic_write_json(p, {"a": "é"})
        self.assertEqual(C.read_json(p), {"a": "é"})
        self.assertEqual(os.listdir(self.d), ["x.json"])

    def test_corrupt_file_raises_and_is_not_overwritten_by_checked_save(self):
        p = os.path.join(self.d, "PLAN.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write("{pas du json")
        with self.assertRaises(C.ContractError):
            C.read_json(p)
        with self.assertRaises(C.ContractError):
            C.save_checked(p, {"schema": 2, "tasks": "pas une liste"}, "plan")
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{pas du json")

    def test_invalid_object_never_replaces_a_valid_file(self):
        p = os.path.join(self.d, "PLAN.json")
        C.save_checked(p, _plan(), "plan")
        with self.assertRaises(C.ContractError):
            C.save_checked(p, _plan(tasks=[{"id": "T1"}, {"id": "T1"}]), "plan")
        self.assertEqual(C.read_json(p)["tasks"][0]["title"], "a")


class Schemas(unittest.TestCase):
    def test_every_example_matches_its_verdict(self):
        files = sorted(glob.glob(os.path.join(EX, "*", "*.json")))
        self.assertGreaterEqual(len(files), 10)
        kinds = set()
        for f in files:
            verdict, name = os.path.basename(os.path.dirname(f)), os.path.basename(f)
            kind = name.split("-")[0]
            kinds.add(kind)
            errs = C.validate(kind, C.read_json(f))
            if verdict == "valid":
                self.assertEqual(errs, [], f)
            else:
                self.assertTrue(errs, f)
        self.assertEqual(kinds, {"state", "plan", "seal", "event", "receipt"})

    def test_plan_dependency_errors(self):
        self.assertTrue(any("cycle" in e for e in C.validate("plan", _plan(tasks=[
            {"id": "T1", "status": "ready", "deps": ["T2"]}, {"id": "T2", "status": "ready", "deps": ["T1"]}]))))
        self.assertTrue(any("inconnue" in e for e in C.validate("plan", _plan(tasks=[{"id": "T1", "status": "ready", "deps": ["T9"]}]))))
        self.assertTrue(any("double" in e for e in C.validate("plan", _plan(tasks=[{"id": "T1"}, {"id": "T1"}]))))

    def test_strict_plan_needs_hash_and_criteria(self):
        p = _plan()
        del p["source_order_hash"]
        self.assertEqual(C.validate("plan", p), [])               # legacy plan tolerated
        self.assertTrue(C.validate("plan", p, strict=True))
        q = _plan()
        q["tasks"][0]["acceptance_criteria"] = []
        self.assertTrue(C.validate("plan", q, strict=True))

    def test_versions_are_declared(self):
        self.assertEqual(set(C.SCHEMA_VERSIONS), {"state", "plan", "seal", "event", "receipt"})
        self.assertTrue(C.validate("plan", _plan(schema=99)))


class Events(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sr-ev-")
        self.m = os.path.join(self.d, ".super-reprompt", "demo")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_emit_is_valid_and_deduplicated(self):
        e1 = C.emit(self.m, "task.done", "manager", {"task": "T1"}, dedup_key="T1:run1")
        e2 = C.emit(self.m, "task.done", "manager", {"task": "T1"}, dedup_key="T1:run1")
        self.assertIsNotNone(e1)
        self.assertIsNone(e2)
        evs = C.read_events(self.m)
        self.assertEqual(len(evs), 1)
        self.assertEqual(C.validate("event", evs[0]), [])
        self.assertEqual(evs[0]["mission_id"], "demo")
        self.assertTrue(evs[0]["timestamp"].endswith("Z"))

    def test_bad_event_type_or_actor_refused(self):
        with self.assertRaises(C.ContractError):
            C.emit(self.m, "Pas Bon", "manager")
        with self.assertRaises(C.ContractError):
            C.emit(self.m, "task.done", "martien")

    def test_concurrent_emitters_lose_nothing(self):
        code = "import sys;sys.path.insert(0,%r);import contracts as C;[C.emit(%r,'test.ping','system',{'i':i}) for i in range(5)]" % (SCRIPTS, self.m)
        ps = [subprocess.Popen([sys.executable, "-c", code]) for _ in range(6)]
        for p in ps:
            self.assertEqual(p.wait(timeout=120), 0)
        evs = C.read_events(self.m)
        self.assertEqual(len(evs), 30)
        self.assertEqual(len({e["event_id"] for e in evs}), 30)

    def test_torn_last_line_is_skipped_not_fatal(self):
        C.emit(self.m, "test.ping", "system")
        with open(os.path.join(self.m, "events.ndjson"), "a", encoding="utf-8") as f:
            f.write('{"event_id": "abc", "trunc')
        self.assertEqual(len(C.read_events(self.m)), 1)
        C.emit(self.m, "test.ping", "system")
        self.assertEqual(len(C.read_events(self.m)), 2)


class Status(unittest.TestCase):
    def test_happy_path_needs_a_receipt_for_done(self):
        t = {"id": "T1", "status": "proposed"}
        C.transition(t, "ready")
        C.transition(t, "running")
        C.transition(t, "review")
        with self.assertRaises(C.ContractError):
            C.transition(t, "done")
        r = C.make_receipt("T1", "run1", "session", "ok", summary="fait", evidence=["exit 0"])
        C.transition(t, "done", receipt=r)
        self.assertEqual(t["status"], "done")
        self.assertEqual(t["receipt"], "run1")

    def test_failed_receipt_cannot_close(self):
        t = {"id": "T1", "status": "review"}
        with self.assertRaises(C.ContractError):
            C.transition(t, "done", receipt=C.make_receipt("T1", "r", "session", "failed", evidence=["x"]))

    def test_illegal_transitions_refused(self):
        for a, b in (("done", "running"), ("proposed", "done"), ("cancelled", "ready")):
            with self.assertRaises(C.ContractError):
                C.transition({"id": "T", "status": a}, b)

    def test_retry_counts_attempts(self):
        t = {"id": "T1", "status": "failed", "attempt": 1}
        C.transition(t, "ready", retry=True)
        self.assertEqual(t["attempt"], 2)
        self.assertEqual(t["status"], "ready")

    def test_legacy_statuses_normalized(self):
        self.assertEqual(C.normalize_status("todo"), "ready")
        self.assertEqual(C.normalize_status("echec"), "failed")
        self.assertEqual(C.normalize_status("done"), "done")


class Receipts(unittest.TestCase):
    def test_unknown_fields_are_null_never_invented(self):
        r = C.make_receipt("T1", "run1", "specialiste", "ok", evidence=["e"])
        self.assertIsNone(r["tokens_input"])
        self.assertIsNone(r["cost_actual"])
        self.assertEqual(r["currency"], None)
        self.assertEqual(C.validate("receipt", r), [])

    def test_save_receipt_atomic_and_unique(self):
        d = tempfile.mkdtemp(prefix="sr-rc-")
        try:
            r = C.make_receipt("T1", "run1", "session", "ok", evidence=["e"])
            p = C.save_receipt(d, r)
            self.assertTrue(p.endswith(os.path.join("receipts", "T1", "run1.json")))
            self.assertEqual(C.read_json(p)["run_id"], "run1")
            with self.assertRaises(C.ContractError):
                C.save_receipt(d, dict(r, summary="autre"))          # same run, different content: refused
            self.assertEqual(C.save_receipt(d, r), p)               # same content: idempotent
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Migration(unittest.TestCase):
    def test_legacy_journal_migrated_on_copy_idempotently(self):
        d = tempfile.mkdtemp(prefix="sr-mig-")
        try:
            m = os.path.join(d, "demo")
            os.makedirs(m)
            legacy = ['{"ts":"2026-11-20T10:00:00Z","slug":"demo","kind":"decision","text":"choix A"}',
                      '{"t":"2026-11-20T10:01:00","ev":"deny","rule":"F01","msg":"rm -rf /"}',
                      'ligne illisible',
                      '{"ts":"2026-11-20T10:02:00Z","slug":"demo","kind":"tache","text":"T1 done"}']
            with open(os.path.join(m, "journal.ndjson"), "w", encoding="utf-8") as f:
                f.write("\n".join(legacy) + "\n")
            before = open(os.path.join(m, "journal.ndjson"), encoding="utf-8").read()
            rep = C.migrate_journal(m)
            self.assertEqual((rep["migrated"], rep["skipped"]), (3, 1))
            rep2 = C.migrate_journal(m)
            self.assertEqual(rep2["migrated"], 0)
            evs = C.read_events(m)
            self.assertEqual([e["event_type"] for e in evs], ["log.decision", "guard.deny", "log.tache"])
            self.assertTrue(all(e["payload"].get("legacy") for e in evs))
            self.assertEqual(open(os.path.join(m, "journal.ndjson"), encoding="utf-8").read(), before)
            self.assertEqual(evs[1]["timestamp"], "2026-11-20T10:01:00Z")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_cli_validate_and_migrate(self):
        f = sorted(glob.glob(os.path.join(EX, "invalid", "plan-*.json")))[0]
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "contracts.py"), "validate", "plan", f], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        g = sorted(glob.glob(os.path.join(EX, "valid", "plan-*.json")))[0]
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "contracts.py"), "validate", "plan", g], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Wiring(unittest.TestCase):
    """The unique journal is really fed: the firewall hook and vault.py log both write events.ndjson."""

    def test_guard_journal_writes_unified_event(self):
        import guard_core
        d = tempfile.mkdtemp(prefix="sr-gj-")
        try:
            m = os.path.join(d, "demo")
            os.makedirs(m)
            old = guard_core.DEF.get("mdir")
            guard_core.DEF["mdir"] = m
            try:
                guard_core.journal("deny", "F01", 'rm "x"\n')
            finally:
                guard_core.DEF["mdir"] = old
            evs = C.read_events(m)
            self.assertEqual(len(evs), 1)
            self.assertEqual(C.validate("event", evs[0]), [])
            self.assertEqual((evs[0]["event_type"], evs[0]["payload"]["rule"]), ("guard.deny", "F01"))
            self.assertFalse(os.path.exists(os.path.join(m, "journal.ndjson")))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
