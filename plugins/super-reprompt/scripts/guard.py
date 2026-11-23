# -*- coding: utf-8 -*-
"""guard.py: the Vigie of super-reprompt (lot L4, spec section 10).  Standard library only, NO network (I2).

Hook mode (PreToolUse, JSON on stdin):  py -3 -I -S guard.py
  Hot path = no `json`, no `re` (their import costs ~70 ms, PREUVES.md proof 4).  JSON is read with the C scanner `_json`.
  Level 1: parse, find the sealed mission, let harmless tools through, path rules for file tools.
  Level 2: only Bash / Write / Edit that level 1 cannot clear: command tokenizer (pure str), then `re` loaded lazily
  and only when a content trigger (secret prefix, `except`, `skip`, test summary...) is present.
  Outside a sealed mission the hook is silent and exits 0 BEFORE reading stdin (I7).  Inside one it fails CLOSED:
  any corrupted input or internal error exits 2.  Exit 2 + a stderr line = block.

Commands (full Python, not on the hot path):
  seal    --project P --slug S [...]   freeze order, criteria, perimeter, sealed tests, hosts, colour, budget -> SCELLE.json
  drift   [--project P] [--slug S]     layer 2: files without requirement, requirement without task, weakened criteria, budget
                                       exit 0 clean | 3 fix it (first time) | 4 ask the owner (same finding a 2nd time)
  post    [--project P] [--slug S]     after-the-fact git comparison: catches indirect writes the hook cannot parse (detection, not blocking)
  close   [--project P] [--slug S]     end of mission: the hook becomes silent again
  avenant ...                          signed by the owner in their own terminal: the hook refuses it when Claude runs it

A hook is not a sandbox: commands can hide writes (a script that writes elsewhere, obfuscation).  What the hook cannot parse,
`post` detects by comparing git state to the seal.  Every denial is appended to journal.ndjson.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # -I removes the script directory from sys.path
import guard_core  # noqa: E402  (bytecode is cached, the stub stays tiny)

if __name__ == "__main__":
    guard_core.main()
