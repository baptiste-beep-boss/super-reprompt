# NOTES-CONSTRUCTION - mechanics of the super-reprompt plugin

Build notes for the people who maintain the plugin. Doc pages are those of the local Claude Code documentation
corpus (`code.claude.com/docs/en/<page>`). A fact marked **UNVERIFIED** is not in that documentation (or was only
observed on one machine) and is never relied on without a fallback.

Tested with Claude Code 2.1.266 on Windows 11, Python 3.13 (also 3.12 and 3.14, see section 6). Nothing here
launched a Claude session (no quota used).

## 1. Register of verified facts

| # | Fact | Page |
|---|------|------|
| 1 | Plugin root variable is exactly `${CLAUDE_PLUGIN_ROOT}` (install directory of the plugin version; changes on update, do not write state there). Persistent data variable: `${CLAUDE_PLUGIN_DATA}`. Project root: `${CLAUDE_PROJECT_DIR}`. | plugins__manifest-reference (Environment variables), plugins__components |
| 2 | Substitution happens in hook `command`/`args`, MCP config and in the Markdown body of skills, commands and agents. The variables are exported as environment variables to hook processes only; they are NOT in the environment of commands Claude runs through the Bash tool, so a skill must write `${CLAUDE_PLUGIN_ROOT}` in its body and let Claude Code substitute it. | plugins__manifest-reference (Where each variable resolves), skills (string substitutions) |
| 3 | On Windows the substituted plugin paths use forward slashes (`C:/Users/...`). | plugins__manifest-reference (Quoting and path separators) |
| 4 | `.claude-plugin/plugin.json`: only `name` is required (kebab-case; names starting with `claude-`/`anthropic-` etc. are rejected). All other directories (`skills/`, `agents/`, `hooks/`) sit at the plugin root, not inside `.claude-plugin/`. An unknown top-level key is stripped with a warning. | plugins__manifest-reference |
| 5 | Plugin hooks live in `hooks/hooks.json`: optional top-level `description`, then `"hooks": { Event: [ { "matcher"?, "hooks": [ { "type": "command", "command": ..., "timeout": seconds } ] } ] }` - same shape as the `hooks` object of settings.json. They are registered when a session loads the plugin and fire on their events whether or not a plugin skill runs. | plugins__components (Hooks), hooks (Configuration) |
| 6 | A command hook without `args` is "shell form": run by `sh -c` on macOS/Linux, by Git Bash on Windows, or by PowerShell when Git Bash is not installed. With `args` it is "exec form": a real executable is spawned with no shell (on Windows it must be a real `.exe`). Shell form needs `${CLAUDE_PLUGIN_ROOT}` in double quotes (a path with spaces otherwise splits). | hooks (Exec form and shell form), plugins__components |
| 7 | User invokes a plugin skill as `/<plugin>:<skill-dir>` -> `/super-reprompt:super-reprompt`. A frontmatter `name` replaces only the last segment. The bare `/super-reprompt` also works unless another command already has that name (a personal skill with the same name does clash). | skills (How a skill gets its command name) |
| 8 | Plugin agents are named `<plugin>:<name>` (`super-reprompt:reprompt-reviewer`); the user can @-mention `@agent-super-reprompt:reprompt-reviewer`; hooks receive the scoped name as `agent_type`; the Agent tool takes `subagent_type`. | plugins__components (Agents), sub-agents, hooks (SubagentStart, Agent tool input) |
| 9 | Frontmatter fields supported in plugin agents: name, description, model, effort, maxTurns, autoCompactWindow, tools, disallowedTools, skills, memory, background, omitClaudeMd, isolation (`worktree` only), color, experimental.cacheTtl. Ignored in plugin agents: permissionMode, hooks, mcpServers, initialPrompt. `omitClaudeMd` needs Claude Code 2.1.271+. Subagents Claude spawns from the main conversation start in the background by default. | plugins__components, sub-agents (Frontmatter reference, foreground/background) |
| 10 | Common hook input: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `permission_mode` (+ `effort`, `prompt_id`, `agent_id`/`agent_type` when relevant). UserPromptSubmit adds `prompt`. SessionStart adds `source` = `startup`, `resume`, `clear`, `compact`, `fork` (also the matcher values; `compact\|resume` is an exact-list matcher). Stop adds `stop_hook_active`, `last_assistant_message`, `background_tasks`, `session_crons`. | hooks (Common input fields, SessionStart, UserPromptSubmit, Stop) |
| 11 | Exit 0: stdout is plain text added to Claude's context for UserPromptSubmit and SessionStart (never shown in the transcript); stderr of an exit-0 hook is not seen by Claude. Exit 2 blocks UserPromptSubmit and Stop (stderr is the reason); any other code is a non-blocking error (the action goes ahead). Stop can also block with exit 0 and JSON `{"decision":"block","reason":"..."}`. Plain stdout and `additionalContext` are capped at 10,000 characters. | hooks (Exit code output, Decision control, Stop decision control) |
| 12 | Timeouts: default 600 s for command hooks, lowered to 30 s on UserPromptSubmit; a UserPromptSubmit hook that times out has its output discarded and the prompt goes through. Stop: after 8 consecutive continuations caused by stop hooks Claude Code ends the turn anyway (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` raises it). `onFailure: "block"` exists (2.1.295+) and is deliberately NOT used. | hooks (Common fields, Stop input, Block the action when a hook fails) |
| 13 | `CLAUDE_CODE_SESSION_ID` is set in Bash-tool subprocesses and hook subprocesses and equals the hook's `session_id` (updated on `/clear`). In skills, `${CLAUDE_SESSION_ID}` is substituted. | env-vars, skills |
| 14 | `transcript_path` is the session JSONL (`projects/<project>/<session>.jsonl`, every message, tool call and tool result). The file is written asynchronously and may not yet hold the current turn's latest messages when a hook fires. | hooks (Common input fields), claude-directory |
| 15 | CLI: `--bg`/`--background` starts a background session and prints its id (cannot combine with `-p`; checks workspace trust first, and exits when it cannot ask because the shell is not interactive); `--name`/`-n`; `--model` (alias or full id); `--effort low\|medium\|high\|xhigh\|max\|ultracode`; `--permission-mode default\|acceptEdits\|plan\|auto\|dontAsk\|bypassPermissions`. | cli-reference, changelog |
| 16 | `claude plugin validate <path> [--strict] [--json]` exists and checks the manifest (and MCP entries); it also lists agents/skills/commands in a directory. | plugins__manifest-reference (Validate), `claude plugin validate --help` |
| 17 | Installed plugins are recorded in `~/.claude/plugins/installed_plugins.json` and live in `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`. `CLAUDE_CONFIG_DIR` relocates the config dir. User MCP servers are in `~/.claude.json`, project ones in `.mcp.json`. | plugins__loading, env-vars, claude-directory, mcp |

## 2. Observed but NOT documented (UNVERIFIED as a contract)

- Transcript line layout, read on a local 2.1.266 transcript: top-level `"type": "assistant"` lines carry
  `message.content[]` blocks `{"type":"tool_use","name":"Skill","input":{"skill":"..."}}`; the Agent tool appears as
  `name":"Agent"` with `input.subagent_type`; MCP tools as `mcp__<server>__<tool>`. The same file also holds
  `"type":"api-request-blob"` lines that repeat the tool_use blocks, so `_lib.count_tool_calls` reads only
  `"type":"assistant"` lines (otherwise every call counts twice). Also accepts the older tool name `Task`.
- `installed_plugins.json` schema (`{"version":2,"plugins":{"name@market":[{"installPath":...}]}}`) was read from
  a local file; the docs only say it records what is installed.

## 3. Launcher choice for the hooks (and the proof)

Problem: the plugin is for the general public on Windows, macOS and Linux with only the standard library, but a
hook command must name an interpreter. On the build machine `python3` is the Windows Store stub (found on PATH,
prints "Python was not found..." on stderr, exit 49), `python` also resolves to a stub before the real install, and
only `py -3` is the right launcher.

Chosen command (identical for the three hooks, shell form, no `shell` field):

    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/X.py" || py -3 "${CLAUDE_PLUGIN_ROOT}/scripts/X.py" || python "${CLAUDE_PLUGIN_ROOT}/scripts/X.py"; exit 0

Why it works, with the runs behind each claim (all executed here):
- Git Bash (what Claude Code uses on Windows when Git is installed; `sh -c` on macOS/Linux is NOT TESTED):
  the stub `python3` fails (exit 49), `py -3` runs, the hook output is exactly one line on stdout; the stub's message goes
  to stderr, which is harmless on exit 0. With no interpreter at all the command exits 0 and prints nothing.
- PowerShell 7.6 (used when Git Bash is missing): `||` chains work; an interpreter name that does not exist at all
  is a terminating error in PowerShell, which is why the chain ends with `; exit 0` instead of `|| exit 0`
  (a first version with `|| exit 0` exited 1 in PowerShell when nothing was installed). stdin reaches whichever
  launcher runs. Windows PowerShell 5.1 (no `||`) is NOT TESTED; the hook would fail non-blocking.
- Because a failing launcher triggers the next one, the scripts must exit 0 after they have started. Every hook body is
  wrapped by `_lib.run_hook` (any exception is logged and turned into exit 0), and the Stop hook blocks with JSON on
  exit 0 instead of exit 2, otherwise a block would re-run the hook under the next launcher.
- A mac with the Xcode stub `python3` may pop the developer-tools installer: NOT TESTED.

The unit test `LauncherChain` runs this exact string from `hooks.json` through bash.

## 4. Deviations from CONTRAT.md (and why)

1. **Stop hook blocks with `{"decision":"block","reason":...}` and exit 0, not exit 2** (section 3). Same effect per the docs.
2. **`launch.py` decides on `--bg` being listed by `claude --help`**, not on the version number: the docs state no minimum
   version for `--bg` (the 2.1.212 in the contract matches a `/resume` note, not `--bg`). A version below 2.1.212
   only prints a warning. Absent `claude` or no `--bg` -> exit 3 with manual instructions.
3. **Extra `mission.py` subcommands** the execution session needs: `ready` (validates, framing -> ready),
   `waive`, `verify`, `criterion`. `start` takes the session id from `--session-id` or, by default, from
   `CLAUDE_CODE_SESSION_ID` (set in the Bash tool), so the session does not have to know its own id.
4. **STATE.json additions** (optional, ignored if absent): `calls` (`{"K1": 1}`, written by the Stop hook from the
   transcript: this is "the counter" that `mission.py close` reads), and `exit_code`/`reason` on verification commands.
5. **`REPORT.md`** in the mission folder is the final report file. The Stop hook requires it; `mission.py close --report FILE`
   copies a file there. The contract did not name the file.
6. **`close` reads capability calls from `calls` or from `--transcript FILE`** (explicit argument); it never searches
   `~/.claude/projects` by itself, to stay inside the read perimeter of the contract.
7. **`scan_capabilities.py` reads outside the two data folders** by design (skills, agents, plugin records,
   MCP server names in `~/.claude.json`/`.mcp.json`). It parses only names/keys, never commands, urls, headers or env.
8. Hooks, like the other scripts, accept `--help` (printed without reading stdin).
9. `CONTRAT.md` itself contains a local absolute path and is the orchestrator's file; it must not be shipped with the plugin.

## 5. Behaviour worth knowing

- Stop hook only acts when `exec_session_id` equals the hook's `session_id`. A `/clear` or a resume that changes the id
  detaches the mission (hooks silent); `mission.py start <slug> --reattach` moves it to the new id. UNVERIFIED: whether
  `--resume` keeps the id.
- Because `transcript_path` can lag by a turn (fact 14), a capability called in the very last turn can be missed once; the
  counter in `calls` remembers earlier ones and the hook gives way after 3 blocks.
- The Stop hook does not gate when the last assistant message ends with "?" (Claude is waiting for the user).
- Verification commands from STATE.json run through the shell (`shell=True`) because they are command lines
  (`pytest -q`, `npm test`). Mitigations: only for the exact executing session; refused when they match a
  destructive or networked pattern (`git push`, `rm -r`, `curl`, `ssh`, `sudo`, pipes to a shell...); first word
  must exist on PATH (localised "command not found" messages cannot be trusted); 120 s each, 240 s total.
- H1 never blocks and never orders; it adds one line saying a command exists. Slash commands, waiver phrases,
  mentions of the skill, a framing in progress and a 15-minute per-session cooldown silence it.

## 6. Measurements

Hook H1 (`hook_suggest.py`), threshold 3, English and French, accents ignored, file paths stripped before scoring:
- Synthetic set `tests/hook_suggest_cases.json` (108 prompts, 60 that must NOT trigger = 56 %, written before the
  scorer; two of its cases were used to adjust the scorer afterwards, so treat 100 % as optimistic):
  recall 100 % (48/48), false positives 0/60.
- Private set of 30 real prompts (read for measurement only, nothing copied): precision 87.5 % (21/24), recall 100 %
  (21/21). The previous shell hook scored 87.5 % / 100 % on the same set. The 3 false positives are ordinary
  long requests that mention words such as "complete" or "analysis"; they were not tuned away to avoid overfitting.

Unit tests: `py -3 -m unittest discover -s tests` (stdlib only), 81 tests. See the build report for the final counts per
interpreter (3.12 / 3.13 / 3.14). Python 3.8-3.11 were NOT run; the code was only parsed with
`ast.parse(feature_version=(3, 8))`.

## 7. Still UNVERIFIED / NOT TESTED

- Real loading of the plugin by Claude Code (`claude --plugin-dir`) and a real `claude --bg` launch: not run (quota).
  `claude plugin validate .` passes (see build report).
- macOS and Linux: hook chain, `sh -c`, stub `python3`, file modes. Windows PowerShell 5.1 without Git Bash.
- Minimum Claude Code version for `--bg`; exact string the `Skill` tool receives for a plugin skill (counting compares
  the part after the last colon, so both `dataviz` and `plugin:dataviz` match); session id stability across `--resume`.
- Python 3.8-3.11 execution.
- Behaviour of subagent-made calls: a capability called inside a subagent shows as an `Agent` call in the main
  transcript, not as the tool the subagent used.

## 8. Names to use in the skill text

- User invocation: `/super-reprompt:super-reprompt` (bare `/super-reprompt` only if no other command has that name).
- Agents (Agent tool `subagent_type`): `super-reprompt:reprompt-scout`, `super-reprompt:reprompt-reviewer`, `super-reprompt:reprompt-reader`.
- Script call from the skill body: `<PY> "${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py" <args>`, with `<PY>` the first of
  `python3`, `py -3`, `python` that answers - and beware: on Windows `python3`/`python` can be Store stubs that print
  "not found" and exit non-zero, so test with `<PY> --version` and use the first that exits 0.
- The reader agent answers four questions (goal and audience; deliverable and where; how to know it is done; limits and
  gaps); the reviewer receives ORDRE.md, STATE.json and a checklist from the caller.

## 9. Platform budgets the loading sits inside (Skills docs, read 2026-10-26)

Platform limits, not this plugin's starting values; they justify keeping SKILL.md small with its triggers first.

- Compaction re-attachment: Claude Code keeps the first 5000 tokens of each invoked skill after a summary, within a
  combined 25000-token budget across skills. SKILL.md here is ~3900 tokens, so all of it (six rules first) survives one
  compaction; references are re-read from disk by the phase logic and hook H2 re-injects the essentials. Keep SKILL.md
  under 5000 tokens. (Source S3-34.)
- Skill-listing budget: the name+description listing that drives triggering is capped at ~1% of the model's context
  window; on overflow Claude Code drops the least-invoked skills' descriptions first. The description here is ~670 chars
  (cap 1536) with triggers in the first sentence. Users with many skills check `/context` and `/skill-doctor`. (S3-59.)

## 10. New unverified items (added with the corpus pass, 2026-10-26)

- **H11 — CONFIRMED in real execution (2026-10-26).** A sub-agent spawned from the main conversation runs in the
  background and hands its report back via a completion notification in a *later* turn, framed by the harness as data
  that carries no user authority — not inside the spawning tool call (matches S5-31/S5-33/S5-37). So the framing spans
  several turns by construction. `agents.md` already says to wait for the report before the next phase and to treat it as
  data; no change needed there. Cost data point: one trivial read-only sub-agent used ~107 k tokens — a single sub-agent
  is not cheap, which supports the "costs several times a single session" framing in `agents.md`.
- **H12 — resolved by reasoning + the H11 observation (full interactive confirmation still pending).** `allowed-tools`
  is scoped to the turn that invokes the skill and clears on the next message (S3-35). Because P5/P7 use sub-agents that
  return in a later turn (H11), the grant is gone well before `mission.py ready`, so most script calls after turn 1 go
  through the normal permission prompt in `default` mode. This is not a bug; README "Known limits" now explains it and
  offers a settings allow-rule or `acceptEdits` to silence the prompts. A full live confirmation needs the loaded plugin
  driven through P0→P7 interactively.
- `omitClaudeMd` on the reader agent needs Claude Code >= 2.1.271 and is ignored WITHOUT error below it (S5-08), so the
  cold reader would silently get CLAUDE.md. README now states the minimum version.
