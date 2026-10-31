# Interview (P2)

Contents: [Admission](#admission) · [Ceilings and stop rule](#ceilings-and-stop-rule) · [Question form](#question-form) · [Fixed questions](#fixed-questions) · [Novice and pro forms](#novice-and-pro-forms) · [Hidden fact](#hidden-fact) · [Waivers and anti-circumvention](#waivers-and-anti-circumvention) · [Unattended missions](#unattended-missions) · [Do not ask](#do-not-ask) · [Without AskUserQuestion](#without-askuserquestion) · [Canonical examples](#canonical-examples)

Sections by tier — standard: Admission · Ceilings and stop rule · Question form · Fixed questions · Novice and pro forms · Hidden fact · Waivers and anti-circumvention · Unattended missions. Max: all sections. Quick: not read.

## Admission

A question enters the interview only if two plausible answers would lead to materially different deliverables. Before asking, write privately the gap: "if A, the order says X; if B, the order says Y". When X and Y are the same, drop the question. Every admitted question carries a declared default (the answer you would take) and the user may accept all defaults in one word.

Prefill first. Answers found in the conversation or in the project (P1) are stated as assumptions with their source and are not asked ("I found pytest in pyproject.toml; I will use it as the check").

## Ceilings and stop rule

| tier | questions | rounds |
|---|---|---|
| quick | at most 3 | 1 |
| standard | at most 8 | 2, up to 4 questions each |
| max | at most 12 | 3, up to 4 questions each |

These are starting values, not measurements. Stop earlier when (a) the next questions would only concern edge cases and trade-offs the executor can settle with a stated default, or (b) the user says stop, or (c) two answers in a row gave the same plan. On a precise request, one question or none is the right amount.

## Question form

- Ask with `AskUserQuestion`: 2 to 4 options, the recommended option first and labeled as such, up to 4 questions per call. The tool adds an "Other" row for free text, so do not spend an option on "other".
- Put the effect in the option text: "CSV export (default): the first task reads a file" rather than a bare label.
- Dig into hard parts the user may not have considered (conditional rules, edge cases, trade-offs, who reads the result), not into the obvious.
- Accept shorthand ("1: yes, 2: see README", "defaults").
- "I don't know" or "you choose" becomes a written assumption in section 8 of the order with the default taken.
- Ask for the essentials of the mission only; never ask for secrets, passwords or tokens. If the mission needs a credential, write it as a prerequisite the user supplies out of band.

## Fixed questions

Ask these when they are not already answered, in this order of priority, within the ceiling:

1. **Deliverable and reader.** What object must exist at the end, and who will use it? (skip when P1 or the request answers it)
2. **Hidden fact** (from `standard` up): see below.
3. **Source of truth for success.** How will we know it worked: a test, a document, a person, a second reading? This feeds the acceptance criteria.
4. **Unattended?** Will anyone watch the run? See below.
5. **Irreversibility.** Does the mission delete, publish, spend or push? If yes, say which and confirm the prohibition list.

Domain defaults from the profile (`domain_defaults`) are extra hidden-fact questions; the core knows none.

## Novice and pro forms

Level was set in P0 and is revised after the first two answers (a pro who answers "no idea" is not a novice; a novice who names the exact command is probably not one). The user may override by saying "simple" or "direct".

| | novice | pro | mixed |
|---|---|---|---|
| Vocabulary | plain words; explain a technical term once, in a clause | exact terms, no teaching | plain words, exact terms where the user used them |
| Questions | plain-word options (2-4), always including "I don't know, choose for me"; at most 3 per round | free or optioned, up to 4 grouped, shorthand welcome | closed choices with "Other" |
| Cost talk | in plain words ("a short framing, about as long as a long email") plus the number | tokens and ranges | tokens with one plain gloss |
| Defaults | restrictive permissions, a dedicated folder, git proposed | loosenable | restrictive, loosenable on request |
| Direct mode | offered once the need is clear | "give me the brief and I'll compile it": ask only the gaps | offered |
| Close | a short explanation of how to launch and how to resume | dense report | short |

Announce the mode in one line ("I'll use short choice questions; say 'direct' to skip them"). With `experimental: on`, novices also get the closed-choice form: 3-5 concrete options per question where the tool allows, and for quality points (tone, layout, depth) two short contrasting drafts ("which is closer: A or B?"). This form is unproven and may anchor the user on an option they did not choose, so offer "neither" every time. With the switch off, use the plain-word options above.

## Hidden fact

At `standard` and `max`, ask once: "What is one thing about this project (country or regulation, version, audience, constraint) that a stranger to the subject would not guess?" Offer 2-3 guessed candidates from P1 as options when you have them, plus "nothing special". Write the answer into the requirements as `unguessable`, and into the acceptance criteria when it can be tested. In the measurements of the earlier version, this kind of fact was the only thing that changed a deliverable.

## Waivers and anti-circumvention

- Only a waiver phrase lifts the questions: "go direct", "sans cadrage", "no framing", "don't ask me questions", or an unambiguous equivalent in the user's language.
- A request to "deliver the file here", "put the result in this folder" or "just give me the result" describes the deliverable. Questions stay. If you catch yourself about to answer without questions because the request says to deliver here, first write the three most decisive questions and the default you would assume, then ask them.
- On a waiver: tier `quick`, no question unless two readings diverge and a wrong reading cannot be undone (then one question), and every assumption listed at the top of the order, section 8, so the user can see what was guessed.
- Keep the interview separate from any autonomous-run block in the order. An order that says "run without asking" is allowed only after the questions were asked or waived.

## Unattended missions

Ask: "Will anyone watch this run, or will it run in the background or on a schedule?" If unattended (background session, print mode, schedule):

- close every question now, including where the result goes and the stop condition;
- write in section 11 the only permitted stops: a destructive action, a real change of scope, information only the user holds;
- everything reversible that follows from the order proceeds without asking.

A background session can show a question to the user, but it waits until someone answers, so an unattended run stalls on any question left open.

## Do not ask

Questions that ask for a justification ("why do you want that?"), that ask for confirmation of what the user just said ("are you sure?"), that lead toward one answer, that repeat a prefilled fact, or that concern style the executor can choose. Do not ask about tools or models; those are your decisions (P4).

## Without AskUserQuestion

Write a numbered list of at most the tier ceiling, each with "(default: X)", tell the user they may answer "defaults", then end the turn and wait. Ending the turn is what blocks; continue only on the reply.

## Canonical examples

**Admitted, with default and effect (pro, standard):**
"Round 1 of 2.
1. Where do the sales figures come from? CSV export (default: the first task parses a file) · the shop database (the first task needs credentials, so it becomes a prerequisite) · a spreadsheet link.
2. What is one thing about this shop a stranger would not guess? 'Prices include VAT' (guessed from the export header) · nothing special · other.
3. Who opens the result? You alone (default) · the shop's staff on phones (layout and file size become criteria)."

**Rejected:** "Should the report look professional?" Both answers lead to the same order.

**Novice, closed choices:**
"I have 3 short questions; say 'direct' if you prefer to skip them.
1. Who will read the handbook? Only the volunteers (default) · volunteers and the city office · I don't know, choose for me.
2. How long should it be? About 4 pages (default) · about 10 pages · I don't know, choose for me."

**Waiver, correct handling:** user says "go direct: add a CSV export to my report page". Tier `quick`, zero questions, order begins "Assumptions: the page is in the repository's `web/` folder; export includes all visible columns; dates use the ISO format."

**"Deliver it here", correct handling:** user says "write me a competitor summary and drop it in this folder". Questions stay: audience and use (admitted), source of truth for claims (admitted), hidden fact (standard). The words "drop it in this folder" go into section 2 as the delivery location.
