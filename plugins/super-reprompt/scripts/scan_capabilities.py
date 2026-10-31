# -*- coding: utf-8 -*-
"""Index the capabilities available to Claude Code on this machine, in a small, deterministic digest.

Usage:  scan_capabilities.py [--project DIR] [--max-tokens 1500] [--json] [--claude-home DIR]

Reads, read-only: skill and agent front matter (user, project, installed and enabled plugins), the NAMES of
configured MCP servers (user, project .mcp.json, and servers bundled in enabled plugins; never their commands,
URLs, headers or environment) with a flag per server (disabled, needs_approval) and the call form, and whether a
super-reprompt profile exists. claude.ai connectors are not on disk and are never listed. Prints an index of at most --max-tokens tokens (estimated at 3.5 characters per token):
name, source, 120 characters of description, call form, flags, and a fingerprint of the whole set.
Missing sources only produce warnings on stderr; the exit code is 0. Same inputs give the same output.
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _lib as L  # noqa: E402
from pathlib import Path  # noqa: E402

CHARS_PER_TOKEN = 3.5
DESC_LEN = 120


def parse_frontmatter(text):
    """Minimal YAML front matter reader: top-level `key: value` plus folded/literal and indented continuation."""
    if not text.startswith("---"):
        return {}
    lines = text.replace("\r\n", "\n").split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}
    fm, key = {}, None
    for ln in lines[1:end]:
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", ln)
        if m and not ln.startswith((" ", "\t")):
            key, val = m.group(1), m.group(2).strip()
            if val in (">", "|", ">-", "|-", ">+", "|+"):
                fm[key] = ""
            else:
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                fm[key] = val
        elif key is not None and ln.startswith((" ", "\t")):
            fm[key] = (fm[key] + " " + ln.strip()).strip()
    return fm


def read_head(path, limit=16384):
    try:
        with open(str(path), "r", encoding="utf-8-sig", errors="replace") as f:
            return f.read(limit)
    except Exception:
        return ""


def short(text, n=DESC_LEN):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def skill_flags(fm):
    flags = []
    if str(fm.get("disable-model-invocation", "")).lower() == "true":
        flags.append("manual-only")
    if str(fm.get("user-invocable", "")).lower() == "false":
        flags.append("model-only")
    if str(fm.get("context", "")).lower() == "fork":
        flags.append("fork")
    return flags


def collect_skills(base, source, prefix=""):
    out = []
    try:
        dirs = sorted(p for p in Path(base).iterdir() if p.is_dir())
    except Exception:
        return out
    for d in dirs:
        f = d / "SKILL.md"
        if not f.is_file():
            continue
        fm = parse_frontmatter(read_head(f))
        name = (fm.get("name") or d.name).strip()
        full = (prefix + name) if prefix and not name.startswith(prefix) else name
        out.append({"kind": "skill", "name": full, "source": source, "description": short(fm.get("description", "")),
                    "call": "Skill(%s)" % full, "flags": skill_flags(fm)})
    return out


def collect_agents(base, source, prefix=""):
    out = []
    try:
        files = sorted(Path(base).rglob("*.md"))
    except Exception:
        return out
    for f in files:
        fm = parse_frontmatter(read_head(f))
        name = (fm.get("name") or "").strip()
        if not name or not fm.get("description"):
            continue
        full = prefix + name
        flags = []
        if fm.get("model"):
            flags.append("model=%s" % fm["model"])
        if fm.get("tools"):
            flags.append("tools-restricted")
        out.append({"kind": "agent", "name": full, "source": source, "description": short(fm.get("description", "")),
                    "call": "Agent(subagent_type=%s)" % full, "flags": flags})
    return out


def mcp_names(path_json, project_key=None):
    """Names of configured MCP servers in a JSON file. Never reads commands, urls, headers or env."""
    data = L.read_json(path_json, None)
    names = set()
    if not isinstance(data, dict):
        return names
    srv = data.get("mcpServers")
    if isinstance(srv, dict):
        names.update(str(k) for k in srv.keys())
    if project_key:
        proj = _project_entry(data, project_key)
        if isinstance(proj, dict) and isinstance(proj.get("mcpServers"), dict):
            names.update(str(x) for x in proj["mcpServers"].keys())
    return names


def _project_entry(data, project_key):
    projs = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projs, dict):
        return None
    want = os.path.normcase(os.path.normpath(project_key))
    for k, v in projs.items():
        try:
            if os.path.normcase(os.path.normpath(str(k))) == want and isinstance(v, dict):
                return v
        except Exception:
            continue
    return None


def safe_name(text):
    """Documented rule for MCP tool names: any character outside A-Z a-z 0-9 _ - becomes _."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(text))


def plugin_call_form(plugin, server):
    return "mcp__plugin_%s_%s__<tool>" % (safe_name(plugin), safe_name(server))


def plugin_mcp_names(root):
    """Names of the MCP servers a plugin bundles: .mcp.json at its root and mcpServers in plugin.json.
    Only names are read; a path in plugin.json must stay inside the plugin folder."""
    root = Path(root)
    names = set()

    def from_obj(obj):
        if not isinstance(obj, dict):
            return
        inner = obj.get("mcpServers")
        if isinstance(inner, dict):
            names.update(str(k) for k in inner.keys())
        elif "mcpServers" not in obj:
            names.update(str(k) for k, v in obj.items() if isinstance(v, dict))

    from_obj(L.read_json(root / ".mcp.json", None))
    manifest = L.read_json(root / ".claude-plugin" / "plugin.json", None)
    if isinstance(manifest, dict):
        decl = manifest.get("mcpServers")
        refs = decl if isinstance(decl, list) else [decl]
        for ref in refs:
            if isinstance(ref, dict):
                names.update(str(k) for k in ref.keys())
            elif isinstance(ref, str):
                try:
                    target = (root / ref).resolve()
                    if root.resolve() in target.parents and target.is_file():
                        from_obj(L.read_json(target, None))
                except Exception:
                    continue
    return names


def mcp_settings(project, claude_home):
    """Approval lists that decide whether a project .mcp.json server is usable."""
    out = {"enable_all": False, "enabled": set(), "disabled_json": set()}
    files = (claude_home / "settings.json", Path(project) / ".claude" / "settings.json",
             Path(project) / ".claude" / "settings.local.json")
    for f in files:
        d = L.read_json(f, None)
        if not isinstance(d, dict):
            continue
        if d.get("enableAllProjectMcpServers") is True:
            out["enable_all"] = True
        for key, dest in (("enabledMcpjsonServers", "enabled"), ("disabledMcpjsonServers", "disabled_json")):
            if isinstance(d.get(key), list):
                out[dest].update(str(x) for x in d[key])
    return out


def disabled_mcp(project, claude_home):
    """Per-project disabledMcpServers list recorded in ~/.claude.json by the /mcp toggle."""
    res = set()
    home = Path(os.path.expanduser("~"))
    for cand in {home / ".claude.json", claude_home / ".claude.json"}:
        data = L.read_json(cand, None) if cand.is_file() else None
        proj = _project_entry(data, str(project))
        if isinstance(proj, dict) and isinstance(proj.get("disabledMcpServers"), list):
            res.update(str(x) for x in proj["disabledMcpServers"])
    return res


def profile_info(path):
    p = Path(path)
    if not p.is_file():
        return None
    fm = parse_frontmatter(read_head(p, 4096))
    keep = {k: fm[k] for k in ("level", "lang", "default_tier") if k in fm}
    return keep


def gather(project, claude_home, warnings):
    items = []
    user_skills = claude_home / "skills"
    if user_skills.is_dir():
        items += collect_skills(user_skills, "user")
    else:
        warnings.append("no user skills folder at %s" % user_skills)
    proj_skills = Path(project) / ".claude" / "skills"
    if proj_skills.is_dir():
        items += collect_skills(proj_skills, "project")
    for base, src in ((claude_home / "agents", "user"), (Path(project) / ".claude" / "agents", "project")):
        if base.is_dir():
            items += collect_agents(base, src)

    # plugins
    enabled = None
    settings = L.read_json(claude_home / "settings.json", None)
    if isinstance(settings, dict) and isinstance(settings.get("enabledPlugins"), dict):
        enabled = settings["enabledPlugins"]
    rec = L.read_json(claude_home / "plugins" / "installed_plugins.json", None)
    plugins_seen = 0
    plugin_mcp = []
    if isinstance(rec, dict) and isinstance(rec.get("plugins"), dict):
        for pid in sorted(rec["plugins"].keys()):
            if enabled is not None and enabled.get(pid) is False:
                continue
            entries = rec["plugins"][pid]
            if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
                continue
            root = entries[0].get("installPath")
            if not root:
                continue
            pname = pid.split("@")[0]
            plugins_seen += 1
            items += collect_skills(Path(root) / "skills", "plugin:" + pid, prefix=pname + ":")
            items += collect_agents(Path(root) / "agents", "plugin:" + pid, prefix=pname + ":")
            for sn in sorted(plugin_mcp_names(root)):
                plugin_mcp.append((pid, pname, sn))
    else:
        warnings.append("no installed_plugins.json under %s: plugin skills and agents are not listed" % (claude_home / "plugins"))

    # mcp servers (names only, with flags)
    off = disabled_mcp(project, claude_home)
    cfg = mcp_settings(project, claude_home)
    home = Path(os.path.expanduser("~"))
    user_names = set()
    for cand in {home / ".claude.json", claude_home / ".claude.json"}:
        if cand.is_file():
            user_names |= mcp_names(cand, str(project))
    servers = {}
    for n in sorted(user_names):
        servers[n] = {"name": n, "origin": "user", "call": "mcp__%s__<tool>" % safe_name(n),
                      "flags": ["disabled"] if n in off else []}
    pm = Path(project) / ".mcp.json"
    if pm.is_file():
        for n in sorted(mcp_names(pm)):
            if n in servers:
                continue
            flags = []
            if n in off or n in cfg["disabled_json"]:
                flags.append("disabled")
            elif not (cfg["enable_all"] or n in cfg["enabled"]):
                flags.append("needs_approval")
            servers[n] = {"name": n, "origin": "project", "call": "mcp__%s__<tool>" % safe_name(n), "flags": flags}
    for pid, pname, sn in plugin_mcp:
        label = "plugin:%s:%s" % (pname, sn)
        flags = ["disabled"] if (label in off or sn in off) else []
        servers[label] = {"name": label, "origin": "plugin:" + pid, "call": plugin_call_form(pname, sn), "flags": flags}
    if not servers:
        warnings.append("no MCP server names found (checked ~/.claude.json, <project>/.mcp.json and enabled plugins)")
    for key in sorted(servers):
        sv = servers[key]
        items.append({"kind": "mcp", "name": sv["name"], "source": "mcp", "origin": sv["origin"], "description": "",
                      "call": sv["call"], "flags": sv["flags"], "tools": "discover at runtime"})
    return items, plugins_seen


SOURCE_RANK = {"user": 0, "project": 1, "mcp": 3}


def rank(it):
    s = it["source"]
    r = SOURCE_RANK.get(s, 2 if s.startswith("plugin:") else 4)
    kind_rank = {"skill": 0, "agent": 1, "mcp": 2}.get(it["kind"], 3)
    return (r, kind_rank, s, it["name"])


def fingerprint(items):
    h = hashlib.sha256()
    for it in sorted(items, key=rank):
        h.update(("%s|%s|%s|%s\n" % (it["kind"], it["source"], it["name"], it["description"])).encode("utf-8"))
    return h.hexdigest()[:8]


def item_line(it):
    flags = (" [" + ",".join(it["flags"]) + "]") if it["flags"] else ""
    desc = (": " + it["description"]) if it["description"] else ""
    return "- %s (%s)%s%s" % (it["name"], it["source"], desc, flags)


def prof_text(p):
    if p is None:
        return "none"
    return "found(%s)" % ",".join("%s=%s" % (k, v) for k, v in sorted(p.items())) if p else "found"


def plugin_summaries(items):
    """One summary per plugin: id, counts and the first skill names."""
    by = {}
    for it in items:
        if it["source"].startswith("plugin:"):
            by.setdefault(it["source"][7:], []).append(it)
    out = []
    for pid in sorted(by):
        its = sorted(by[pid], key=lambda x: (x["kind"], x["name"]))
        ns = sum(1 for x in its if x["kind"] == "skill")
        na = sum(1 for x in its if x["kind"] == "agent")
        names = []
        total = 0
        for x in its:
            nm = x["name"].split(":", 1)[-1] + ("*" if "manual-only" in x["flags"] else "")
            if total + len(nm) + 2 > 100:
                break
            names.append(nm)
            total += len(nm) + 2
        more = len(its) - len(names)
        line = "- plugin %s: %d skill(s), %d agent(s): %s%s" % (pid, ns, na, ", ".join(names), (" +%d more" % more) if more > 0 else "")
        out.append({"id": pid, "skills": ns, "agents": na, "names": names, "more": more, "line": line})
    return out


def build(items, profiles, max_tokens, plugins_seen):
    """Pick what fits in the budget. Priority: project items, MCP names, plugin summaries (at most 30% of the
    budget), then user items. Returns the pieces in print order."""
    fp = fingerprint(items)
    budget = int(max_tokens * CHARS_PER_TOKEN) - 140   # room for the trailing "omitted" line
    counts = {}
    for it in items:
        key = it["source"] if it["source"] in ("user", "project", "mcp") else "plugins"
        counts[key] = counts.get(key, 0) + 1
    head = ["CAPABILITIES INDEX v1 fingerprint=%s | user=%d project=%d plugin-items=%d (from %d plugin(s)) mcp=%d" % (
        fp, counts.get("user", 0), counts.get("project", 0), counts.get("plugins", 0), plugins_seen, counts.get("mcp", 0)),
        "profile: user=%s project=%s" % (prof_text(profiles["user"]), prof_text(profiles["project"])),
        "call forms: skill -> Skill(name); agent -> Agent(subagent_type=name); plugin items are prefixed <plugin>:; MCP -> mcp__<server>__<tool>; plugin MCP -> mcp__plugin_<plugin>_<server>__<tool> (tools: discover at runtime). '*' = manual-only",
        "claude.ai connectors are visible only in the session (not on disk); a server flagged disabled or needs_approval is a prerequisite, not a capability"]
    used = sum(len(x) + 1 for x in head)
    proj = sorted((x for x in items if x["source"] == "project"), key=rank)
    user = sorted((x for x in items if x["source"] == "user"), key=rank)
    mcp_items = sorted((x for x in items if x["source"] == "mcp"), key=lambda x: x["name"])
    mcp = [x["name"] for x in mcp_items]
    sel_proj, sel_user = [], []
    omitted = 0
    for it in proj:
        ln = len(item_line(it)) + 1
        if used + ln > budget:
            omitted += 1
            continue
        sel_proj.append(it)
        used += ln
    mcp_line = ""
    if mcp:
        mcp_line = "- mcp servers (names only): " + ", ".join(
            "%s[%s]" % (x["name"], ",".join([x.get("origin", "")] + x["flags"])) for x in mcp_items)
        if used + len(mcp_line) + 1 > budget:
            mcp_line = mcp_line[: max(0, budget - used - 4)] + "..."
        used += len(mcp_line) + 1
    summaries, omitted_plugins = [], 0
    plugin_cap = used + int(budget * 0.30)
    for sm in plugin_summaries(items):
        if used + len(sm["line"]) + 1 > min(budget, plugin_cap):
            omitted_plugins += 1
            continue
        summaries.append(sm)
        used += len(sm["line"]) + 1
    for it in user:
        ln = len(item_line(it)) + 1
        if used + ln > budget:
            omitted += 1
            continue
        sel_user.append(it)
        used += ln
    return head, sel_proj, sel_user, mcp, mcp_line, summaries, omitted, omitted_plugins, fp


def main(argv=None):
    L.setup_stdio()
    ap = argparse.ArgumentParser(description="Index available skills, agents and MCP servers in at most --max-tokens tokens.")
    ap.add_argument("--project", help="project directory (default: current directory)")
    ap.add_argument("--max-tokens", type=int, default=1500, help="size cap of the index in tokens (default 1500)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of text")
    ap.add_argument("--claude-home", help="Claude config folder (default: $CLAUDE_CONFIG_DIR or ~/.claude)")
    a = ap.parse_args(argv)
    if a.max_tokens < 100:
        sys.stderr.write("error: --max-tokens=%d is invalid. Valid: an integer >= 100\n" % a.max_tokens)
        return 2
    project = Path(a.project).resolve() if a.project else Path(os.getcwd()).resolve()
    claude_home = Path(a.claude_home) if a.claude_home else L.claude_home()
    warnings = []
    items, plugins_seen = gather(project, claude_home, warnings)
    profiles = {
        "user": profile_info(L.home_dir() / "profile.md"),
        "project": profile_info(project / ".claude" / "super-reprompt" / "profile.md"),
    }
    head, sel_proj, sel_user, mcp, mcp_line, summaries, omitted, omitted_plugins, fp = build(items, profiles, a.max_tokens, plugins_seen)
    for w in warnings:
        sys.stderr.write("warning: %s\n" % w)
    if a.json:
        print(json.dumps({"index_version": 1, "fingerprint": fp, "profile": profiles, "total": len(items),
                          "omitted_items": omitted, "omitted_plugins": omitted_plugins,
                          "items": sel_proj + sel_user, "mcp_servers": mcp,
                          "mcp_detail": [{"name": x["name"], "origin": x.get("origin"), "call": x["call"], "flags": x["flags"],
                                          "tools": x.get("tools")} for x in items if x["source"] == "mcp"],
                          "claude_ai_connectors": "visible only in the session, not on disk",
                          "plugins": [{k: v for k, v in sm.items() if k != "line"} for sm in summaries]},
                         ensure_ascii=False, indent=1))
        return 0
    lines = list(head) + [item_line(it) for it in sel_proj] + [item_line(it) for it in sel_user]
    if mcp_line:
        lines.append(mcp_line)
    lines += [sm["line"] for sm in summaries]
    if omitted or omitted_plugins:
        lines.append("(+%d item(s), +%d plugin(s) omitted for size; raise --max-tokens or use --json)" % (omitted, omitted_plugins))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
