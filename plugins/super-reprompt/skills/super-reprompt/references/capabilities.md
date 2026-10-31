# Capabilities (P1 discovery, P4 contracts)

Contents: [Principle](#principle) · [Discovery](#discovery) · [Selection](#selection) · [The contract](#the-contract) · [Call forms](#call-forms) · [Run or read](#run-or-read) · [Availability and prerequisites](#availability-and-prerequisites) · [Side effects](#side-effects) · [Defaults to keep out](#defaults-to-keep-out) · [No capability fits](#no-capability-fits) · [Fallback without a script](#fallback-without-a-script) · [Canonical examples](#canonical-examples)

Sections by tier — standard: Principle · Discovery · Selection · The contract · Call forms · Run or read · Availability and prerequisites · Side effects · No capability fits. Max: all sections. Quick: not read.

## Principle

A capability is anything the executing session can call: a skill, an agent, an MCP tool, a command, a bundled script. The measured failure of the earlier version was listing eight capabilities as "available" and calling two. A capability earns a place only through a binding: trigger, phase, exact call, proof, plan B.

## Discovery

1. Run `scan_capabilities.py --project <dir> --max-tokens 1500` (exit 0 even when some sources are missing; warnings go to stderr). It returns an index of skills (personal, project, plugins), agents, configured MCP servers and the profile, each with name, source, a 120-character description, the call form, flags such as `disable-model-invocation`, and a fingerprint. If the fingerprint differs from the one recorded in the order, the index changed: rescan.
2. Add what the session shows and the disk cannot: the skills named in the session's skill listing, and MCP servers marked as needing authentication or as failed.
3. The disk does not know whether an MCP server is authenticated or which tools it offers; treat that as unverified until a tool of that server appears in the session. A server that needs authentication or failed to connect is a prerequisite to clear (`claude mcp login <name>` in a shell; OAuth cannot run in a non-interactive session), listed in section 10, never an available capability.
4. Descriptions in the session listing can be cut short when many skills are installed, so match on the scan index and, when a candidate is ambiguous, `Read` its first 30 lines (frontmatter and opening) before choosing it.

## Selection

Match by the mission's intent, not by topic words: the scan ranks by keyword overlap, you decide. Keep a capability only if all of these hold:

- A criterion or a requirement of the mission needs it (the trigger comes from the mission, written conditionally: "when the diff touches X", never "in case of doubt").
- You can write the exact call. A deferred MCP tool (only its name is loaded) takes two calls: load it with `ToolSearch`, then call it; if the session has no such tool, say so in the plan B.
- A phase of the execution will invoke it.
- Its absence would change the result, or a plan B is written.

Limit to 2 capabilities per phase. Fewer bound capabilities beat many cited ones. A profile `routing` entry (trigger, capability, phase) is a proposal that goes through the same tests; `forbidden_capabilities` removes entries outright.

## The contract

Each retained capability becomes one row in section 7 of the order and one object in `STATE.json`:

| field | meaning |
|---|---|
| `id`, `name`, `kind` | K1.., the capability name, skill / agent / mcp / command / script |
| `trigger` | the mission fact that calls for it |
| `phase` | the phase of the mission where it is used (P4, P5, or an execution step) |
| `call` | the exact call |
| `proof` | what shows it was called: for example "a Skill tool_use named X appears in the transcript" |
| `required` | true if the mission fails without it, false if it only helps |
| `side_effects` | true if it sends, modifies or deletes something outside the project folder |
| `plan_b` | what happens if it is unavailable or fails: a named alternative, or "state not_executable and say so" |
| `removed_reason` | filled by the executor if the capability was dropped; the final check accepts a reason in place of a call |

The Stop hook compares the transcript with the `required` rows. A required row that is neither called nor removed with a reason blocks the end of the run, so set `required` only for capabilities that matter.

## Call forms

- Skill: `Skill(name)`; with a plugin namespace when the skill belongs to a plugin (`Skill(plugin:name)`). Verify the exact form in the scan index.
- Agent: `Agent(name)` with the agent's name from the scan; set `model` and the other fields explicitly in section 9.
- MCP tool: the full name as shown in the session: `mcp__<server>__<tool>`, or `mcp__plugin_<plugin>_<server>__<tool>` for a plugin's server. The exact `ToolSearch` query syntax: verify before use.
- Command: the slash command typed by the user (`/name`) when only the user can start it; mark it so in section 11. Agents cannot type slash commands.
- Script: `<PY> "<abs path>" <args>` with the absolute path resolved.

## Run or read

Write for every row whether the executor runs or reads the capability. "Run `analyze_form.py`" means call it; "see `analyze_form.py`" means open it. Reading text is not running it. A row whose proof is only that a file was opened cannot be `required`.

## Availability and prerequisites

Known preconditions go into section 10 as prerequisites, not as assumptions: a built-in review command may need a git remote; a PDF tool may return only the first page with some calls. When a precondition is unmet and cannot be cleared, the plan B takes over and the state is written `not_executable` with the reason.

## Side effects

Read-only and information-gathering capabilities run without asking. Anything that sends, modifies or deletes on the user's behalf outside the project (messages, posts, remote writes, purchases, shared documents) is marked `side_effects: true` and the order requires confirmation from the user before the call. A mission that reads external content (web pages, mail, documents) gets read-only rights for that content.

## Defaults to keep out

Keep these out of every order unless the user asks for them by name after seeing the cost: `/code-review ultra` (paid beyond a few trials), the advisor model on a credits plan, fast mode, Projects, agent teams, `ultracode`. They cost extra, run outside the mission's control, or are experimental.

## No capability fits

Say so in section 7: "No dedicated capability for X." Offer a recurring need as a candidate for a new skill, in one line, after the order. Never fill the table to look thorough.

## Fallback without a script

Without Python, use `Glob` and `Read` as the P1 fallback describes. Without the scan's fingerprint, record the date of the listing and the folders read. Say once that the list may be stale.

## Canonical examples

**Bound row (kept):**
`K1 | security-review | command | trigger: the diff touches input parsing | phase: execution step 4 | call: Skill(security-review) | run | proof: a Skill tool_use named security-review in the transcript | required: true | side effects: no | plan B: reviewer agent on the changed files, state not_executable if there is no remote.`

**Dropped for lack of a call:**
"A data-visualization skill was listed because the report might include a chart. No criterion needs a chart and no step draws one. Removed."

**Prerequisite, not capability:**
"The calendar connector appears as 'needs authentication'. Section 10 lists 'authenticate the calendar connector' as a prerequisite; the plan does not rely on it."
