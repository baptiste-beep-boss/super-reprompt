# super-reprompt

A Claude Code plugin that **frames a large request before work starts**. Instead of running a vague or sprawling prompt
as it is, it interviews you, writes a mission order (goal, deliverable, acceptance criteria, verification, which tools
to use, what it will cost), has it reviewed by independent agents, and launches the work in a fresh session that follows
the order and checks its own results.

The skill text is in `skills/super-reprompt/`. This README covers the mechanics: what gets installed, how to switch
parts off, what is stored where, and the known limits.

## Requirements

- Claude Code **2.1.271 or newer**: the `reprompt-reader` agent uses the `omitClaudeMd` frontmatter field, which that
  version added. On an older version the field is **ignored without any error**, so the cold reader would receive your
  CLAUDE.md files and no longer judge the order from `ORDRE.md` alone. Other version-gated behaviours the plugin relies on:
  `maxTurns` partial-result marking (2.1.246) and the launch `--bg` option (2.1.212). Tested with 2.1.266 on Windows.
- Python 3.8 or newer on your PATH as `python3`, `py -3` or `python`. Standard library only, nothing to `pip install`.
- On Windows, Git for Windows (Git Bash) is recommended, as for Claude Code itself.

## Install

One line inside a Claude Code session (2.1.275 or later):

    /plugin install super-reprompt --marketplace baptiste-beep-boss/super-reprompt

Or from your shell:

    claude plugin marketplace add baptiste-beep-boss/super-reprompt
    claude plugin install super-reprompt@super-reprompt

To try it for one session without installing anything, from the folder that contains this plugin's directory:

    claude --plugin-dir ./super-reprompt

Run `claude plugin validate <plugin folder>` to check the files. The project README is one level up, and the
measured results are in `evals/RESULTS.md`.

Start the skill with `/super-reprompt:super-reprompt` followed by what you want done.

After installing, three one-off checks are worth running: `claude plugin validate <plugin folder>` (frontmatter parses),
`/doctor prompt-audit` (flags instructions written for older models and clashes with your own CLAUDE.md), and
`/skill-doctor` (shows what each installed skill costs in context and how often it fires). If you have many skills
installed, the slash-command listing drops the least-used descriptions to fit a budget of about 1% of the model's context
window; this skill keeps its trigger words in the first sentence of its description so it stays discoverable, but check
with `/context` if it stops triggering.

## What the plugin installs

| Part | What it does |
|---|---|
| Skill `super-reprompt` | The framing procedure (interview, order, review, launch). |
| Agents `reprompt-scout`, `reprompt-reviewer`, `reprompt-reader` | Read-only helpers: a project scout, an adversarial reviewer, and a cold reader who must understand the order from the file alone. Full names: `super-reprompt:reprompt-scout`, etc. |
| Hook **H1** (UserPromptSubmit) | If your prompt looks like a large multi-part task, adds one line saying the skill exists. It never blocks and never decides for you. Silent for short prompts, questions, edits, acknowledgements, slash commands, and for 15 minutes after a suggestion. When the session transcript file is large (size only; its content is never read), the line adds that framing in a long conversation costs more and that `/clear` first is cheaper. |
| Hook **H2** (SessionStart: `compact`, `resume`) | If the session is working on a mission, re-injects a short reminder (about 400 tokens: file paths, budget left, six rules) after the conversation is compacted or resumed. Otherwise silent. |
| Hook **H3** (Stop) | Only for a session that is **executing** a mission: runs the verification commands the order declared, checks that every required tool was really called and that `REPORT.md` exists. If something is missing it asks Claude to continue, at most 3 times, then lets it stop and notes "not executable: ..." in `NOTES.md`. Silent for every other session. |
| `scripts/` | `scan_capabilities.py`, `validate_order.py`, `mission.py`, `launch.py` and the hook scripts. Python, no network. Each one answers `--help`. |

The hooks never call a model and cost no usage by themselves. The skill and the agents do use your normal Claude usage.

## Turning things off

- All three hooks: set the environment variable `SUPER_REPROMPT_HOOKS=0` (for example in your shell profile, or in the `env`
  section of Claude Code's `settings.json`). Hooks then exit immediately and print nothing.
- Everything: `claude plugin disable super-reprompt` (or `/plugin`).
- If you already have your own hook that suggests the same thing, disable one of them to avoid double suggestions.

## Uninstall

    claude plugin uninstall super-reprompt

Claude Code deletes the plugin files. The plugin's own data stays until you remove it:

- `~/.claude/super-reprompt/` - optional `profile.md`, `hook.log`, small cooldown files under `state/`. Delete the folder.
- `<project>/.super-reprompt/` - one folder per mission (order, state, notes, report). Delete it when you no longer need it.

## Your profile (optional)

Copy `profile-example/profile.md` to `~/.claude/super-reprompt/profile.md` (all projects) or to
`<project>/.claude/super-reprompt/profile.md` (one project, takes precedence) and edit it: your language, how much
explanation you want, tools you have, things that must never be done. At most about 1000 tokens are read. Do not put
passwords, API keys or tokens in it.

## What is stored, and privacy

- Nothing is sent anywhere by the plugin. The scripts contain no network code.
- `hook.log` (rotated at 200 KB) holds timestamps, which hook ran and short labels such as the suggestion score. It does not store your prompt.
- Mission files live in your project under `.super-reprompt/<slug>/` (`ORDRE.md`, `STATE.json`, `NOTES.md`, `REPORT.md`).
  Decide whether to commit or ignore that folder; do not put secrets in it. `validate_order.py` refuses files that contain
  something that looks like an API key or token.
- `scan_capabilities.py` reads the names and descriptions of your skills and agents, and the **names** of your MCP servers.
  It does not read their commands, addresses, headers or environment values. It also lists the servers bundled in enabled
  plugins and flags each server `disabled` or `needs_approval`; claude.ai connectors are not on disk and are visible only in the session.
- H3 runs the verification commands written in the order, through your shell, in your project folder. It refuses commands
  that look destructive or networked (`git push`, `rm -r`, `curl`, `ssh`, `sudo`, pipes into a shell...). Read section 6 of
  your order before you launch it: those are the commands that will run.

## Non-interactive use

- In print mode (`claude -p`) a permission request becomes a refusal, so a plugin skill needs
  `--allowedTools "Skill(super-reprompt:super-reprompt)"`.
- A deny rule `Skill(super-reprompt)` also blocks the plugin skill (observed: matching is by prefix).
- If a user skill with the short name `super-reprompt` is installed, it can mask the plugin skill when the plugin call fails.
  Uninstall one of the two, or always call the full name `super-reprompt:super-reprompt`.

## Known limits

- The hooks use `python3`, then `py -3`, then `python`, and exit silently if none works. Tested on Windows (Git Bash and
  PowerShell 7) only; macOS and Linux are not tested. Windows PowerShell 5.1 without Git Bash is not supported.
- On a Mac without developer tools, the system `python3` stub may offer to install them the first time a hook runs.
- The suggestion hook is a keyword scorer: it can miss a large request phrased in plain words, and can suggest framing for a
  long request that did not need it. Say "go direct" (or "sans cadrage", "no framing") to skip framing.
- H3 reads the session transcript, which Claude Code writes slightly behind the conversation; a tool called in the very last
  turn can be counted late. That is why H3 gives way after 3 blocks.
- `launch.py` needs `claude` with the `--bg` option. Without it, it prints the manual steps instead (exit code 3). `claude --bg`
  asks you to trust the folder first when run interactively and exits if it cannot ask.
- A background mission session uses your Claude usage like any other session. The order shows an estimate before you launch.
- **Script approval prompts during framing.** The `allowed-tools` grant in the skill's frontmatter only pre-approves its
  Python scripts for the single turn that invokes the skill, and clears on your next message (Claude Code behaviour). The
  framing spans several turns — the review and reader agents hand their reports back in a later turn — so after the first
  turn, calls like `scan_capabilities.py`, `validate_order.py` and `mission.py ready` go through the normal permission
  prompt in `default` mode. This is expected; approve them, or silence them for the session by running framing in
  `acceptEdits` mode, or by adding a persistent allow rule to your settings:

      // ~/.claude/settings.json  →  "permissions": { "allow": [ ... ] }
      "Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)",
      "Bash(py -3 ${CLAUDE_PLUGIN_ROOT}/scripts/*)",
      "Bash(python ${CLAUDE_PLUGIN_ROOT}/scripts/*)"

  The scripts are read-mostly and stdlib-only (they create and edit files only under `.super-reprompt/<slug>/`), so a
  blanket allow is low-risk; review `scripts/` before adding it if you prefer.

## Development

    py -3 -m unittest discover -s tests          (Windows)
    python3 -m unittest discover -s tests        (macOS / Linux)

`dev/NOTES-CONSTRUCTION.md` lists the documentation facts the mechanics rely on and what is still unverified.

`evals/CRITICAL-FAILURES.md` lists the failures no good score can offset (and the router error metric) and how to spot each one in a transcript.
