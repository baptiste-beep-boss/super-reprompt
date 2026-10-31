# -*- coding: utf-8 -*-
"""Correction 2: long-conversation warning from the transcript file SIZE only."""
import builtins
import io
import json
import os
import unittest
from unittest import mock

from _t import TmpCase

import hook_suggest as HS  # noqa: E402


def make_file(path, size):
    with open(path, "wb") as f:
        if size:
            f.seek(size - 1)
            f.write(b"\0")


class Estimate(TmpCase):
    def test_sizes_and_thresholds(self):
        cases = [(0, ""), (500 * 1024, ""), (1024 * 1024, "already long"), (3 * 1024 * 1024, "strongly")]
        for size, expect in cases:
            p = os.path.join(self.tmp, "t%d.jsonl" % size)
            make_file(p, size)
            note = HS.long_conversation_note(p, "en")
            if expect:
                self.assertIn(expect, note, size)
                self.assertIn("/clear", note)
                self.assertIn(" k tokens estimated", note)
            else:
                self.assertEqual(note, "", size)
        p = os.path.join(self.tmp, "mid")
        make_file(p, 1024 * 1024)
        self.assertNotIn("strongly", HS.long_conversation_note(p, "en"))

    def test_absent_invalid_and_odd_paths_are_silent(self):
        for bad in (None, "", "   ", os.path.join(self.tmp, "nope.jsonl"), 5, ["x"], "\0bad", self.tmp):
            self.assertEqual(HS.long_conversation_note(bad, "en"), "", repr(bad))

    def test_french_wording(self):
        p = os.path.join(self.tmp, "big")
        make_file(p, 3 * 1024 * 1024)
        note = HS.long_conversation_note(p, "fr")
        self.assertIn("Conversation déjà longue", note)
        self.assertIn("fortement", note)

    def test_content_is_never_opened(self):
        p = os.path.join(self.tmp, "guard.jsonl")
        make_file(p, 2 * 1024 * 1024)
        real_open = builtins.open
        real_io_open = io.open
        target = os.path.abspath(p)

        def guard(real):
            def inner(file, *a, **k):
                if isinstance(file, (str, bytes, os.PathLike)) and os.path.abspath(os.fsdecode(file)) == target:
                    raise AssertionError("open() called on the transcript path")
                return real(file, *a, **k)
            return inner

        with mock.patch.object(builtins, "open", guard(real_open)), mock.patch.object(io, "open", guard(real_io_open)):
            note = HS.long_conversation_note(p, "en")
        self.assertIn("already long", note)

    def test_constants_are_named(self):
        self.assertEqual((HS.LONG_CONV_TOKENS, HS.VERY_LONG_CONV_TOKENS, HS.BYTES_PER_TOKEN), (60000, 150000, 16))


class HookEndToEnd(TmpCase):
    BIG = "I want you to do a comprehensive audit of our codebase, analyze the architecture, and write a report with prioritized risks."

    def call(self, prompt, transcript, sid="s-long"):
        payload = json.dumps({"session_id": sid, "cwd": self.project, "hook_event_name": "UserPromptSubmit",
                              "prompt": prompt, "transcript_path": transcript})
        return self.run_script("hook_suggest.py", stdin=payload)

    def test_warning_is_appended_on_the_same_line(self):
        p = os.path.join(self.tmp, "t.jsonl")
        make_file(p, 3 * 1024 * 1024)
        rc, out, _e = self.call(self.BIG, p)
        self.assertEqual(rc, 0)
        self.assertEqual(len(out.strip().splitlines()), 1)
        self.assertIn("strongly", out)
        self.assertIn("/super-reprompt:super-reprompt", out)

    def test_ordinary_prompt_stays_silent_whatever_the_size(self):
        p = os.path.join(self.tmp, "t.jsonl")
        make_file(p, 5 * 1024 * 1024)
        rc, out, _e = self.call("Rename the variable foo to bar in utils.py, please, nothing else.", p)
        self.assertEqual((rc, out), (0, ""))

    def test_small_or_missing_transcript_gives_the_plain_line(self):
        for tp in (os.path.join(self.tmp, "missing.jsonl"), "", None):
            rc, out, err = self.call(self.BIG, tp, sid="s-%s" % abs(hash(str(tp))))
            self.assertEqual(rc, 0)
            self.assertIn("/super-reprompt:super-reprompt", out)
            self.assertNotIn("tokens estimated", out)
            self.assertEqual(err, "")


if __name__ == "__main__":
    unittest.main()
