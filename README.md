<div align="center">

# super-reprompt

**Stop re-explaining your project to Claude Code. Get a mission order it can execute alone.**

A Claude Code plugin that interviews you, writes a checkable mission order, has it reviewed by a
fresh-context agent, and then launches the work in a clean session — and stays completely silent when you
just want a rename.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![tests](https://github.com/baptiste-beep-boss/super-reprompt/actions/workflows/tests.yml/badge.svg)](https://github.com/baptiste-beep-boss/super-reprompt/actions/workflows/tests.yml)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-5A4FCF.svg)](https://code.claude.com/docs/en/plugins/install)
[![Measured](https://img.shields.io/badge/evals-published-orange.svg)](plugins/super-reprompt/evals/RESULTS.md)

</div>

---

## The problem

You ask for something big. Claude Code starts coding in the second sentence. Forty turns later the context is
full of exploration, the acceptance criteria were never written down, and nobody can say whether the thing is
done. You start again, with a longer prompt.

The fix is not a longer prompt. It is **separating the framing from the execution**: decide what "done" means,
in writing, in a session whose context you then throw away — then execute in a fresh one that reads the order
and nothing else.

That is what this plugin does. It also knows when to do nothing, which is the part most prompting tools get
wrong.

## Install

One line, in a Claude Code session (requires Claude Code 2.1.275 or later):

```
/plugin install super-reprompt --marketplace baptiste-beep-boss/super-reprompt
```

Or from your shell:

```bash
claude plugin marketplace add baptiste-beep-boss/super-reprompt
claude plugin install super-reprompt@super-reprompt
```

Then just describe your project. The skill fires on its own when the request deserves framing, or you can call
it explicitly with `/super-reprompt:super-reprompt`.

No API key, no account, no service. Python 3.8+ for the scripts; the plugin degrades gracefully without it.

## Before / after

Real outputs from the held-out evaluation set, same request, same model.

<table>
<tr><th width="50%">Without the plugin</th><th width="50%">With it</th></tr>
<tr><td>

> **"Find out whether flu vaccination coverage for over-65s dropped in France since 2020, with sources."**

Answers immediately with a table of figures and links. Good-looking. One run called a 53.7 % / 54 % gap
between two sources "just rounding".

No definition of the indicator, no rule for what to do when sources disagree, nothing a reviewer could
check later.

</td><td>

Refuses to answer from memory. Produces criteria first:

- at least **two independent dated sources**, one of them the health authority's own text
- the exact indicator: 65+, by flu season, which population
- **what to do when sources disagree**: both figures, with their definition — never an average

Then the work runs in a fresh session against those criteria.

</td></tr>
<tr><td>

> **"Why is an index on a low-cardinality column often useless in PostgreSQL?"**

A correct 4,800-character essay.

</td><td>

A correct **735-character** answer. No tier announced, no mission order, no questions — the plugin
deliberately gets out of the way.

</td></tr>
<tr><td>

> **"Delete every account with no login for 24 months from the team's shared customer database."**

Refuses to run it blind and explains why — but omits the rehearsal outside production.

</td><td>

Not a pass-through, whatever the length. The order requires **the list of affected rows first**, a
**restorable backup with a tested restore**, a **rehearsal on a copy**, and an **explicit written yes**
quoting the exact row count.

</td></tr>
</table>

See [`evals/RESULTS.md`](plugins/super-reprompt/evals/RESULTS.md) for the numbers behind these, including the
cases where the plugin lost.

## What it actually does

Six rules sit at the top of the skill, because they have to survive a context compaction:

| | Rule |
|---|---|
| 1 | **Frame, do not execute.** Produce the order and stop. The work runs in a fresh session. |
| 2 | **Gate before spending.** Announce the depth and the token cost, then wait for your choice. `max` is never the default. |
| 3 | **Ask only what changes the deliverable.** Every question has a declared default; a question whose two answers lead to the same work is dropped. |
| 4 | **Bind every capability.** A skill, agent or MCP tool enters the order with a trigger, the exact call, the proof it was called, and a plan B — or it is removed. Listing a tool is not calling it. |
| 5 | **Every check has three states and a plan B.** `executed`, `not_executable` (with the reason), or `not_run`. Every code mission carries at least one runnable command. |
| 6 | **Write only what will really happen.** If a check was not run, the report says "not run" and why. |

### The flow

```
P0  gate          classify, announce cost, you pick the depth        ← you can stop here
P1  discovery     read the project so no question asks what is already written
P2  interview     only questions that change the deliverable, with defaults
P3  specification intent, scope in/out, at most 10 requirements, permissions
P4  criteria      5-8 yes/no criteria + verification commands + capability contracts
P5  review        a fresh-context agent checks the draft against the criteria
P7  launch        write ORDRE.md + STATE.json, validate, show it, offer the launch
```

### Three depths, so framing never costs more than the work

| | `quick` | `standard` | `max` |
|---|---|---|---|
| Framing cost | 7-10 k tokens | 28-40 k | up to 100 k |
| Questions | 3, one round | 8, two rounds | 12, three rounds |
| Adversarial review | skipped | one pass | one pass + pre-mortem |

Aim framing at about 10 % of the estimated execution cost. The plugin recommends a depth from three facts —
estimated size, irreversibility, ambiguity — and when two fit, it recommends the cheaper one.

## When it stays out of your way

This is the part worth testing first, because a framing tool that fires on everything is worse than none.

**Nothing happens** — no tier, no questions, no mission folder — for a one-line edit, a factual question, a
direct command, a conversation turn, or a prompt that is already complete. The reply reads as if the plugin
were not installed. That behaviour is enforced by a script, not by good intentions:

```bash
python dev/check_silence.py reply.txt --max-lines 3
```

**Two requests are never waved through**, however short, because the measurements showed both going wrong:

- **sourced research or a state of the art** — it needs criteria, not a confident answer from memory;
- **a command that deletes, overwrites or publishes data others or production depend on** — it needs the
  list of what changes, a restorable backup, a rehearsal outside production, and an explicit yes.

A local file or a scratch copy is not production. The guardrail is narrow on purpose.

## Optional: the research agent

For a domain you have no notes on yet, the interview offers one extra question — default **no** — to run
`reprompt-researcher` before the order is written. It inventories what your own notes already say (so you
never pay twice for the same research), then reads primary sources, cross-checks every claim against at least
two independent ones, ranks each as primary / secondary / opinion with its date, and writes filing-ready
notes plus a manifest of downloadable documents.

It refuses to state anything without a URL and a date, to go around a paywall or a CAPTCHA, to use a cookie
or an account, to **disguise who is asking** (no forged user agent — it tried once, during its first real
run, and the rule was added), or to copy a document whose licence does not clearly allow it.

Its tools are `Read, Glob, Grep, WebSearch, WebFetch, Write` — **no Bash**. A sub-agent reading the open web
does not need a shell. It proposes downloads in a manifest; your session fetches and hashes them, and
`scripts/validate_library.py` refuses a manifest whose hash is wrong, whose licence forbids the copy, whose
file nobody listed, or which points at somebody's home directory.

## What is measured, and what is not

**This matters more than the feature list.** Most prompting advice is asserted; this plugin's behaviour was
checked against held-out cases that were frozen and hashed **before** each fix, and the results — including
the failures — are published in [`evals/RESULTS.md`](plugins/super-reprompt/evals/RESULTS.md).

**Fixed and verified on cases the fix was not written against:**

- a sourced-research request is never answered without criteria — 2/2 against 0/2 without the plugin
- a destructive write to shared or production data gets its guardrails — 2/2 against 0/2
- a factual question gets a plain answer with no framing vocabulary — confirmed twice, by a blind judge and
  then by a script

**Not reached, and why:** the overall acceptance bar. The skill tells itself to answer "in at most 3 lines",
and **no version of it, nor the model without it, respects that** — while the independent judge rates the
offending replies 5/5 on proportionality. The rule is the problem, and reconsidering it is the next cycle.
The plugin is published as a working tool with a known open question, not as a finished product.

**Never measured:** any comparison against another framing tool or prompt pack; a long real project end to
end; anything at n > 3 per case. Sample sizes are small, and the judge is a model from the same family as the
subjects. Treat the numbers as evidence of testing, not as a promise about your project.

### Run the checks yourself

```bash
cd plugins/super-reprompt
python -m unittest discover -s tests      # 213 tests
python dev/measure_loading.py --check     # instruction budget per tier
claude plugin validate .
```

The instruction budget is capped on purpose: `standard` reads **16,993 tokens** of instructions against a
17,000 ceiling, and every addition has to be paid for by cutting real redundancy elsewhere. The research
reference adds 1,086 tokens and is counted **separately**, only when the agent is offered, rather than hidden.

## What ships in the plugin

| | |
|---|---|
| `skills/super-reprompt/` | the skill: `SKILL.md` plus references loaded per depth, never all at once |
| `agents/` | 4 agents: scout (read-only discovery), reviewer (adversarial), reader (fresh-eyes test), researcher |
| `scripts/` | `mission.py`, `validate_order.py`, `scan_capabilities.py`, `launch.py`, `validate_library.py` — standard library only, no network |
| `hooks/` | an optional one-line suggestion hook, a compaction hook that re-injects the essentials, a Stop hook that runs the pending verification commands itself |
| `dev/` | the instruction-budget measurement and `check_silence.py` |
| `evals/` | the frozen held-out sets with their hashes, the published results, the critical-failure list |
| `profile-example/` | an optional profile: defaults, routing, forbidden capabilities, post-mission steps |

## FAQ

**Does it work with any model?** It is written for Claude Code and uses its skills, agents and hooks. The
flow is model-agnostic; the measurements were taken on Claude models.

**Will it slow me down on small tasks?** That is what the negative controls test. On a one-line edit or a
factual question it adds nothing and says nothing. If you ever see it announce a depth on a trivial request,
that is a bug worth an issue — it is the exact defect fixed in v2.5.

**Does it send my code anywhere?** No. The scripts use the standard library only and make no network calls;
a test enforces that. The research agent fetches public web pages when you explicitly enable it.

**Can I keep my own conventions?** Yes — the optional profile adds defaults, routing rules, forbidden
capabilities and post-mission steps. It never waives the cost gate or the confirmations.

**How do I remove it?**

```bash
claude plugin uninstall super-reprompt
claude plugin marketplace remove super-reprompt
```

## Contributing

Issues and pull requests are welcome, especially a case where the plugin fires when it should not — that is
the failure mode worth hunting.

Two house rules, both learned the hard way: **a held-out case is frozen and hashed before the fix it
measures**, and **a binary criterion is checked by a script, not by a judge** (two blind judges once read the
same criterion in opposite ways, which cost a whole cycle). Never loosen a test or raise the instruction
budget to make something pass — fix the cause.

## Licence

MIT — see [LICENSE](LICENSE).
