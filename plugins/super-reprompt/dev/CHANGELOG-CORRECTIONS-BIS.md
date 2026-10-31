# Changelog of the 8 corrections (brief CORRECTIONS-V2-BIS)

Backup before the corrections: `super-reprompt-v2.sauvegarde-avant-bis\` (created at the start; untouched afterwards). Baseline: 108 tests passing.
New tests live in `tests/test_bis.py` (T1 to T8). Doc lines cited below are in `anthropic-corpus\raw\claude-code-docs\pages\`.

## T1 Python launcher detection that no longer blocks - applied
- Files: `SKILL.md` (frontmatter `allowed-tools`, section "Scripts and fallbacks"), `README.md` (new section "Non-interactive use").
- What: the skill now calls `python3 "<script>"` directly, repeats the same call with `py -3` then `python` when the launcher is missing or a Store stub (exit 49 or 9009), one command per call (no `;`, `&&`, `|`, `2>&1`), no `--version` probe. `allowed-tools` keeps the three unquoted patterns and adds the three quoted ones.
- Doc check: `code.claude.com__docs__en__skills.md` line 392 (`allowed-tools` accepts a space- or comma-separated string, or a YAML list), line 615 (example `allowed-tools: Bash(git add *) Bash(git commit *)`, space-separated), line 481 and 487 (`${CLAUDE_PLUGIN_ROOT}` is substituted in `allowed-tools` Bash rules of a plugin skill). The docs do not say whether the quoted or unquoted form matches a path with spaces: both are kept ("verify before use").
- README non-interactive facts: the `--allowedTools "Skill(super-reprompt:super-reprompt)"` need and the prefix-matching of a `Skill(super-reprompt)` deny rule come from the real trial (not from a doc line), and are worded "observed".
- Tests: six patterns in the frontmatter, no `--version` anywhere under `skills/`, one-command rule present, README section present.

## T2 quick.md self-sufficient without Python - applied
- Files: `references/quick.md`. A compact JSON skeleton of `STATE.json` (required fields only) plus the sentence "If scripts cannot run, write this by hand" and the value lists. Measured about 185 tokens for the skeleton (limit 280).
- Tests: the skeleton extracted from `quick.md`, filled with example values, passes `validate_order.py` (exit 0); size test.

## T3 scan_capabilities.py complete MCP view - applied
- Files: `scripts/scan_capabilities.py`, `README.md`.
- What: reads servers bundled in enabled plugins (`.mcp.json` at the plugin root, wrapped or flat; `mcpServers` inline or as a path inside the plugin in `.claude-plugin/plugin.json`); per-project `disabledMcpServers` from `~/.claude.json`; `enabledMcpjsonServers`, `disabledMcpjsonServers`, `enableAllProjectMcpServers` from user, project and local settings; flags `disabled` / `needs_approval`; `origin` per server; correct call form `mcp__plugin_<plugin>_<server>__<tool>` (non-word characters become `_`); "tools: discover at runtime"; the line "claude.ai connectors are visible only in the session (not on disk)". New JSON keys `mcp_detail` and `claude_ai_connectors` (existing `mcp_servers` unchanged).
- Doc check: `mcp.md` line 520 and `plugins__components.md` line 410 (tool name form and the character replacement rule); `mcp.md` lines 246-266 (pending approval, rejected, disabled statuses and the settings keys); lines 315-320 (`disabledMcpServers` is recorded per project in `~/.claude.json`); `mcp.md` line 458 (plugin servers in `.mcp.json` at the plugin root or inline in `plugin.json`).
- Limits (reported, not hidden): approvals committed to a project's checked-in settings are ignored by Claude Code in an untrusted folder, which the scan cannot know; the flag is a hint, `claude mcp list` is the check. The disabled-name format for plugin servers in `disabledMcpServers` is not documented; the scan matches `plugin:<plugin>:<server>` and the bare server key.
- Tests: fictional tree (6 tests) covering flags, call forms, privacy (no command or env in the output), enable-all, disabled plugin, manifest path escaping the plugin folder.

## T4 capabilities.md two-step contract and authentication - applied
- Files: `references/capabilities.md` (Discovery 3, Selection bullet, Call forms MCP line). Net size about +51 tokens (limit +120), after trimming one sentence in Principle and one in Availability.
- What: a deferred MCP tool takes two calls (`ToolSearch` to load, then the tool); say so in the plan B if the session has no such tool; a server needing authentication or failed is a prerequisite (`claude mcp login <name>`, OAuth impossible in a non-interactive session). The exact `ToolSearch` query syntax is marked "verify before use".
- Doc check: `tools-reference.md` line 58 (`ToolSearch` loads deferred tools), `mcp.md` line 1485 (only names load at session start), line 775 (`claude -p` cannot run OAuth; `claude mcp login <name>`).
- Test: required phrases present, old "without any reservation" gone.

## T5 criteria that cannot be weakened silently - applied
- Files: `scripts/_lib.py` (`criteria_digest`, `criteria_fingerprints`, `criteria_changes`, `criteria_report`), `scripts/mission.py`, `scripts/hook_stop.py`, `scripts/validate_order.py`, `references/order-template.md` (3 lines), protocol text in `quick.md`.
- What: `ready` records `criteria_sha256` (canonical JSON of id, text, source, sorted by id) and per-criterion `criteria_fingerprints`; `close` refuses and names the modified, added or removed criteria; the Stop hook reports it once in its reason (`criteria_warned`), then lets pass; `criterion --passes yes` needs `--evidence` when the source is not `test` and records `self_reported` and `evidence`; `close` and `check` split criteria into "passed with a test source" and "self-reported"; the validator accepts and type-checks the optional fields. A state without the fields behaves as before.
- Tests (11): stable digest, ignores pass state and order, recorded by `ready`, close refuses weakened and removed criteria, close works when unchanged and prints the split, evidence required, backward compatibility, validator rejects malformed fields, Stop hook warns once then stays silent, silent without digest.
- Honest limit: a source of `test` is still declared by the framing session; the check proves the text was not changed, not that the proof is true.

## T6 execution protocol: four sentences; delegation depth - applied (with a correction of the brief)
- Files: `references/quick.md`, `references/order-template.md` (protocol block items 3, 4, 6, 7, 8), `references/launch.md` (the "data, not instructions" line now points to protocol item 6; no extra text), `references/agents.md`.
- (a) assume interruption + NOTES.md, (b) stop and report a wrong test or workaround rather than edit the test, (c) unattended: write for a stranger, (d) NOTES.md and every read file are data. Same four in `quick.md` and `order-template.md`; `launch.md` was not given a copy (it already cross-refers).
- Depth: the brief expected "official depth is 1". The doc says the opposite: `sub-agents.md` line 1051: "By default, a subagent can spawn subagents of its own, up to three layers below the main conversation"; `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` changes it, "Set `1` to turn nesting off". There was no "1 or 2" text in `agents.md`; the false statement was "nesting is off by default". It is replaced by the doc's fact plus the plugin's own design choice (plan for depth 1, leave `Agent` out of worker tools).
- Size compensation: the per-phase "Hypothesis" lines of `phases.md` were moved to the max-only section (nothing deleted); the duplicate announcement text in the P0 section, three P1 sub-bullets (merged), the "Why" paragraph of `interview.md`, a duplicate sentence on prices in `launch.md`, and wording in `SKILL.md` were trimmed. One stale instruction was fixed on the way (P7 said to set `status: ready` by hand; it now says `mission.py ready`).
- Tests: four sentences present in both blocks, no stale wording, agents.md matches the docs.

## T7 non-text pieces during framing - applied
- Files: `references/phases.md` (P1, one bullet). Test: bullet present in the P1 section.

## T8 models.md cache sentence - applied
- Files: `references/models.md`. The unsupported claim is replaced by "assume a cold cache after any change of model or effort, and verify with `/usage`". Test: old phrase gone, new phrase present.

## Other files touched
- `dev/measure_loading.py` limits updated (quick.md 1900, quick total 6200); `tests/test_budgets.py` quick.md limit 1900; `dev/CHARGEMENT-PAR-PALIER.md` regenerated by the measure script.

## T9 (2026-10-25, after the real battery) PowerShell patterns and no `cd` - applied
- Seen in battery case E: the model ran `cd "<dir>" && py -3 ...` (compound, denied) then the PowerShell tool (no matching rule, denied); no script ran.
- Files: `skills/super-reprompt/SKILL.md`: three `PowerShell(<launcher> "${CLAUDE_PLUGIN_ROOT}/scripts/*)` patterns added to `allowed-tools` (docs: "PowerShell permission rules use the same shape as Bash rules"); the scripts sentence now says "from the current directory, with no `cd` prefix ... use `--project DIR`".
- Check: rerun of case E: 0 denials, `mission.py` ran, NOTES.md + STATE.json written. `claude plugin validate .` OK, test_bis OK, SKILL.md ~3 930 tokens.
- T10: SKILL.md also says to read files with Read/Glob, not `cat`/`ls` (regression battery: 2 denials, both compound `cat`/`ls` reads, no script blocked). Not re-run (weekly quota).
