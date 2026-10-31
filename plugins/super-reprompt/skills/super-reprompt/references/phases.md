# Phases P0 to P7 — detail

Contents: [How to use](#how-to-use) · [P0 gate](#p0-gate) · [P1 discovery](#p1-discovery) · [P2 interview](#p2-interview) · [P3 specification](#p3-specification) · [P4 criteria-verification-capabilities](#p4-criteria-verification-capabilities) · [P5 adversarial review](#p5-adversarial-review) · [P6 dry run (experimental)](#p6-dry-run-experimental) · [P7 assembly-launch](#p7-assembly-launch) · [Budgets by tier](#budgets-by-tier) · [State and recovery](#state-and-recovery) · [Hypotheses to retest](#hypotheses-to-retest)

Sections by tier — standard: How to use · P1 discovery · P2 interview · P3 specification · P4 criteria-verification-capabilities · P5 adversarial review · P7 assembly-launch · State and recovery. Max: all sections. Quick: not read.

## How to use

Read this file on entering a phase and again after any compaction: find the current phase in `.super-reprompt/<slug>/STATE.json` (field `status`, plus the last `spent_est_k`), then read that phase's section only. Every phase lists its inputs, outputs and budget; the hypothesis each phase assumes about the model is under "Hypotheses to retest", so a phase can be removed when a measurement shows the model no longer needs it. All figures are starting values.

## P0 gate

Detail lives in SKILL.md. Output: `STATE.lang`, `STATE.level`, `STATE.class`, `STATE.tier`, a created mission folder, and the user's explicit choice.

- Budget: 1-1.5 k (quick), 1.5-2 k (standard), 3 k (max).
- The announcement and the four-option tier question are in SKILL.md P0 step 5; "direct" behaves like a waiver (tier quick, assumptions first).

## P1 discovery

Goal: never ask what the environment already answers.

1. **Conversation.** List what the user already said: deliverable, audience, constraints, examples, names. These fill answers before any question.
2. **Project files.** With `Glob` and `Read`, look for README, the package or build manifest (`package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod` and similar), the test command, `CLAUDE.md`, a `.git` directory. Read the first 60 lines of each at most. Git cleanliness needs `git status --short`, which may prompt for permission; if refused, ask in P2. Note detected defaults (language, test tool, project language) as assumptions with their source.
   - Any non-text piece received during framing (image, PDF, screenshot) is transcribed or copied into a file under `.super-reprompt/<slug>/` and referenced in the order, because a compaction summary loses it.
   - Duplicates or contradictions in `CLAUDE.md` and project rules that touch the request (for example two opposite rules on output format): one line among the assumptions, a question only if it changes the deliverable; never modify those files.
3. **Capabilities.** Run `scan_capabilities.py --project <dir> --max-tokens 1500`. It lists skills, agents, MCP servers, hooks and the profile with a fingerprint. Complete it with what the session shows: skills named in the session listing, MCP servers marked "needs authentication" or "failed" (those are prerequisites to clear, never capabilities).
   - Fallback without a script: `Glob` for `~/.claude/skills/*/SKILL.md`, `<project>/.claude/skills/*/SKILL.md`, `<project>/.claude/agents/*.md`, `~/.claude/agents/*.md`, `<project>/.mcp.json`; `Read` the first 15 lines of each (the frontmatter) with `limit`. Never read whole files.
4. **Profile.** If the scan reports a profile, `Read` it (cap 1,000 tokens). Use `lang`, `default_tier` (as a recommendation that still needs the user's click), `forbidden_capabilities` (remove them from every plan), `routing` (trigger, capability, phase triples to feed P4), `domain_defaults` (extra hidden-fact questions for P2), `doctrines` (copy the relevant lines into the order's section 3 or 9), `post_mission` (copy into section 11). The project profile overrides the personal one. Read `experimental` from it if present.
5. **Project scout (max only).** Launch `super-reprompt:reprompt-scout` (read-only) with the folder and the question "what does this project contain that affects the mission?". Its report is capped at 2 k tokens. Skip it for small folders.

- Outputs: a list of prefilled answers with sources, a candidate capability shortlist, prerequisites, assumptions.
- Budget: 0.5-1 k (quick), 3-4 k (standard), 9 k (max).

## P2 interview

Load the interview reference first (SKILL.md says when). Output: answered or defaulted questions, a list of `requirements` candidates (with `kind`), the unattended answer, written assumptions.

- Budget: 1-2 k (quick), 5-8 k (standard), 15 k (max).

## P3 specification

Load the order-template reference (its sections 1 to 4 and 8). Assemble a single self-contained message.

1. Intent sentence in the form "I'm working on <larger task> for <who>. They need <what the output enables>."
2. Scope in and out, as lists. Prohibitions and permissions: anything the executor would choose alone and that deletes, publishes, spends, pushes, touches the network for writing, or uses credentials is not authorized unless the order says so.
3. Requirements, sorted: unguessable (always written), guessable (written only if they matter), irrelevant (dropped). Keep at most 10 major ones; move the rest into acceptance criteria. Write each as one testable sentence.
4. A delivery clause: "Deliver what was asked, at the scope intended. Mention extra ideas at the end instead of doing them."
5. The executor never talks to the user: every question that can still arise is answered now or written as an assumption with its default.

- Budget: 1.5-2.5 k (quick), 4-5 k (standard), 9 k (max).

## P4 criteria-verification-capabilities

Load the verification reference; add the capabilities, agents and models references as SKILL.md says.

Order of work: criteria first (they drive everything), then the verification commands and plan B, then capabilities (only those a criterion or a requirement needs), then agents (only if all four conditions hold), then model and effort, then permissions and launch settings. Draft `ORDRE.md` and `STATE.json` at the end of P4 so the reviewer reads files, not memory.

- Budget: 1-1.5 k (quick), 4-6 k (standard), 11 k (max).

## P5 adversarial review

Skipped in quick. Checkpoint first (see SKILL.md, cost control). Launch `super-reprompt:reprompt-reviewer` with the path of `ORDRE.md`, the path of `STATE.json` and nothing else; its contract is in the agents reference. Read its answer, apply every finding about a contradiction, an undecidable criterion, a missing requirement or a capability without a call, and record rejected findings with one line of reason in `NOTES.md`. One pass; a second pass only if the first changed the criteria. In max, add to the same brief the pre-mortem question: "Suppose the mission failed; which three causes would be the likeliest, given only this order?" Fold useful answers into section 8 (assumptions) or 6 (verification).

- Budget: 5-8 k (standard), 14 k (max).

## P6 dry run (experimental)

Runs only when `experimental: on`, tier is max, and a reduced trial is representative (code, decomposable analysis). Otherwise skip it and spend its budget on P1, P2 and P5.

1. Checkpoint with the user (cost 15-20 k).
2. Pick one or two small tasks from the order. Run them in a sub-agent started with the order only, limited to a few turns.
3. Compare the output with the criteria. Hand the gaps to a fresh sub-agent that proposes corrections in plain language.
4. Rewrite the order accordingly. At most two rounds, then stop.

- Budget: 18 k (max, conditional).
- Hypothesis (unproven): trial runs reveal order defects that review misses. Keep P6 only if a measurement shows a gain at the cost of three times the tokens; otherwise remove it.

## P7 assembly-launch

1. Write the final `ORDRE.md` (order-template reference) and `STATE.json`. Resolve `${CLAUDE_PLUGIN_ROOT}` into absolute script paths inside the order, because the executing session does not load this skill.
2. Run `validate_order.py <slug>`. On exit 2 fix the named field and rerun, three rounds at most; then show the remaining error to the user.
   - Fallback without a script: tick this list by hand and say the validator did not run. Every required capability has `call`, `proof`, `plan_b`; a CODE mission has at least one verification command with a plan B; every criterion has `source` and `proof` or `unsourced: true`; at most 10 requirements; `announced_k` at most `cap_k` at most 100; `lang` set; `permissions.deny` not empty; no secret-looking string; at most 2 capabilities per phase.
3. Max, optionally standard: launch `super-reprompt:reprompt-reader` with `ORDRE.md` only; it answers four questions (deliverable and criterion; first action and exact capability; ambiguities; one assumption it would have to make). Fix the order wherever its answers diverge from your intent.
4. Show the order in full, in the user's language. Ask for approval with `AskUserQuestion` (approve, change something, cancel). On approval run `mission.py ready <slug>`, which validates and moves `framing` to `ready` (without Python, set `"status": "ready"` by hand).
5. Load the launch reference, check the git safety net, and offer the launch. Stop after the offer or after the launch command ran.

- Budget: 1-1.5 k (quick), 3-4 k (standard), 9 k (max).

## Budgets by tier

| Phase | quick | standard | max |
|---|---|---|---|
| P0 gate | 1-1.5 k | 1.5-2 k | 3 k |
| P1 discovery | 0.5-1 k | 3-4 k | 9 k |
| P2 interview | 1-2 k | 5-8 k | 15 k |
| P3 specification | 1.5-2.5 k | 4-5 k | 9 k |
| P4 criteria-verification-capabilities | 1-1.5 k | 4-6 k | 11 k |
| P5 adversarial review | none | 5-8 k | 14 k |
| P6 dry run (experimental) | none | none | 18 k |
| P7 assembly-launch | 1-1.5 k | 3-4 k | 9 k |
| Reserve | 0.5 k | 2 k | 8 k |
| Total | about 7-10 k | about 28-40 k | about 96 k (cap 100 k) |

With `experimental: off`, move P6's 18 k to P1 (+6 k), P2 (+6 k) and P5 (+6 k) only if the user asks for max; the tier still ends under the cap.

## State and recovery

- `STATE.json` holds the machine state; `ORDRE.md` the human order; `NOTES.md` free notes. Update `STATE.json` at the end of every phase (`spent_est_k`, requirements, assumptions, capabilities as they are decided).
- After a compaction or a resume: read `STATE.json`, `NOTES.md`, the current draft of `ORDRE.md`, then continue at the recorded phase. Re-ask the user nothing that the files already answer.
- A mission abandoned by the user gets `"status": "aborted"`.

## Hypotheses to retest

At every new model or Claude Code version, remove one phase at a time and compare orders on the same missions; keep a change only if the mechanism it predicted shows in the traces. Candidates: the question ceilings (3, 8, 12), the 10-requirement cap, P5, P6, the hidden-fact question, closed-choice questions for novices, the reader test, the footer reminder.

Hypotheses by phase:

- P0: a model asked to frame everything over-frames small requests, so the pass-through test comes first.
- P1: users do not volunteer facts the project already contains, and models ask for them anyway; prefilling removes those questions.
- P2: current models under-ask (they find a minority of hidden preferences unprompted) and also over-ask on clear requests; a filtered, capped interview beats both.
- P3: a model follows one complete message better than requirements spread over turns, and follows a short sorted list better than an exhaustive one.
- P4: a model asked to verify its own work after the fact does not improve; criteria fixed in advance, an external source of truth and an executable check do.
- P5: a reviewer anchored on a checklist finds defects; a free "improve it" review does not.
- P7: an order written by someone with the whole conversation in mind is ambiguous to a reader without it; the reader test and the validator catch that.
