# Criteria and verification (P4)

Contents: [Acceptance criteria](#acceptance-criteria) · [Three states](#three-states) · [Plan B and the fallback ladder](#plan-b-and-the-fallback-ladder) · [Class CODE](#class-code) · [Class DOCUMENT](#class-document) · [Class RESEARCH](#class-research) · [Class DATA](#class-data) · [Classes DECISION, INFRA, OTHER](#classes-decision-infra-other) · [Anchoring levels](#anchoring-levels) · [Iteration cap](#iteration-cap) · [Canonical examples](#canonical-examples)

Sections by tier — standard: Acceptance criteria · Three states · Plan B and the fallback ladder · the Class section of the mission's class · Iteration cap. Max: all sections. Quick: not read.

## Acceptance criteria

Write 5-8 criteria specific to this mission, plus 2 edge cases. Each must be:

- **Yes/no decidable by a stranger** who has the deliverable and nothing else. Good: "a patient with a basic smartphone finds the waiting time in under 30 seconds without creating an account." Poor: "easy to use."
- **Tied to an external source of truth**, recorded in `source`: `test` (a command that passes or fails), `document` (a cited text), `person` (a named human who looks), `second_model` (a fresh-context reader or reviewer).
- **Backed by a proof**, recorded in `proof`: the exact output, the verbatim citation, or the artifact that shows it.
- **Marked `unsourced: true`** when the fact comes only from general knowledge. The report repeats the label so the reader knows where to look first.
- **Given its failure case**: say what a failing result looks like ("fewer than 3 independent sources" fails C4), so the rule binds.

Turn a requirement into a criterion before adding anything else; requirements beyond ten become criteria. A criterion that no one could check ("is high quality") is rewritten or dropped, and the order says so.

Why: tests and checklists written in advance improved results in measurements, whereas asking a model to judge its own work afterwards did not.

## Three states

Every verification command and criterion is in exactly one state, written down:

- `executed`: it ran and its output is recorded (command, exit status, the decisive lines).
- `not_executable`: it cannot run here; the reason is written ("no git remote", "no network", "tool absent").
- `not_run`: it could run but did not; the reason is written.

Nothing is reported as done without one of these. A check that failed to start, or a syntax-only check, is `not_executable` or `not_run`, not `executed`. Also write, for each check, its plan B in the form "if X is impossible or fails, then Y".

## Plan B and the fallback ladder

Descend only as far as needed, and record the rung used:

1. an executable test or command with a discriminating result;
2. cited sources, with verbatim quotes and dates;
3. a second model in a fresh context (a reviewer or reader agent) answering yes/no per criterion;
4. a named competent human, with the exact question to ask.

At the last rung the order states plainly: "not verified by a machine; the person named checks X." A mission whose only check is rung 4 gets tier `standard` or higher so that the fallback is reviewed.

## Class CODE

- The base check (test, lint or build command) is detected in P1 and written as V1; it runs before any change to record a baseline.
- At least one end-to-end check proves the feature works as a user sees it.
- The project is a clean git state before launch; no git means `git init` and a first commit, or a backup copy. Checkpoints do not cover shell commands or sub-agents.
- Plan B when a built-in review command fails because the project has no remote or no repository: a fresh-context reviewer limited to the changed files plus a search for risky patterns (for example grep for `eval(`, string-built SQL, hard-coded keys), with the state written as `not_executable: no remote`. Verify which review commands need a remote before relying on them.
- Locks against early victory, copied into the order: one feature at a time; success reported only after the end-to-end check; fix the root cause, not the message; the same failure at the same point twice means stop and report; tests are never edited or deleted to pass; no value is hard-coded to satisfy a specific test input.
- Criteria live in `STATE.json` with `passes: false`; the executor flips the field only after producing the proof.

## Class DOCUMENT

- Criteria are yes/no and tied to the reader's task. Every factual claim has a source or the label `unsourced`; quotes come first (extract the verbatim passage, then write from it).
- Add a reader test: a fresh-context agent given only the document answers the reader's key questions; wrong or missing answers are defects.
- The report carries an exact diligence statement: what was re-read, by whom, and how.
- Plan B: second model in a fresh context, then a named human reader.

## Class RESEARCH

- Each key claim has at least two or three independent, dated sources; contradictions between sources are named, not smoothed over.
- A declared gap is a valid result. Allow one targeted follow-up search per gap, then write "not found" and stop; filling a gap from memory is not allowed.
- Key claims get an adversarial check by an agent that tries to refute them; "not verified" is distinct from "refuted".
- The search tool is chosen in P4. If none is available, the check is `not_executable` and the order says "no figure from memory".
- Plan B: fewer claims with stronger sources beats more claims with weaker ones.

## Class DATA

- Audit the file before any change: sheets, ranges, formulas against constants, date, number and percentage formats, missing values. Work on a copy, or take a backup, before a destructive change; never overwrite the source without a written yes.
- Numeric checks: totals preserved (or every difference explained); reconciliation by segment; an independent recalculation of a sample of formulas; types and units (a percentage stored as 0.12 versus shown as 12); duplicates examined on the business key before deletion; empty cells distinguished from zero; a change log (what, where, why).
- Guardrails: never call formulas validated when no engine recalculated them; arithmetic consistency is not business validity; state the assumptions.
- Plan B: with no calculation engine available, say that the formulas were not recalculated.

## Classes DECISION, INFRA, OTHER

- DECISION: state the decision, the threshold that would change it, the best counter-argument written by a separate reader, and what is irreversible. Criterion example: "the memo names the figure that would reverse the recommendation."
- INFRA: idempotent steps, a rollback written before the first change, a backup of any settings file the mission edits, and a post-change check that the previous behavior still works.
- OTHER: derive criteria from the user's own words; ask in P2 how success will be recognized.

## Anchoring levels

From weakest to strongest guarantee. Use the strongest that exists and say which one applies:

1. An instruction in the order (advisory).
2. A user-typed `/goal <condition>` line: a small model reads the transcript and judges; it runs nothing. Useful when the condition displays its own proof and includes "or stop after N turns". An agent cannot type it, so it is only offered to the user in the launch block.
3. The Stop hook of the plugin: runs the declared verification commands and checks that required capabilities were called; blocks the end of the turn up to three times.
4. A fresh-context second opinion limited to gaps in correctness or stated requirements.

The hook exists only if hooks are installed; if they are not, say the order relies on level 1 and 4.

## Iteration cap

Three iterations per loop. At the cap, stop and report what fails, what was tried and the likeliest cause. A fourth silent attempt is a defect.

## Canonical examples

**Good criterion (document, source person):** "C3. A volunteer who has never seen the garden finds the tool shed key policy in the handbook in under a minute. Source: person (Ana, the coordinator). Proof: Ana's yes/no after the test. Fails if the policy is only in an appendix."

**Poor criterion, repaired:** "The report is clear" becomes "A reader with no context states the three recommendations after one reading. Source: second_model (super-reprompt:reprompt-reader). Proof: the reader's three-line answer matches section 2."

**Plan B written:**
"V2. `security-review` on the diff. If the folder has no git remote the command cannot run: then a reviewer agent reads the changed files and the grep list in section 6, and the state is `not_executable: no remote`."
