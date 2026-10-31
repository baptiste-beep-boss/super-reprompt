# Model and effort (P4, P7)

Verified as of 2026-10-23. Models and defaults change quickly: treat every row as a starting hypothesis and re-audit at each new model or Claude Code version.

Contents: [Principles](#principles) · [Starting table](#starting-table) · [Facts to respect](#facts-to-respect) · [Choosing for an order](#choosing-for-an-order) · [What the owner must re-verify](#what-the-owner-must-re-verify) · [Canonical examples](#canonical-examples)

Sections by tier — standard: Principles · Starting table · Facts to respect · Choosing for an order. Max: all sections. Quick: not read.

## Principles

- **Effort before model.** To get more depth, raise effort one step on the same model; change model only when effort no longer helps or the task is mechanical enough for a smaller one. One step at a time, then compare.
- **Cost per accomplished task, not per token.** A stronger model at lower effort can cost less per success than a weaker one at high effort. Judge on a sample.
- **Levels are not equivalent across models.** The same word (`high`) means different effort on different models; never carry a level from one model to another.
- **Set at launch, never mid-run.** Model and effort go on the launch command. Switching model in the middle of a session loses the cache and changes behavior. Check the real values on arrival (`/status`) and report any difference.
- **No `model:` in this skill's own frontmatter.** The framing session uses whatever model the user runs.
- **One model per session.** "Cheaper tiers" exist only as sub-agents launched with an explicit `model`.

## Starting table

Defaults in Claude Code at the date above: Opus 5.5, Sonnet 5.5 and Haiku 5.5 start at `medium`; Fable 5.1 starts at `high`.

| Execution task | Model | Effort | Guardrail |
|---|---|---|---|
| Mechanical or high volume (extraction, reformatting) with a discriminating check | Haiku 5.5 | medium (low only if the check is reliable) | escalate by hand if the check fails twice |
| Well-specified implementation, tests | Sonnet 5.5 | medium | explicit scope; anti-expansion clause |
| Long agentic work, harder analysis, structured writing, final drafting | Opus 5.5 | medium, then high | anti-expansion clause |
| Judgment, security, irreversible actions | Opus 5.5 | high; `xhigh` or `max` only after a measured gain | scope clause and a turn ceiling |
| Fable 5.1 | only if the plan includes it and the user consents (usage credits may apply) | high | fresh-context verifier |

## Facts to respect

- Sonnet 5.5 at `max` effort can launch multi-agent reviews of its own; keep it at `high` or below unless the order wants that and the cost is announced.
- Opus 5.5 does not cut its reasoning short on easy steps; extra "think again" lines are not needed and tend to cause over-checking.
- A plan without Opus (free offering with Haiku and Sonnet) needs a named fallback in section 9: say which model runs instead and what that changes.
- Print mode and background runs on a model billed from usage credits are billed without a prompt; the order's cost section says so.
- Changing effort mid-run changes quality; assume a cold cache after any change of model or effort, and verify with `/usage`.

## Choosing for an order

1. Classify each execution task with the table; start with the cheapest row that fits and has a discriminating check.
2. For each task that is not on the session model, name the sub-agent with an explicit `model` and `effort`.
3. Write one line of reason per choice in section 9: "Sonnet 5.5 / medium: implementation with a failing test to pass; the check is discriminating."
4. Write the launch values into `STATE.json` `launch` (`model`, `effort`, `permission_mode`).
5. Conditional escalation, proposed by default for class CODE when `verification.commands` holds an executable test (any other class: only when the check is reliable). First pass one step below the effort of the table, run the verification, then relaunch only the failing criteria at the table's effort, at most 1 relaunch (2 only if the user asks). Record it in `launch.escalation` and present it in section 9 as a proposal the user may refuse. Source: Anthropic's "Optimizing for cost and intelligence" guide reports about 40 percent lower cost than running everything at high, at the same pass rate; that is an internal measurement, not a guarantee, and it needs a reliable check. Without such a check, propose no escalation.

## What the owner must re-verify

The skill's author could not confirm these from the documentation at the date above. Re-check before relying on them, and update the date when done:

- the effort defaults per model and the effort levels each model accepts (`claude --help`, `/model`);
- whether Opus 5.5 over-verifies like Opus 5 when told to check its work;
- which models the user's plan can launch, and the fallback when one is missing;
- whether `effort` can be set in a skill's frontmatter and honored;
- the billing of Fable models on the user's plan;
- model aliases accepted by `--model` (`sonnet`, `opus`, `haiku`, or full ids) on the installed version.

Re-audit triggers: a new model release, a Claude Code major update, a result of a quality measurement that contradicts the table.

## Canonical examples

**Section 9 line (code):** "Launch: Sonnet 5.5, effort medium. Reason: a specified change with a failing test to turn green; the check is the test suite. Escalation: if the same test fails twice, stop and report instead of raising effort."

**Section 9 line (decision):** "Launch: Opus 5.5, effort high. Reason: an irreversible choice with trade-offs; depth matters more than speed. Not xhigh: no measurement shows a gain. Turn ceiling 40."

**Escalation line (code):** "Escalation proposed: first pass at low, `pytest -q` decides, only failing criteria relaunch at medium (1 relaunch at most). You may refuse; then the run stays at medium."

**Fallback line:** "If Opus is not available on this plan, run on Sonnet 5.5 at high and expect a thinner counter-argument section; the reviewer step stays."
