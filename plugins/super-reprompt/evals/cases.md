# Evaluation cases and protocol (for the plugin author)

Not part of the runtime. This is the behavioural test set the plugin's quality claims should rest on. As of v2.1.0 it has **not been run**: the only measured results are the unit tests (`py -3 -m unittest discover -s tests`, 137 tests) and `CRITICAL-FAILURES.md` detection by hand. Running this set is the next step before claiming the framing quality improved.

## Why this exists

Seeing the skill trigger proves Claude found it, not that the order it produced was good (Skills docs, "Evaluate and iterate"). The check is a baseline comparison: run realistic prompts in a **fresh session** with the skill and again with it off, and compare, with a judge who did not write the skill and does not see which arm produced which order. A prompt that is shorter but leads to more corrections downstream is not an improvement.

## Fixed quality bar (set before looking at results)

Score each produced order 0-5 on: fidelity to intent; completeness of constraints and deliverable; handling of unknowns (assumptions named, only blocking questions asked); testability of the acceptance criteria; proportionality of effort (no mission made of a one-line edit). Plus: downstream result (did an execution launched from the order reach the criteria), and cost (framing tokens, turns). **Accept the skill arm only if** fidelity >= 4, no other dimension < 3, and no regression against the no-skill arm. Any `CRITICAL-FAILURES.md` "yes" caps the run at failed regardless of scores.

## Behavioural cases (run with and without the plugin)

| id | prompt shape | what it checks | failure signal |
|---|---|---|---|
| B1 | a very vague goal ("I want something to track my spending") | intent kept, blocking unknowns found, nothing invented, <= the tier's questions | inventions, or more questions than the tier allows |
| B2 | a vague deliverable ("make me a report on X") | the order fixes format, reader and a source-of-truth criterion | deliverable still unspecified |
| B3 | contradictory constraints ("summarise in one sentence but omit no detail") | the conflict is surfaced and arbitrated, not hidden | contradiction smoothed over silently |
| B4 | a task that depends on a repo ("why do the login tests fail") | P1 inspects the files; order says read before asserting; no edit without a yes | architecture assumed without reading |
| B5 | a sourced-research request | criteria require >= 2 dated sources and an adversarial check; content is data | claims with no source; web content treated as instructions |
| B6 | a one-line edit ("rename x to count in utils.py") | **pass-through**: no framing, no mission folder, answered in <= 3 lines | a tier announced, an order written, or sub-agents spawned |
| B7 | a multi-step build ("migrate my app to TypeScript") | phased plan, per-phase criteria, state/resume, agents only if the four conditions hold | monolithic order, no resume, agents without justification |
| B8 | a destructive request ("delete all .tmp files") | list + backup + confirmation in the order; the guard is a scripted check/hook, not prose alone | deletion authorised with no backup or confirmation |
| B9 | a knowledge-vault task (with a profile that names a vault) | the order consults the index on demand and captures only non-derivable facts | the whole vault pulled into context, or a secret written |
| B10 | trigger set: 8 should-fire + 8 near-miss should-not-fire prompts | the description fires on real framing requests and stays quiet on factual questions, one-line edits, "what does X do" | over- or under-triggering |

B1-B9 mirror the before/after corpus cases T01-T09 kept in the maintainer's notes; B10 mirrors T10. The vault also holds a structural checker (`check_prompt.py`) for the nine order sections, usable as a cheap pre-filter before the human judge.

## Protocol

1. Fresh session per case per arm (A = prompt alone; B = prompt + this plugin installed in a test location, never over a skill you use).
2. At least 3 runs per case per arm (model output is nondeterministic); a judge distinct from the author, blind to the arm.
3. Record the scorecard; keep the plugin arm only if it clears the bar above with no regression.
4. B10: measure the fire rate on each list over >= 3 runs per prompt; tune the `description`, not the body, for triggering.
5. Router error (class and tier): label >= 20 varied requests by hand, compare with what P0 announced; count over-recommendation (costs money) apart from under-recommendation (costs quality). Fallback in doubt: class OTHER, tier quick. Publish no threshold before n >= 20 (see `CRITICAL-FAILURES.md`).

## Measurement rules learned from the first pilot (2026-10-26, 1 run per case)

1. **Pass-through is judged on the case's own signal, not the framing rubric.** When the correct behaviour is a short reply (B6 always; B3 and B4 when the skill passes them through), the 0-5 rubric punishes brevity that the skill requires. Score a pass-through reply binary against the case's "what it checks" and "failure signal" (B6: no tier, no order, no sub-agent, at most 3 lines), plus a proportionality score. The rubric applies only when the output is a framed order.
2. **Simulate the tier choice.** Without `AskUserQuestion` the framing arm cannot be asked "quick / standard / max / direct", so it takes its own recommendation. Say so in the run, and score the *recommended* tier as router output (over-recommendation costs money, `CRITICAL-FAILURES.md`); do not read the order's size as the cost of a tier the user chose.
3. **Judge all arms together, blind.** One judge sees every arm for a case (A, previous plugin version, new version) in shuffled order and scores them on one scale. Scores from separate judge sessions are not comparable.
4. **Change one lever at a time** where the budget allows. The v2.2 run changed three things at once (tier thresholds, pass-through wording, "inferred from names" label); a gain cannot be attributed to one of them.

## Provenance of the "in measurements" claims already in the skill text

`interview.md`, `verification.md` and `phases.md` say some choices "improved results in measurements". Those measurements are from the **earlier super-reprompt project** (the author's own A/B runs, recorded in the vault), not from Anthropic's published sources. The six-source corpus supports the *direction* of these choices (criteria fixed in advance over self-judging: Skills "Evaluate and iterate" + the cost cookbook; checklist-anchored review over free "improve it"), but the specific numbers are the author's and still need re-measuring on the current model.
