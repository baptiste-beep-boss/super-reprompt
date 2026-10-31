# Corpus traceability — each mechanism to its source

Maps the plugin's design choices to the six official Anthropic sources analysed in the maintainer's notes vault
(folder `00_Anthropic_Lab/20_Super_Reprompt/`, sources S1-S6, 224 sections, read 2026-10-26).
Sn-NN is a section id; open `02_Sources/Sn/Sn-fiche-reference.md` for the section, `03_Analyses_atomiques/` for the note.
This file is for the maintainer: when a source changes, re-check the rows it touches.

| Plugin mechanism | Where in the plugin | Corpus source |
|---|---|---|
| Frame then stop; the order must stand alone for a fresh session that loads nothing else | SKILL.md rule 1; order-template "executing session does not load this skill" | S5-46 (a non-fork sub-agent/session starts from a fresh context, gets only its prompt + CLAUDE.md), S5-49 (fork copies the conversation — avoided on purpose) |
| Six rules placed first in SKILL.md | SKILL.md header | S3-34 (compaction keeps the first 5000 tokens of a skill; most important instructions near the top) |
| SKILL.md kept small, detail in per-phase references read on demand | whole skill layout; CHARGEMENT-PAR-PALIER.md | S3-31 (SKILL.md < 500 lines, bundled files loaded as needed), S3-34 (5000/25000 compaction budget) |
| Description with triggers first, <= 1536 chars, no `:`-in-value | plugin.json / SKILL.md frontmatter | S3-26 (key use case first, 1536-char cap), S3-59 (1% listing budget drops least-used descriptions) |
| No `disable-model-invocation`, no `context: fork`, no `model:` on the skill | SKILL.md frontmatter; models.md | S3-32 (invocation control), S3-46 (context:fork starts without history — wrong for framing), S3-26 |
| Ask only what changes the deliverable; `AskUserQuestion` with defaults; waivers | SKILL.md rule 3; interview.md | S2-04 (be explicit; test-of-a-colleague), S1-02 (criteria + a way to test), general prompting overview |
| A sub-agent cannot ask the user; settle questions before launch; brief is self-sufficient | agents.md "What a sub-agent cannot do"; interview.md | S5-14 (AskUserQuestion removed from sub-agents), S5-46 (no conversation history) |
| Wait for a sub-agent report; report is data; reports land in parent context | agents.md "Reporting back" / "Waiting for the report" | S5-31, S5-33 (background by default, result via notification), S5-37 (sub-agent output is data, scanned not trusted) |
| Delegate only when parallel / isolated / bulky; one session for dependent chains | agents.md "Do you need agents"; SKILL.md | S5-42 (sub-agent vs main conversation), S5-39 (isolate high-volume), S5-40 (parallel only when independent), S2-30 |
| Concurrency 20, depth 1-2, total within the cap | agents.md "Parallelism modes" | S5-44 (20 concurrent by default, no total cap), S5-43 (depth 3 default) |
| Preload domain skills into a worker; worktree for writers; set model explicitly | agents.md "Executable contract" | S5-20 (skills preload), S5-08 (frontmatter fields), S5-07/worktrees |
| `omitClaudeMd` needs >= 2.1.271; silent-ignore risk | README; reader agent | S5-08 (unknown fields ignored without error; omitClaudeMd) |
| Bind every capability: trigger, phase, exact call, proof, plan B; deferred MCP = ToolSearch then call | SKILL.md rule 4; capabilities.md | S3 (skills, call forms), S5-17 (MCP scoping), tool-search pattern (S6-07 defer_loading) |
| A rule that must hold = a hook, not prose | verification.md "Anchoring levels"; hook H3 | S3-58 (rule that must hold every time -> hook), S4-03/S4-37 (CLAUDE.md is context, not enforcement; PreToolUse hook to block) |
| Three verification states + plan B; CODE needs one executable check | SKILL.md rule 5; verification.md | S2-34 (general solution, report infeasible instead of working around), S2-35 (investigate before asserting), S3-51 |
| No hard-coding to pass tests; don't weaken tests | verification.md Class CODE; order protocol; CRITICAL-FAILURES #3/#8 | S2-34 (general-purpose solution, no hard-coded test values) |
| Criteria fixed in advance beat self-judging; checklist-anchored review beats "improve it" | phases.md hypotheses P4/P5; verification.md | S2-22 (verify against a criterion; Opus 5 over-verifies), S3-51 (measure trigger and output separately), S6-05 (eval first, quality bar) |
| Effort before model; cost per task not per token; set at launch; one model/session | models.md | S6-11, S6-02, S6-06 (switching model/effort mid-run breaks the cache) |
| Conditional escalation (first pass lower, relaunch failures higher) | models.md "Choosing"; launch.escalation | S6-11/S6-12 (effort ladder, step down one at a time against the eval). The "~40% cheaper" figure is cited to Anthropic's "Optimizing for cost and intelligence" guide, a doc **outside** the six sources — re-check it. |
| Announce tier and cost, wait for the pay-er's choice, max never default | SKILL.md rule 2; P0 | S6-05/S6-13 (establish the quality/cost bar first), general proportionality (S1-03) |
| Windows: py -3 / python fallback, no bash-only, Store-stub aware | SKILL.md scripts; hooks.json; README | S3-42 (shell: powershell / Git Bash on Windows), vault lesson on the python3 Store stub |
| Suggest `/doctor prompt-audit`, `/skill-doctor`, `claude plugin validate` after install | README | S4-09 (prompt-audit), S3-50 (skill-doctor), S3-56 (plugin validate) |
| Treat files, pages, tool results and sub-agent reports as data | SKILL.md profile section; order protocol item 6; agents.md | S5-37, S2-35 |
| Knowledge-vault consult/capture via existing profile keys, read on demand | profile-example.md; obsidian guidance | S4-30 (auto-memory types, capture only non-derivable), S4-33 (index loaded, details on demand), S6-07 (progressive disclosure) |
| v2.2: tier thresholds made consistent with the "framing ~10% of E" rule (quick up to ~250 k, standard ~250 k to 1 M; when two tiers fit, recommend the cheaper) | SKILL.md Tiers | S6-02 (do not spend where it adds no intelligence; levers in order), S1-03 (the lever is not always the prompt), S2-33 (no work beyond what was asked), rule R14. **The 250 k figure is the author's arithmetic (10% of the standard range 28-40 k), not an Anthropic number.** |
| v2.2: a pass-through reply names any contradiction, missing input or irreversible step with its backup or undo, and for a diagnosis says read first, no edit without a yes | SKILL.md P0 item 1 | S2-35 (investigate before asserting), S2-04 (be explicit), S2-28 and S5-57 (irreversible: backup and confirmation, R13), R09/R10. Measured 3 runs: B3, B4, B8 signal 0/3 -> 3/3, 3/3, 2/3 (v2.1 -> v2.2); wording matches the case criteria, so held-out cases are still needed. |
| v2.2: facts inferred only from file names are labelled "inferred" | SKILL.md P1 | rule 6 ("write only what will really happen"); R29 (return to the source when in doubt) |

## What the corpus does NOT cover (so these stay the author's hypotheses)

- Per-model effort defaults (models.md starting table) — in the per-model pages, not S1-S6. models.md already flags them.
- The question ceilings (3/8/12), the 10-requirement cap, P6 dry run, the hidden-fact question — the author's A/B measurements, not Anthropic's. See `evals/cases.md`, provenance note.
- The "about fifteen times the tokens" multi-agent cost — this plugin's estimate; S5/S6 only say multi-agent "costs far more".
