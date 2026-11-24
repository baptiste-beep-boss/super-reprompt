# -*- coding: utf-8 -*-
"""Methode « contre-epreuve adverse », testee sur le banc A24 : trois sessions neuves par essai.
  1. Realisation : meme invite que les autres bras.
  2. Testeur adverse : contexte neuf, boite noire (enonce + module, consigne de ne pas lire le code), ecrit et lance
     test_adverse.py. Sa consigne est GENERIQUE : elle ne cite aucun cas de la batterie etendue (pas de fuite).
  3. Correcteur : contexte neuf, recoit les echecs, corrige le module si l'echec trahit un ecart a l'enonce,
     ecarte un test faux en le disant.
Meme isolation que a24_run.py (CLAUDE_CONFIG_DIR dedie, aucun plugin). Tokens = somme des trois sessions.
Usage : py -3 dev/a24_adverse.py --config-dir D --out O [--claude C] [--projects moyen,difficile] [--n 1]"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import a24_run as R  # noqa: E402

TESTEUR = ("Tu es testeur adverse, independant de l'auteur. Lis ENONCE.md. Le module livre est dans ce dossier : "
           "traite-le en boite noire, ne lis pas son code source. Ecris test_adverse.py (unittest, bibliotheque standard) "
           "qui cherche a le faire echouer sur tout ce que l'enonce exige : cas limites, entrees inhabituelles ou mal "
           "formees, chemins d'erreur, gros volumes avec un temps raisonnable. Chaque test doit decouler de l'enonce. "
           "Execute-le, puis termine par la liste des tests en echec, chacun avec l'exigence de l'enonce qu'il verifie.")
CORRECTEUR = ("Tu reprends ce projet (ENONCE.md, module et tests). Un testeur independant a ecrit test_adverse.py ; "
              "voici son rapport :\n\n%s\n\nPour chaque echec : si le module s'ecarte de l'enonce, corrige le module ; "
              "si le test lui-meme contredit l'enonce, ne le suis pas et dis pourquoi. Garde les tests existants verts, "
              "relance tous les tests a la fin et rends le bilan.")


def session(a, cwd, invite):
    cmd = [a.claude, "-p", invite, "--model", a.model, "--effort", a.effort, "--output-format", "json",
           "--strict-mcp-config", "--no-session-persistence", "--permission-mode", "acceptEdits", "--allowedTools"] + R.OUTILS
    env = dict(os.environ, CLAUDE_CONFIG_DIR=a.config_dir)
    p = subprocess.run(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=a.timeout)
    try:
        res = json.loads(p.stdout.decode("utf-8", "replace"))
    except ValueError:
        res = {"is_error": True, "result": p.stdout.decode("utf-8", "replace")[-400:]}
    u = res.get("usage") or {}
    tok = sum(int(u.get(x) or 0) for x in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
    return res, tok, int(u.get("output_tokens") or 0), res.get("num_turns") or 0


def trial(a, projet, k):
    work = os.path.join(a.out, "adverse-%s-%d" % (projet, k))
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    shutil.copy(os.path.join(R.BANC, "projets", projet, "ENONCE.md"), work)
    t = time.time()
    r1, t1, o1, n1 = session(a, work, R.INVITE)
    test_dir = work + "-testeur"
    shutil.rmtree(test_dir, ignore_errors=True)
    shutil.copytree(work, test_dir, ignore=shutil.ignore_patterns("test_*.py", "__pycache__", ".claude"))
    r2, t2, o2, n2 = session(a, test_dir, TESTEUR)
    if os.path.isfile(os.path.join(test_dir, "test_adverse.py")):
        shutil.copy(os.path.join(test_dir, "test_adverse.py"), work)
    r3, t3, o3, n3 = session(a, work, CORRECTEUR % (r2.get("result") or "(rapport vide)")[:6000])
    return {"arm": "adverse", "projet": projet, "essai": k, "erreur": any(bool(r.get("is_error")) for r in (r1, r2, r3)),
            "tours": n1 + n2 + n3, "duree_s": round(time.time() - t), "tokens_total": t1 + t2 + t3,
            "tokens_par_etape": [t1, t2, t3], "tokens_sortie": o1 + o2 + o3,
            "tests_caches": R.hidden_tests(work, projet), "fin": (r3.get("result") or "")[:300]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--claude", default="claude")
    ap.add_argument("--projects", default="moyen,difficile")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--timeout", type=int, default=1800)
    a = ap.parse_args()
    a.claude = shutil.which(a.claude) or a.claude
    os.makedirs(a.out, exist_ok=True)
    for k in range(a.start, a.start + a.n):
        for projet in a.projects.split(","):
            r = trial(a, projet, k)
            with open(os.path.join(a.out, "journal.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(json.dumps(r, ensure_ascii=False)[:300], flush=True)


if __name__ == "__main__":
    main()
