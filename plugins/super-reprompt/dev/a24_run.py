# -*- coding: utf-8 -*-
"""A24 : lance les essais du banc comparatif en sessions Claude Code sans interface (`claude -p`), une par essai.

Isolation : chaque essai tourne avec CLAUDE_CONFIG_DIR pointe sur un dossier de configuration DEDIE (aucun hook,
aucun plugin, aucun CLAUDE.md personnel) ; seul le plugin du bras est charge, par --plugin-dir. Ce dossier doit
avoir ete connecte une fois par l'utilisateur lui-meme :  CLAUDE_CONFIG_DIR=<dossier> claude auth login
Dossier de travail vierge par essai, meme invite, meme modele et meme effort pour tous les bras.
Tokens : lus dans la sortie JSON de `claude -p` (usage reel, pas d'estimation).
Juge objectif : les tests caches du projet, executes sur le livrable copie hors du depot.

Usage : py -3 dev/a24_run.py --config-dir D --out O [--claude claude] [--arms nu,v25,v3] [--projects moyen,difficile]
        [--v25 <plugin 2.5>] [--v3 <plugin 3>] [--n 1] [--model sonnet] [--effort medium] [--dry-run]
Bibliotheque standard seulement. N'envoie rien d'autre que ce que `claude -p` envoie."""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
BANC = os.path.join(PLUGIN, "evals", "v3-a24")
INVITE = "Réalise le projet décrit dans ENONCE.md."
OUTILS = ["Read", "Write", "Edit", "Glob", "Grep", "Bash(py:*)", "Bash(python:*)", "Bash(python3:*)", "Bash(ls:*)"]


def run_trial(a, arm, projet, k):
    work = os.path.join(a.out, "%s-%s-%d" % (arm, projet, k))
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    shutil.copy(os.path.join(BANC, "projets", projet, "ENONCE.md"), work)
    cmd = [a.claude, "-p", INVITE, "--model", a.model, "--effort", a.effort, "--output-format", "json",
           "--strict-mcp-config", "--no-session-persistence", "--permission-mode", "acceptEdits",
           "--allowedTools"] + OUTILS + (["Agent"] if getattr(a, "agent_tool", False) else [])
    if arm == "v25":
        cmd += ["--plugin-dir", a.v25]
    elif arm == "v3":
        cmd += ["--plugin-dir", a.v3]
    elif arm == "v31":
        cmd += ["--plugin-dir", a.v31]
    elif arm == "v32":
        cmd += ["--plugin-dir", a.v32]
    env = dict(os.environ, CLAUDE_CONFIG_DIR=a.config_dir)
    if a.dry_run:
        return {"arm": arm, "projet": projet, "essai": k, "cmd": cmd}
    t = time.time()
    p = subprocess.run(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=a.timeout)
    dur = time.time() - t
    try:
        res = json.loads(p.stdout.decode("utf-8", "replace"))
    except ValueError:
        res = {"is_error": True, "result": p.stdout.decode("utf-8", "replace")[-500:] + p.stderr.decode("utf-8", "replace")[-500:]}
    tokens, sortie, cout, sous_agents = tokens_of(res)
    caches, echecs = hidden_tests_detail(work, projet)
    return {"arm": arm, "projet": projet, "essai": k, "erreur": bool(res.get("is_error")), "tours": res.get("num_turns"),
            "duree_s": round(dur), "tokens_total": tokens, "tokens_sortie": sortie, "cout_usd_equiv": cout,
            "sous_agents": sous_agents, "tests_caches": caches, "echecs": echecs, "fin": (res.get("result") or "")[:300]}


def tokens_of(res):
    """Tokens reels d'une sortie JSON de `claude -p`. `usage` ne couvre que le modele principal : les sous-agents ne figurent
    que dans `modelUsage` (constate le 27/11/2026 sur une sonde : 51 006 tokens Haiku absents de `usage`). On somme donc
    modelUsage quand il existe. `total_cost_usd` est un equivalent au tarif API (estimated), pas un debit sur l'abonnement."""
    mu = res.get("modelUsage") or {}
    if mu:
        keys = ("inputTokens", "cacheCreationInputTokens", "cacheReadInputTokens", "outputTokens")
        total = sum(int(v.get(k) or 0) for v in mu.values() for k in keys)
        out = sum(int(v.get("outputTokens") or 0) for v in mu.values())
    else:
        u = res.get("usage") or {}
        total = sum(int(u.get(x) or 0) for x in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
        out = int(u.get("output_tokens") or 0)
    spawned = int((res.get("subagent_stats") or {}).get("spawned") or 0)
    cost = res.get("total_cost_usd")
    return total, out, (round(float(cost), 4) if cost is not None else None), spawned


def hidden_tests(work, projet):
    return hidden_tests_detail(work, projet)[0]


def hidden_tests_detail(work, projet):
    """Copie le livrable hors du depot, y pose les tests caches, les execute ; rend ('reussis/total', [tests en echec])."""
    juge = work + "-juge"
    shutil.rmtree(juge, ignore_errors=True)
    shutil.copytree(work, juge, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    src = os.path.join(BANC, "projets", projet, "caches")
    for f in os.listdir(src):
        shutil.copy(os.path.join(src, f), juge)
    p = subprocess.run([sys.executable, "-m", "unittest", "-v"] + [f[:-3] for f in os.listdir(src) if f.endswith(".py")],
                       cwd=juge, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
    out = p.stdout.decode("utf-8", "replace")
    total = out.count(" ... ")
    ok = out.count(" ... ok")
    echecs = re.findall(r"^(test_\w+) \(.*?\.\.\. (?:FAIL|ERROR)", out, re.M)
    return "%d/%d" % (ok, total), echecs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--claude", default="claude")
    ap.add_argument("--arms", default="nu,v25,v3")
    ap.add_argument("--projects", default="moyen,difficile")
    ap.add_argument("--v25", default="")
    ap.add_argument("--v3", default=PLUGIN)
    ap.add_argument("--v31", default="", help="plugin V3.1 (lot 10) pour le bras v31")
    ap.add_argument("--v32", default=PLUGIN, help="plugin avec le declencheur de code (lot 11) pour le bras v32")
    ap.add_argument("--agent-tool", action="store_true", help="autorise l'outil Agent dans TOUS les bras")
    ap.add_argument("--start", type=int, default=1, help="numero de la premiere repetition")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    a.claude = shutil.which(a.claude) or a.claude      # Windows : claude.cmd
    arms = a.arms.split(",")
    if "v25" in arms and not os.path.isdir(a.v25):
        ap.error("--v25 : dossier du plugin 2.5 introuvable")
    chk = subprocess.run([sys.executable, os.path.join(HERE, "a24_manifest.py"), "--check"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if chk.returncode != 0:
        print(chk.stdout.decode("utf-8", "replace"))
        sys.exit("empreintes du banc invalides : comparaison refusee")
    if "v31" in arms and not os.path.isdir(a.v31):
        ap.error("--v31 : dossier du plugin V3.1 introuvable")
    os.makedirs(a.out, exist_ok=True)
    journal = os.path.join(a.out, "journal.jsonl")
    done = set()
    if os.path.isfile(journal):
        with open(journal, encoding="utf-8") as f:
            for ln in f:
                if ln.strip():
                    d = json.loads(ln)
                    done.add((d["arm"], d["projet"], d["essai"]))
    for k in range(a.start, a.start + a.n):
        for projet in a.projects.split(","):
            for arm in arms:
                if (arm, projet, k) in done:
                    continue                      # reprise : un essai deja journalise n'est pas relance
                r = run_trial(a, arm, projet, k)
                if a.dry_run:                     # a blanc : jamais dans le journal, sinon la reprise le prendrait pour un essai fait
                    print(json.dumps(r, ensure_ascii=False)[:400], flush=True)
                    continue
                with open(journal, "a", encoding="utf-8") as f:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
                print(json.dumps(r, ensure_ascii=False)[:400], flush=True)


if __name__ == "__main__":
    main()
