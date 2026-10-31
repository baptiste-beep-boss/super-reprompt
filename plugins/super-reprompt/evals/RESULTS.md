# Measured results

Everything below was measured on this plugin. Where a number is weak, this page says so. Where a bar was
not reached, this page says that too — including the current one.

**Honest summary.** Three defects found in earlier versions are fixed and the fix generalised to new,
held-out cases. One acceptance bar out of three was reached. Sample sizes are small (n = 2 or 3 per cell),
the judge is a model from the same family as the subjects, and no run compares this plugin against another
framing tool. **Do not read these numbers as a promise of better results for your project.** Read them as
evidence that the plugin's behaviour was checked at all, which is more than most prompting advice offers.

## How the measurements work

- **Held-out sets.** Each set of cases is written, dated, and its SHA-256 recorded **before** the skill is
  modified, and it is never edited after its first run. A fix therefore cannot be tuned against the cases
  that measure it. Correcting a defect opens a new cycle with new cases.
- **Arms.** A = no skill (the model alone), B = previous version, C = new version. Every arm gets the same
  neutralisation instruction, so a personal configuration file cannot favour one of them.
- **Blind judge.** One judge per case sees every arm's output for that case, shuffled and relabelled, and
  never learns which arm produced which. Scores from separate judge sessions are not comparable, so a case
  is always judged in one pass.
- **Binary criteria go to a script, not a judge.** `dev/check_silence.py` decides them identically for every
  output. This came out of a measured failure, described below.
- **Pass-through is judged on the case's own signal**, not on the framing rubric: a short reply that the case
  requires must not be punished for being short.

## Cycle 1 — v2.3, cases H1-H6 (2026-10-29)

Six new requests, 3 runs each, no skill vs v2.3, blind judge; 18 outputs per arm.

| Metric | No skill | v2.3 |
|---|---|---|
| Fidelity to intent | 4.17 | **4.44** |
| Proportionality of effort | 2.56 | **3.94** |
| Completeness | 4.28 | **3.78** |
| Testability | 4.22 | **3.28** |
| Case signal | 12/18 | **14/18** |
| Critical failures | 0 | 0 |

**Read it honestly:** a real gain on modest requests (a one-line edit got a ~300-character reply instead of
900-3,000), paid for by a **regression in completeness and testability**. Two causes, both reproducible:
a sourced-research request was answered directly 3/3 instead of being given criteria, and an irreversible
write to a production table skipped the rehearsal and the rollback plan. Verdict: **not installable**.

## Cycle 2 — v2.4, cases H7-H10 (2026-10-30)

New cases in different domains, plus two negative controls — cases where the skill must **not** fire.
Budget forced a reduction, declared here: 3 cases × 2 arms × 2 runs instead of 6 × 3 × 3, so H11, H12 and
the v2.3 arm were **not measured**.

| Case | No skill | v2.4 | Verdict |
|---|---|---|---|
| H7 sourced research (vaccination coverage) | 0/2 | **2/2** | defect fixed |
| H8 delete from a shared production database | 0/2 | **2/2** | defect fixed |
| H10 negative control (a factual git question) | **2/2** | 0/2 | **new defect** |

The two fixes generalised to domains the fix was not written against. But v2.4 answered the factual question
correctly **and opened with "tier: none"** — it named the framing machinery to say it did not apply. Without
a negative control in the set, this version would have been declared good. Verdict: **not installable**.

## Cycle 3 — v2.5, cases H13-H17 (2026-10-30 / 31)

One lever changed, nothing else: the pass-through reply must read as if the skill were not installed.

| Case | v2.4 | v2.5 | Verdict |
|---|---|---|---|
| H13 negative control (PostgreSQL index question) | 0/2 | **2/2** | lever works |
| H14 negative control (one-line edit) | 2/2 (judge) · 0/2 (literal) | 1/2 (judge) · 2/2 (literal) | **inconclusive** |
| H15 no-regression, sourced research (remote work) | 2/2 | **2/2** | no regression |
| H16 no-regression, publishing a public page | 2/2 | **2/2** | no regression |
| H17 negative control, rerun with a scripted criterion | silence 0/2 · format 0/2 | **silence 2/2** · format 0/2 | lever confirmed, bar missed |

On H13 the v2.5 replies were **735 and 757 characters** against **4,758 and 4,815** for v2.4, with equivalent
technical content. On H17, the script found the word "cadrage" (framing) on line 1 of both v2.4 outputs and
nothing in either v2.5 output — a verdict anyone can reproduce by running the script on the four files.

### Two metrology failures worth more than the scores

1. **Two judges, one shared criterion, opposite verdicts.** H14's criterion said "same criterion as H13".
   H13's judge failed the phrase "no framing needed"; H14's judge called the same phrase a harmless aside and
   passed it. A binary criterion read by two judges is not a criterion. Fix: `dev/check_silence.py`, 19 tests,
   including a list of innocent sentences that must stay silent ("entier" contains *tier*, "permission"
   contains *mission*).
2. **A case that names a file which does not exist** measures the reaction to a missing file. H14 named a
   path that was absent, so a legitimate "where is this file?" was scored as framing. Fix: H17 ships a real
   fixture whose line 14 is the line under test.

### Why the bar is still not reached

H17's signal combined silence **and** a cap of 3 lines, because the skill imposes "at most 3 lines" on itself.
All four outputs — both arms — exceeded it: 4, 4, 7 and 9 non-blank lines. The independent judge, who did not
see that criterion, scored the two 4-line v2.5 outputs **5/5 on proportionality**: "exactly the right format".
An edit that needs an extra import cannot be described in 3 lines without lying by omission. **The rule is
unrealistic, not the outputs** — and that is the next lever, for a new cycle with new cases. Taken as a block
the signal was 0/2 everywhere, which says nothing; decomposed, it says silence 2/2 against 0/2.

## Current status

| Claim | State |
|---|---|
| Sourced research is never answered without criteria | **fixed**, 2/2 vs 0/2 on a held-out case |
| A destructive write to shared or production data gets guardrails | **fixed**, 2/2 vs 0/2 on a held-out case |
| A factual question gets a plain answer, with no framing vocabulary | **fixed**, confirmed twice (judge, then script) |
| No regression on what already worked | **holds** on the two cases measured |
| The skill's own "at most 3 lines" rule | **not met by any version**; the rule is being reconsidered |
| Overall acceptance bar | **not reached** |
| Comparison against other framing tools or prompt packs | **never measured** |

## Costs, measured

A sub-agent costs **105-133 k tokens** as a floor (15 agents, 1.78 M tokens). The full evaluation plan for
cycle 2 (54 outputs plus judges) would have cost ~7 M tokens, three times the quota available, which is why
it was reduced and why the reduction is declared instead of hidden. Cycle 3 cost 3.15 M tokens for 20 useful
agents, plus one wasted wave: 20 sub-agents were launched with a rate window already 88 % used, and seven of
them died. **Check every quota window before a fan-out, not just the weekly one.**

## Limits that apply to every number here

n = 2 or 3 per cell, so a difference of one run changes a ratio. The judge belongs to the same model family as
the subjects. The skill arm cannot ask the user questions in a sub-agent, so it always takes its own tier
recommendation and never escalates. The cases were written by the plugin's author, who knew which defect each
one targeted; the mitigation was to change domain and wording between cycles and to add negative controls, not
to pretend the bias is absent. Nothing here was measured on a long real project from start to finish.
