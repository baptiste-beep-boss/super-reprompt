# Changelog

Versions are measured against held-out cases that are frozen and hashed **before** the change they test.
The numbers, including the failures, are in [`plugins/super-reprompt/evals/RESULTS.md`](plugins/super-reprompt/evals/RESULTS.md).

## 2.5.0 — 2026-10-31

One lever, nothing else: a pass-through reply says nothing about the framing machinery.

- **Changed** the gate's pass-through instruction. It used to say to reply `"No framing needed: <what you
  will do>"`, which invited the model to name the machinery in order to deny it; both v2.4 runs on a factual
  question opened with "tier: none". It now says the reply "mentions only the thing asked and reads as if
  this skill were not installed". Written positively on purpose: the first draft listed the forbidden words
  and so made them salient — the same mistake, one level up.
- **Added** `dev/check_silence.py` (19 tests): the negative-control criterion as a script instead of a judge,
  after two blind judges read the same binary criterion in opposite ways. Narrow patterns, word boundaries,
  accents and case folded, with innocent sentences tested to stay silent.
- **Added** the frozen case `evals/heldout-h17.md` and a real fixture for it, replacing a case that named a
  file which did not exist.
- **Measured:** negative control 2/2 against v2.4's 0/2, confirmed twice (blind judge on H13, script on H17),
  no regression on the two guardrail cases. The overall bar is **not** reached: the skill's own "at most 3
  lines" rule is met by no version, and that is the next lever.

## 2.4.0 — 2026-10-30

- **Added** `agents/reprompt-researcher.md` and `skills/super-reprompt/references/research.md`: an optional
  documentation researcher, offered as one interview question with "no" as the default. Tools are
  `Read, Glob, Grep, WebSearch, WebFetch, Write` — no Bash. It inventories existing notes before searching,
  reads primary sources, cross-checks, dates and ranks every claim.
- **Added** `scripts/validate_library.py` (34 tests): a document library whose CSV manifest is verified —
  real hashes, licences that allow a copy, no path pointing at somebody's machine, caps on count and size,
  and an option that requires every cited note to exist.
- **Added** the two never-pass-through cases to the gate: sourced research, and a command that deletes,
  overwrites or publishes data others or production depend on.
- **Removed** the duplicated "Reminder" block and compressed real redundancy to stay under the instruction
  budget. The research reference is counted separately, only when the agent is offered.
- **Measured:** both targeted defects fixed, 2/2 against 0/2 on held-out cases in different domains. A new
  defect appeared on the negative control, which is what 2.5.0 addresses.

## 2.3.0 and earlier

Developed privately. 2.3.0 introduced the size cap on a `quick` order (−23 % length) and the first held-out
set; it measured a real gain on modest requests and a regression in completeness and testability, which the
later versions set out to fix. Not published.
