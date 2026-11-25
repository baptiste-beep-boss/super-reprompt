# -*- coding: utf-8 -*-
"""Mission reelle du lot 5 V3.1 : le Relais par le contrat ProviderAdapter, contre de faux fournisseurs OpenAI-compatibles
sur 127.0.0.1 (aucun fournisseur externe n'est connecte, aucun reseau sortant). Le faux serveur est celui des tests du
Relais, charge par importlib comme le fait dev/bench_guard.py (le reseau reste hors de dev/, invariant I2).
Etapes : health_check du contrat ; `relais run` delegue via l'adaptateur ; panne d'un fournisseur -> le suivant ;
panne de tous -> repli fini vers Claude (Haiku) ; mode sans fournisseur -> garde locale ; tache qui executerait du code
du modele -> refusee faute de vrai bac a sable, meme avec --exec. Usage : py -3 dev/mission_lot5.py -> 0 si tout passe."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "net"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_spec = importlib.util.spec_from_file_location("tr", os.path.join(ROOT, "tests", "test_relais.py"))
tr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tr)
import adapters as A  # noqa: E402
import relais  # noqa: E402

RELAIS = os.path.join(ROOT, "net", "relais.py")
OK = []


def check(label, cond):
    OK.append(bool(cond))
    print("[%s] %s" % ("PASS" if cond else "FAIL", label))


def main():
    tmp = tempfile.mkdtemp(prefix="sr lot5 é ")
    md = os.path.join(tmp, ".super-reprompt", "essai")
    os.makedirs(md)
    with open(os.path.join(md, "SCELLE.json"), "w", encoding="utf-8") as f:
        json.dump({"color": "vert", "red": []}, f)
    src = os.path.join(tmp, "journal.log")
    with open(src, "w", encoding="utf-8") as f:
        f.write(tr.BIG)
    env = dict(os.environ, RELAIS_HOME=os.path.join(tmp, "home"), PYTHONIOENCODING="utf-8")
    servers = []

    def srv(**kw):
        s = tr.FakeServer(**kw)
        servers.append(s)
        return s

    def run(provs, *extra, task="commit"):
        pf = tr.providers_file(tmp, provs)
        p = subprocess.run([sys.executable, RELAIS, "run", "--task", task, "--in", src, "--out", os.path.join(tmp, "out.txt"),
                            "--providers", pf, "--color", "vert"] + list(extra), cwd=tmp, env=env, capture_output=True, text=True, timeout=180)
        print("$ relais run --task %s (%d fournisseur(s)) -> code %d : %s" % (task, len(provs), p.returncode,
                                                                            " | ".join((p.stdout + p.stderr).strip().splitlines()[:2])[:220]))
        return p
    try:
        ok = srv()
        h = A.adapter_for(tr.provider("alpha", ok.url), excluded=relais.load_providers()["excluded"]).health_check(timeout=20)
        print("  health_check alpha :", h)
        check("contrat : health_check d'un fournisseur sain (ok, latence mesuree)", h["ok"] and h["latency_ms"] is not None)
        down = A.adapter_for(tr.provider("mort", "http://127.0.0.1:9/v1"), excluded=relais.load_providers()["excluded"]).health_check(timeout=3)
        check("contrat : health_check d'un fournisseur injoignable -> faux, classe d'erreur (%s)" % down["error_class"], not down["ok"] and down["error_class"])

        p = run([tr.provider("alpha", ok.url)])
        check("relais run delegue via l'adaptateur : OK et sortie ecrite", p.returncode == 0 and p.stdout.startswith("OK commit | alpha/m1"))
        bad = srv(mode="500")
        p = run([tr.provider("beta", bad.url), tr.provider("alpha", ok.url)])
        check("deux fournisseurs dont un en panne (HTTP 500) : la mission continue (ordre decide par le score ; bascule prouvee par l essai suivant et test_a14)", p.returncode == 0 and "alpha" in p.stdout)
        p = run([tr.provider("beta", bad.url), tr.provider("gamma", srv(mode="429").url)])
        check("panne de tous -> repli fini vers Claude (code 3, Haiku), jamais de boucle", p.returncode == 3 and "haiku" in (p.stdout + p.stderr).lower())
        p = run([])
        check("mode sans fournisseur : garde locale, aucune fausse delegation", p.returncode != 0 and "OK commit" not in p.stdout)
        code_srv = srv(answer=lambda b: json.dumps({"code": "print(1)"}))
        p = run([tr.provider("alpha", code_srv.url)], "--spec", json.dumps({"kind": "script", "stdin": "", "stdout": "1\n"}), "--exec", task="regex_sql_script")
        check("code produit par un modele : refuse meme avec --exec (aucun vrai bac a sable), rien envoye",
              p.returncode == 2 and "bac a sable" in p.stdout and code_srv.seen == [])
        import sqlite3
        con = sqlite3.connect(os.path.join(md, "ledger.sqlite"))
        rows = con.execute("select provider, verdict from relais").fetchall()
        con.close()
        print("  registre :", rows)
        check("chaque tentative et verdict trace dans le registre du Relais (dossier de mission)",
              len(rows) >= 4 and {"alpha", "beta", "gamma"} <= {r[0] for r in rows})
    finally:
        for s in servers:
            s.close()
        shutil.rmtree(tmp, ignore_errors=True)
    print("BILAN : %d/%d verifications" % (sum(OK), len(OK)))
    return 0 if all(OK) else 1


if __name__ == "__main__":
    sys.exit(main())
