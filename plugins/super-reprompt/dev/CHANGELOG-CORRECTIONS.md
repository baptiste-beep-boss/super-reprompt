# Changelog of the 7 corrections (brief CORRECTIONS-V2)

Backup of the state before the corrections: `super-reprompt-v2.sauvegarde-avant-corrections\` (untouched). Baseline: 81 tests passing.

## 1. Quick tier reads only its budget — applied
- Files: new `skills/super-reprompt/references/quick.md`; `SKILL.md` (tier table row "Instructions to read", sentence before the phase table, "read each reference once"); a "Sections by tier" line added under the Contents line of `phases.md`, `interview.md`, `order-template.md`, `verification.md` (and, for consistency, `capabilities.md`, `models.md`, `launch.md`, `agents.md`); new `dev/measure_loading.py` and generated `dev/CHARGEMENT-PAR-PALIER.md`.
- What changed: quick follows one self-contained file (P1 to P7, at most 3 questions, compact order, ready, launch offer with `launch.py <slug>` and a one-line fallback); standard reads only named sections. The tables of contents were checked against the headings (they were exact; a test now guards it). No content was moved or deleted.
- Tests: `tests/test_budgets.py` (SKILL.md and quick.md sizes, self-containment of quick.md, measure script `--check`, Sections-by-tier lines, TOC accuracy, no "think hard", uppercase lines).
- Measured: SKILL.md 3 752 tokens, quick.md 1 474, quick total 5 226, standard (no agents) 16 865, max 22 894 (characters / 3.7).

## 2. Framing inside an already long conversation — applied
- Files: `scripts/hook_suggest.py` (constants `BYTES_PER_TOKEN`=16, `LONG_CONV_TOKENS`=60000, `VERY_LONG_CONV_TOKENS`=150000, marked "starting values, to be calibrated against /context readings"; functions `estimate_conversation_tokens`, `long_conversation_note`); `SKILL.md` P0 step 5 (one sentence); `README.md`.
- What changed: when a suggestion is emitted, the file size of `transcript_path` (`os.path.getsize` only) gives a warning appended to the same line (English or French); "strongly" from 150 k. Absent or invalid path: no warning, no error. Ordinary prompts stay silent whatever the size.
- Tests: `tests/test_long_conversation.py` (sizes 0, 500 KB, 1 MB, 3 MB; absent/invalid paths; French; end to end; `open()` on the transcript path raises in a guard test).

## 3. Conditional escalation — applied
- Files: `references/models.md` (step 5 now the default proposal for CODE with an executable test; source and non-guarantee stated; example line), `references/order-template.md` (schema, allowed values, section 9), `references/launch.md` (new section "Targeted relaunch", proposal only, one level), `scripts/validate_order.py` (`launch.escalation` check).
- Validation: `enabled: true` needs a non-empty `verification.commands`, `from`/`to` valid efforts with `to` higher, `max_relaunches` 1 or 2; errors name the fields and the valid values. Absent field = unchanged behaviour.
- Tests: `tests/test_corrections.py::Escalation` (valid state; no command; `max_relaunches` 5/0/-1/true/"2"; bad efforts; malformed object).

## 4. Class DATA — applied
- Files: `scripts/_lib.py` (`CLASSES`; `mission.py` and `validate_order.py` use it), `SKILL.md`, `references/order-template.md`, `references/verification.md` (new section "Class DATA", about 300 tokens, generic, plus TOC). `phases.md` and the examples contain no class list.
- Tests: `tests/test_corrections.py::ClassData` (validate accepts DATA, no command required, `mission.py init --class DATA`, unknown class lists DATA).

## 5. Critical failures and router error — applied (detection partial)
- Files: new `evals/README.md`, `evals/CRITICAL-FAILURES.md`; one line in `README.md`.
- Detection: failure 1 (check declared executed but not run) is not detectable by the Stop hook with its existing data (it cannot tell a command the model ran from one it only claims), so it is written as manual detection, with a transcript recipe; no hook change, contract unchanged. Failures 4 and 5 are partly covered (validator secret scan; refused verification commands). The router error metric and its fallback (class OTHER, tier quick) are defined.

## 6. Structured sub-agent report — applied
- Files: `references/agents.md` (Reporting back contract: status, findings, evidence, uncertainties, changed_files, recommended_next_step; 1 000-2 000 tokens; large results in a file; stated as a design proposal, not a Claude Code schema; framing-agent outputs aligned), `agents/reprompt-scout.md` (status, findings, evidence, uncertainties), `agents/reprompt-reviewer.md` (status, yes/no per criterion with evidence, findings, uncertainties). `agents/reprompt-reader.md` unchanged (four questions).
- Test: covered by the full suite; no dedicated test (text-only change).

## 7. Instruction contradictions in P1 — applied
- Files: `SKILL.md` (P1 summary, one clause), `references/phases.md` (P1 step 2, three sub-lines).
