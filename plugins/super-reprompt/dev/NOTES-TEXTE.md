# NOTES-TEXTE (author of the skill text)

Written 2026-10-23. Scope: `skills/super-reprompt/` only.

## Deviations from CONTRAT.md or gaps the mechanics must cover
1. **`ready` transition.** `mission.py` has no subcommand that moves `framing -> ready`. The text tells the model to set `"status": "ready"` in STATE.json by hand after approval. Suggest adding `mission.py ready <slug>` (it could run the validator).
2. **Session id.** The execution protocol asks the executor to run `mission.py start <slug> --session-id <ID>`, with the id "recorded by the SessionStart hook", and to run without the flag if none is available. `launch.py`'s short prompt or the hook should tell the executor where the id lives; otherwise make `--session-id` optional in `start`.
3. **`experimental: on|off`.** Not in CONTRAT. The text reads it from the user's request or from the profile frontmatter key `experimental`. The profile reader (model, `Read`) sees it; `scan_capabilities.py` need not report it. It gates P6, the contrasting-drafts form for novices (S12) and the per-model variants (S35).
4. **allowed-tools.** Three `Bash(<launcher> ${CLAUDE_PLUGIN_ROOT}/scripts/*)` patterns (python3, py -3, python). Quoting a plugin root that contains spaces (the Windows home here has a folder with a space) was not tested; if the pattern fails to match, the scripts will prompt. Write and Edit are not pre-approved (brief), so writing ORDRE.md and STATE.json prompts in default permission mode.
5. **Agent names** are bare; `agents.md` says to verify whether the plugin namespace is needed in the Agent call. The order's `call` for agents uses `Agent(name)`.
6. **Model aliases and effort values** in `models.md` (`sonnet`, `opus`, `haiku`, `medium`, ...) are as the contract and docs state; not exercised.
7. `mission.py spent` is called by the model with an estimate (chars / 3.7); no tool measures real spending.

## Mechanisms not embodied as text (live in mechanics) and how the text refers to them
S4 hook_suggest (text: "when a hook suggestion invoked the skill ... stop after P0"), S7 hook_compact (text: "a hook may already have re-injected"), S18 validator (text + manual checklist), S20 scan (text + Glob/Read fallback), S22 Stop hook (text describes it as anchoring level 3), S23/S26 (agents.md covers the fields), S39 launch.py (text + three fallbacks). S46-S51 (evals) are outside the skill text by design. S3 baseline is on; S12 closed-choice drafts, S31 (P6) and S35 are behind the switch.

## Embodied (traceable)
S1 S2 S3 S5 S6 SKILL.md; S8 S9 S10 S11 S13 S19 interview.md + phases.md; S14 S15 order-template.md; S16 S17 S45 verification.md; S21 capabilities.md; S24 S25 S26 S27 S28 S29 S30 S32 agents.md; S33 S34 models.md; S35 S37 S39 S40 S41 S42 S44 launch.md; S36 SKILL.md "Cost control"; S43 execution protocol in order-template.md; S31 phases.md P6; S48 "Hypothesis" lines in phases.md.

## Starting values not settled by sources (revisable)
Question ceilings 3/8/12; 10-requirement cap; tier thresholds (E < 100 k, 100 k-1 M, > 1 M); phase budgets; 1.25x checkpoint; P6 usefulness and its 18 k; value of the reader test in standard; the closed-choice novice form; per-model instruction variants; concurrency ceilings in agents.md (20 / depth 1-2); auto-mode default statement in launch.md (to verify against current docs); worktree base behavior (to verify).

## Self-check
SKILL.md about 3,500 tokens (chars / 3.7). No fully uppercase line outside code (class names kept inside sentences). No personal terms, no "think hard", no request for written reasoning. References never name each other (one level); SKILL.md names each with a read condition.
