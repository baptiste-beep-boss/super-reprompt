# -*- coding: utf-8 -*-
"""Lot L6, Relais: gates, hard filters, score, circuit breaker, fallback, ledger, providers.json, key store, CLI.
Acceptance A13 (no secret / red content leaves), A14 (outage of one then all providers), A15 (excluded providers
unreachable), A16 (key invisible). Every network call goes to a fake OpenAI-compatible server on 127.0.0.1."""
import datetime
import http.server
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

from _t import ROOT

NET = os.path.join(ROOT, "net")
sys.path.insert(0, NET)
import relais  # noqa: E402
import connect  # noqa: E402

RELAIS = os.path.join(NET, "relais.py")
TODAY = datetime.date.today().isoformat()
BIG = ("Ligne de journal %04d : le service a repondu en 12 ms, aucune erreur.\n" * 120) % tuple(range(120))   # ~ 8 000 caracteres


# ------------------------------------------------------------------ fake provider
class FakeServer:
    """OpenAI-compatible /chat/completions. mode: ok | 429 | 500 | length | empty. answer(body) -> content string."""

    def __init__(self, mode="ok", answer=None):
        self.mode, self.answer, self.seen = mode, answer or (lambda b: json.dumps({"text": "feat(relais): ajoute le disjoncteur"})), []
        srv = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                srv.seen.append({"path": self.path, "headers": dict(self.headers), "body": ""})
                self.send_response(200)
                self.end_headers()

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(n).decode("utf-8")
                srv.seen.append({"path": self.path, "headers": dict(self.headers), "body": body})
                if srv.mode == "429":
                    self.send_response(429)
                    self.send_header("retry-after", "120")
                    self.end_headers()
                    return
                if srv.mode.startswith("redirect:"):
                    self.send_response(302)
                    self.send_header("Location", srv.mode[len("redirect:"):])
                    self.end_headers()
                    return
                if srv.mode == "500":
                    self.send_response(500)
                    self.end_headers()
                    return
                content = "" if srv.mode == "empty" else srv.answer(json.loads(body))
                fin = "length" if srv.mode == "length" else "stop"
                data = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": fin}],
                                   "usage": {"prompt_tokens": 2100, "completion_tokens": 40}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("x-ratelimit-remaining-tokens", "150000")
                self.send_header("x-ratelimit-limit-tokens", "200000")
                self.end_headers()
                self.wfile.write(data)

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d/v1" % self.port

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def provider(pid, url, access="none", max_color="orange", trains=False, **kw):
    p = {"id": pid, "name": pid, "base_url": url, "access": access, "max_color": max_color, "trains_on_data": trains, "tos": "ok",
         "country": "FR", "hard_stop": True, "payment_method": False, "enabled": True, "json_mode": True, "reasoning": {},
         "signup_url": "https://example.invalid/keys", "data_policy": "aucune retention (test)",
         "models": [{"id": "m1", "context": 32000, "limit_tokens_day": None}]}
    p.update(kw)
    return p


def providers_file(d, provs, updated=TODAY, excluded=None):
    path = os.path.join(d, "providers.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"schema": 1, "updated": updated, "expires_after_days": 30, "providers": provs,
                   "excluded": excluded if excluded is not None else relais.load_providers()["excluded"]}, f)
    return path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sr-relais-")
        self.home = os.path.join(self.tmp, "home")
        self.servers = []
        # green is a decision of the seal, never of the command line (review #5): tests run inside a sealed green mission
        self.mdir = os.path.join(self.tmp, ".super-reprompt", "essai")
        os.makedirs(self.mdir)
        with open(os.path.join(self.mdir, "SCELLE.json"), "w", encoding="utf-8") as f:
            json.dump({"color": "vert", "red": []}, f)

    def tearDown(self):
        for s in self.servers:
            s.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def server(self, **kw):
        s = FakeServer(**kw)
        self.servers.append(s)
        return s

    def file(self, name, text):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def env(self):
        e = dict(os.environ, RELAIS_HOME=self.home, PYTHONIOENCODING="utf-8")
        return e

    def cli(self, *args, cwd=None):
        p = subprocess.run([sys.executable, RELAIS] + list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           env=self.env(), cwd=cwd or self.tmp, timeout=120)
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


# ------------------------------------------------------------------ providers.json
class Providers(unittest.TestCase):
    def test_shipped_file_is_dated_and_expires_after_30_days(self):
        d = relais.load_providers()
        self.assertEqual(d["expires_after_days"], 30)
        datetime.date.fromisoformat(d["updated"])
        self.assertFalse(relais.load_providers(now=datetime.date.fromisoformat(d["updated"]) + datetime.timedelta(days=30))["expired"])
        self.assertTrue(relais.load_providers(now=datetime.date.fromisoformat(d["updated"]) + datetime.timedelta(days=31))["expired"])

    def test_unknown_limits_are_null_never_unlimited(self):
        raw = json.dumps(relais.load_providers()["providers"]).lower()
        for word in ("unlimited", "illimit", "infinity"):
            self.assertNotIn(word, raw)
        nulls = 0
        for p in relais.load_providers()["providers"]:
            for m in p["models"]:
                for k, v in m.items():
                    if k.startswith("limit_"):
                        self.assertTrue(v is None or (isinstance(v, int) and v > 0), (p["id"], k, v))
                        nulls += v is None
        self.assertGreater(nulls, 0)

    def test_cdc_table_present_and_ovh_cut(self):
        d = relais.load_providers()
        ids = {p["id"] for p in d["providers"]}
        for want in ("ovh", "codex", "groq", "mistral", "cloudflare", "gemini", "sambanova", "cohere", "openrouter", "nvidia"):
            self.assertIn(want, ids)
        ovh = [p for p in d["providers"] if p["id"] == "ovh"][0]
        self.assertFalse(ovh["enabled"])
        self.assertFalse([p for p in d["providers"] if p["id"] == "nvidia"][0]["enabled"])

    def test_a15_no_excluded_provider_is_listed_or_reachable(self):
        d = relais.load_providers()
        ex = d["excluded"]
        for want in ("cerebras", "github-models", "chutes", "ollama-cloud", "antigravity", "kiro", "duckduckgo", "t3", "fireworks", "modal"):
            self.assertIn(want, [e["id"] for e in ex])
        for p in d["providers"]:
            self.assertIsNone(relais.excluded_reason(p, ex), p["id"])
        # an excluded provider slipped into the list by name or by host is filtered out, and the client refuses its host
        bad = [provider("cerebras", "http://127.0.0.1:9/v1"), provider("sneaky", "https://api.cerebras.ai/v1"),
               provider("gh", "https://models.github.ai/inference")]
        elig, why = relais.eligible(bad, ex, color="vert", need_tokens=100, breaker=relais.Breaker({}), keys=lambda p: True)
        self.assertEqual(elig, [])
        self.assertEqual(len(why), 3)
        calls = []
        orig = relais._open
        relais._open = lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("connexion tentee"))
        try:
            for p in bad[1:]:
                with self.assertRaises(relais.Refused):
                    relais.call_provider(p, "m1", None, [{"role": "user", "content": "x"}], excluded=ex)
        finally:
            relais._open = orig
        self.assertEqual(calls, [])

    def test_plain_http_refused_except_loopback(self):
        with self.assertRaises(relais.Refused):
            relais.check_url("http://api.groq.com/openai/v1", [])
        relais.check_url("http://127.0.0.1:8080/v1", [])
        relais.check_url("https://api.groq.com/openai/v1", [])


# ------------------------------------------------------------------ gates
class Gates(unittest.TestCase):
    def test_red_project_is_refused(self):
        ok, _t, why = relais.privacy_gate("bonjour", "rouge", [], "notes.md")
        self.assertFalse(ok)
        self.assertIn("rouge", why)

    def test_red_file_is_refused_whatever_the_colour(self):
        ok, _t, why = relais.privacy_gate("bonjour", "vert", ["clients.csv"], os.path.join("data", "clients.csv"))
        self.assertFalse(ok)

    def test_secret_blocks_in_every_colour(self):
        key = "sk-" + secrets.token_hex(20)
        for c in ("vert", "orange"):
            ok, _t, why = relais.privacy_gate("cle = %s" % key, c, [], "a.txt")
            self.assertFalse(ok, c)
            self.assertIn("secret", why)
            self.assertNotIn(key, why)

    def test_secret_store_file_is_refused(self):
        self.assertFalse(relais.privacy_gate("A=1", "vert", [], ".env")[0])

    def test_orange_anonymises_and_restores(self):
        src = "Ecrire a jean.dupont@acme-corp.fr, voir C:\\Users\\jdupont\\projet\\x.py et https://intranet.acme-corp.fr/a ; jeton 9f8e7d6c5b4a39281706f5e4d3c2b1a0ffee"
        ok, anon, why = relais.privacy_gate(src, "orange", [], "a.txt")
        self.assertTrue(ok)
        for leak in ("jean.dupont", "acme-corp", "jdupont", "9f8e7d6c5b4a"):
            self.assertNotIn(leak, anon.text)
        self.assertEqual(anon.restore(anon.text), src)
        ok, plain, _w = relais.privacy_gate(src, "vert", [], "a.txt")
        self.assertEqual(plain.text, src)

    def test_utility_gate(self):
        self.assertFalse(relais.utility_gate(800, "resume")[0])      # under ~1 500 tokens: keep
        ok, why, n = relais.utility_gate(20000, "resume")
        self.assertTrue(ok)
        self.assertGreater(n["saved"], 3 * n["cost"])

    def test_never_delegated_keywords(self):
        self.assertIsNotNone(relais.never_reason("revoir l'architecture du module"))
        self.assertIsNotNone(relais.never_reason("choisir la cryptographie des jetons"))
        self.assertIsNone(relais.never_reason("resumer le journal de build"))


# ------------------------------------------------------------------ filters, score, breaker, fallback
class Routing(unittest.TestCase):
    def test_hard_filters_explain_each_exclusion(self):
        ex = relais.load_providers()["excluded"]
        ps = [provider("ok", "https://a.invalid/v1"), provider("trains", "https://b.invalid/v1", trains=True, max_color="vert"),
              provider("tos", "https://c.invalid/v1", tos="avoid"), provider("pay", "https://d.invalid/v1", hard_stop=False, payment_method=True),
              provider("small", "https://e.invalid/v1", models=[{"id": "m", "context": 1000, "limit_tokens_day": None}]),
              provider("off", "https://f.invalid/v1", enabled=False), provider("nokey", "https://g.invalid/v1", access="key")]
        elig, why = relais.eligible(ps, ex, color="orange", need_tokens=5000, breaker=relais.Breaker({}), keys=lambda p: p["id"] != "nokey")
        self.assertEqual([p["id"] for p, _m in elig], ["ok"])
        self.assertEqual(sorted(why), ["nokey", "off", "pay", "small", "tos", "trains"])
        elig, _w = relais.eligible(ps[:2], ex, color="vert", need_tokens=5000, breaker=relais.Breaker({}), keys=lambda p: True)
        self.assertEqual(len(elig), 2)            # vert: training providers allowed

    def test_score_is_explainable_and_uses_cdc_weights(self):
        self.assertEqual(relais.WEIGHTS, {"qualite": 0.35, "quota": 0.25, "sante": 0.15, "latence": 0.10, "contexte": 0.10, "diversite": 0.05})
        p = provider("a", "https://a.invalid/v1")
        total, comp = relais.score(p, p["models"][0], "resume", stats={"quality": {}, "quota": {}, "latency": {}, "last": None},
                                   breaker=relais.Breaker({}), need_tokens=2000)
        self.assertAlmostEqual(total, sum(relais.WEIGHTS[k] * v for k, v in comp.items()), places=6)
        self.assertEqual(comp["quota"], 0.5)      # unknown quota is neither full nor empty

    def test_breaker_three_states(self):
        t = [1000.0]
        b = relais.Breaker({}, clock=lambda: t[0])
        for _ in range(3):
            self.assertEqual(b.state("p"), "ferme")
            b.failure("p")
        self.assertEqual(b.state("p"), "ouvert")
        t[0] += relais.Breaker.COOLDOWN + 1
        self.assertEqual(b.state("p"), "demi-ouvert")
        b.failure("p")
        self.assertEqual(b.state("p"), "ouvert")
        t[0] += relais.Breaker.COOLDOWN + 1
        b.success("p")
        self.assertEqual(b.state("p"), "ferme")
        b.trip("p", 600)                       # a 429 opens it at once, for retry-after seconds
        self.assertEqual(b.state("p"), "ouvert")

    def test_fallback_chain_never_loops(self):
        self.assertEqual(relais.next_claude(None), "haiku")
        self.assertEqual(relais.next_claude("haiku"), "sonnet")
        self.assertIsNone(relais.next_claude("sonnet"))
        self.assertEqual(relais.MAX_FREE_ATTEMPTS, 2)

    def test_autotune_cuts_a_pair_over_15_percent_on_20_trials(self):
        d = tempfile.mkdtemp()
        try:
            led = relais.Ledger(os.path.join(d, "ledger.sqlite"))
            for i in range(20):
                led.add(slug="s", task="resume", provider="a", model="m1", tokens_in=10, tokens_out=1, duration_s=1,
                        verdict="OK" if i >= 4 else "VERIF", retouch=i < 4, avoided=10)
            self.assertIn(("resume", "a/m1"), led.cut_pairs())        # 4/20 = 20 % > 15 %
            led2 = relais.Ledger(os.path.join(d, "l2.sqlite"))
            for i in range(20):
                led2.add(slug="s", task="resume", provider="a", model="m1", tokens_in=10, tokens_out=1, duration_s=1,
                         verdict="OK" if i >= 3 else "VERIF", retouch=i < 3, avoided=10)
            self.assertEqual(led2.cut_pairs(), [])                    # 3/20 = 15 %: kept
            led.close()
            led2.close()
        finally:
            shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ end to end with the fake provider
class EndToEnd(Base):
    def setUp(self):
        super().setUp()
        self.src = self.file("journal.log", BIG)

    def run_commit(self, provs, *extra, src=None):
        pf = providers_file(self.tmp, provs)
        out = os.path.join(self.tmp, "out.txt")
        rc, so, se = self.cli("run", "--task", "commit", "--in", src or self.src, "--out", out, "--providers", pf, "--color", "vert", *extra)
        return rc, so, se, out

    def test_ok_receipt_is_at_most_6_lines_and_out_written(self):
        s = self.server()
        rc, so, se, out = self.run_commit([provider("alpha", s.url)])
        self.assertEqual(rc, 0, so + se)
        self.assertLessEqual(len(so.strip().splitlines()), 6)
        self.assertRegex(so, r"^OK commit \| alpha/m1 \| .* in .* out \| .* s \| verif: ")
        with open(out, encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("feat(relais)"))
        body = json.loads(s.seen[0]["body"])
        self.assertEqual(body["temperature"], 0)
        self.assertIn("max_tokens", body)

    def test_a14_one_provider_down_mission_continues(self):
        down, up = self.server(mode="500"), self.server()
        rc, so, se, _o = self.run_commit([provider("alpha", down.url), provider("beta", up.url, models=[{"id": "m1", "context": 16000, "limit_tokens_day": None}])])
        self.assertEqual(rc, 0, so + se)
        self.assertIn("beta/m1", so)
        self.assertIn("alpha", so)        # the failed attempt is reported

    def test_a14_all_providers_down_falls_back_to_haiku_then_sonnet(self):
        a, b = self.server(mode="500"), self.server(mode="429")
        provs = [provider("alpha", a.url), provider("beta", b.url)]
        rc, so, se, _o = self.run_commit(provs)
        self.assertEqual(rc, 3, so + se)
        self.assertTrue(so.startswith("REPLI haiku"), so)
        self.assertLessEqual(len(so.strip().splitlines()), 6)
        rc, so, _se, _o = self.run_commit(provs, "--after", "haiku")
        self.assertEqual(rc, 3)
        self.assertTrue(so.startswith("REPLI sonnet"), so)
        rc, so, _se, _o = self.run_commit(provs, "--after", "sonnet")
        self.assertEqual(rc, 4)
        self.assertTrue(so.startswith("ABANDON"), so)
        self.assertEqual(len(a.seen) + len(b.seen), 2)     # one call each in the first run, then the breakers / no retry

    def test_no_provider_at_all_falls_back_to_haiku(self):
        rc, so, _se, _o = self.run_commit([])
        self.assertEqual(rc, 3)
        self.assertIn("REPLI haiku", so)
        self.assertIn("aucun fournisseur", so)

    def test_truncated_or_empty_answer_is_a_failure(self):
        for mode in ("length", "empty"):
            s = self.server(mode=mode)
            rc, so, _se, _o = self.run_commit([provider("alpha", s.url)])
            self.assertEqual(rc, 3, mode)

    def test_bad_answer_fails_verification_and_is_ledgered(self):
        s = self.server(answer=lambda b: json.dumps({"text": "fixed stuff"}))
        rc, so, _se, _o = self.run_commit([provider("alpha", s.url)])
        self.assertEqual(rc, 3)
        con = sqlite3.connect(os.path.join(self.mdir, "ledger.sqlite"))     # sealed mission: ledger beside the seal (§3.4)
        rows = con.execute("select provider, verdict, retouch, claude_tokens_avoided_est from relais").fetchall()
        con.close()
        self.assertEqual(rows[0][:3], ("alpha", "VERIF", 1))

    def test_ledger_and_report(self):
        s = self.server()
        self.run_commit([provider("alpha", s.url)], "--slug", "demo")
        rc, so, _se = self.cli("report", "demo")
        self.assertEqual(rc, 0)
        self.assertIn("estim", so)
        self.assertIn("alpha/m1", so)

    def test_redirects_are_never_followed(self):
        target = self.server()
        hop = self.server(mode="redirect:" + target.url + "/chat/completions")
        rc, so, _se, _o = self.run_commit([provider("alpha", hop.url)])
        self.assertEqual(len(hop.seen), 1)
        self.assertEqual(target.seen, [], "a redirect was followed")
        self.assertEqual(rc, 3)

    def test_small_volume_is_kept(self):
        s = self.server()
        small = self.file("petit.txt", "deux lignes\n")
        rc, so, _se, _o = self.run_commit([provider("alpha", s.url)], src=small)
        self.assertEqual(rc, 2)
        self.assertIn("GARDE", so)
        self.assertEqual(s.seen, [])

    def test_key_is_never_an_argument(self):
        rc, so, se = self.cli("connect", "groq", "--key", "abc")
        self.assertNotEqual(rc, 0)
        rc, so, se = self.cli("run", "--help")
        self.assertNotIn("--key", so)

    def test_connect_refuses_without_a_terminal(self):
        rc, so, se = self.cli("connect", "groq")
        self.assertNotEqual(rc, 0)
        self.assertIn("terminal", so + se)

    def test_plan_classifies_each_task(self):
        plan = self.file("PLAN.json", json.dumps({"tasks": [
            {"id": "T1", "type": "resume", "text": "resumer le journal", "in": self.src},
            {"id": "T2", "type": "commit", "text": "choisir l'architecture", "in": self.src},
            {"id": "T3", "text": "ecrire le module de paiement"},
            {"id": "T4", "type": "resume", "text": "resumer", "volume_tokens": 300}]}))
        rc, so, _se = self.cli("plan", plan, "--color", "vert", "--providers", providers_file(self.tmp, []))
        self.assertEqual(rc, 0, so)
        lines = {l.split()[0]: l for l in so.splitlines() if l[:1] == "T"}
        self.assertIn("delegue", lines["T1"])
        self.assertIn("garde", lines["T2"])
        self.assertIn("garde", lines["T3"])
        self.assertIn("garde", lines["T4"])

    def test_batch_resumes_after_incident(self):
        s = self.server()
        pf = providers_file(self.tmp, [provider("alpha", s.url)])
        lot = self.file("lot.ndjson", "\n".join(json.dumps({"id": "L%d" % i, "task": "commit", "in": self.src if i != 1 else os.path.join(self.tmp, "absent.txt"),
                                                            "out": os.path.join(self.tmp, "o%d.txt" % i)}) for i in range(3)) + "\n")
        rc, so, _se = self.cli("batch", lot, "--providers", pf, "--color", "vert", "--parallel", "2")
        self.assertIn("L1", so)
        self.assertIn("INCIDENT", so)
        n1 = len(s.seen)
        rc, so, _se = self.cli("batch", lot, "--providers", pf, "--color", "vert")
        self.assertEqual(len(s.seen), n1)            # done items are not re-run
        self.assertIn("deja fait", so)

    def test_status_lists_providers_without_secrets(self):
        rc, so, _se = self.cli("status")
        self.assertEqual(rc, 0)
        self.assertIn("groq", so)
        self.assertIn("expire", so)

    def test_bench_scores_every_type_per_model(self):
        s = self.server()
        rc, so, _se = self.cli("bench", "--providers", providers_file(self.tmp, [provider("alpha", s.url)]), "--color", "vert")
        self.assertEqual(rc, 0, so)
        with open(os.path.join(self.home, "bench.json"), encoding="utf-8") as f:
            b = json.load(f)
        self.assertEqual(len(b["scores"]["alpha/m1"]), 18)

    def test_bench_without_provider_says_so(self):
        rc, so, _se = self.cli("bench", "--providers", providers_file(self.tmp, []))
        self.assertEqual(rc, 0)
        self.assertIn("aucun fournisseur", so)


# ------------------------------------------------------------------ A13: 50 exfiltration attempts on the local proxy
SECRET_MAKERS = [
    lambda: "sk-ant-api03-" + secrets.token_urlsafe(30).replace("-", "a"),
    lambda: "sk-" + secrets.token_hex(24),
    lambda: "ghp_" + secrets.token_hex(18),
    lambda: "github_pat_" + secrets.token_hex(20),
    lambda: "AKIA" + secrets.token_hex(8).upper(),
    lambda: "AIza" + secrets.token_urlsafe(26)[:35].replace("-", "b"),
    lambda: "xoxb-" + secrets.token_hex(12),
    lambda: "-----BEGIN RSA PRIVATE KEY-----\nMIIE" + secrets.token_hex(20),
    lambda: "sk_live_" + secrets.token_hex(12),
    lambda: "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIx" + secrets.token_hex(6) + "." + secrets.token_hex(16),
    lambda: 'api_key = "%s"' % secrets.token_hex(16),
    lambda: 'password: "%s"' % secrets.token_hex(14),
    lambda: "Authorization: Bearer " + secrets.token_hex(20),
]


class A13NoExfiltration(Base):
    def test_a13_fifty_attempts_zero_exit(self):
        s = self.server()
        pf = providers_file(self.tmp, [provider("alpha", s.url, max_color="orange")])
        # positive control: a clean green run reaches the proxy, so the zero below is meaningful
        clean = self.file("clean.log", BIG)
        rc, so, _se = self.cli("run", "--task", "resume", "--in", clean, "--out", os.path.join(self.tmp, "c.json"), "--providers", pf, "--color", "vert")
        self.assertEqual(len(s.seen), 1, so)
        s.seen.clear()
        attempts, planted = 0, []
        # 26: every secret family, in green and orange projects
        for color in ("vert", "orange"):
            for mk in SECRET_MAKERS:
                sec = mk()
                planted.append(sec.splitlines()[0][-20:])
                f = self.file("s%d.log" % attempts, BIG[:4000] + "\nconfig: " + sec + "\n" + BIG[4000:])
                rc, so, _se = self.cli("run", "--task", "resume", "--in", f, "--out", os.path.join(self.tmp, "o.json"), "--providers", pf, "--color", color)
                self.assertEqual(rc, 2, "secret not refused: %s %s" % (color, so))
                attempts += 1
        # 8: secret hidden in the spec rather than in the source
        for mk in SECRET_MAKERS[:8]:
            sec = mk()
            planted.append(sec.splitlines()[0][-20:])
            rc, so, _se = self.cli("run", "--task", "resume", "--in", clean, "--out", os.path.join(self.tmp, "o.json"), "--providers", pf,
                                   "--color", "vert", "--spec", json.dumps({"note": sec}))
            self.assertEqual(rc, 2, so)
            attempts += 1
        # 6: red project, whatever is passed on the command line
        proj = os.path.join(self.tmp, "proj")
        mdir = os.path.join(proj, ".super-reprompt", "rouge-mission")
        os.makedirs(mdir)
        with open(os.path.join(mdir, "SCELLE.json"), "w", encoding="utf-8") as f:
            json.dump({"color": "rouge", "red": ["clients.csv"]}, f)
        red_src = os.path.join(proj, "notes.log")
        with open(red_src, "w", encoding="utf-8") as f:
            f.write(BIG)
        for color in ("vert", "orange", "vert", "orange", "vert", "orange"):
            rc, so, _se = self.cli("run", "--task", "resume", "--in", red_src, "--out", os.path.join(proj, "o.json"), "--providers", pf,
                                   "--color", color, cwd=proj)
            self.assertEqual(rc, 2, so)
            attempts += 1
        # 5: red file listed by the seal in a green project
        with open(os.path.join(mdir, "SCELLE.json"), "w", encoding="utf-8") as f:
            json.dump({"color": "vert", "red": ["clients.csv"]}, f)
        red_file = os.path.join(proj, "clients.csv")
        with open(red_file, "w", encoding="utf-8") as f:
            f.write(BIG)
        for _ in range(5):
            rc, so, _se = self.cli("run", "--task", "resume", "--in", red_file, "--out", os.path.join(proj, "o.json"), "--providers", pf, cwd=proj)
            self.assertEqual(rc, 2, so)
            attempts += 1
        # 5: key-store / credential files as input
        for name in (".env", "credentials.json", "id_rsa", "groq.dpapi", ".npmrc"):
            p = self.file(name, BIG)
            rc, so, _se = self.cli("run", "--task", "resume", "--in", p, "--out", os.path.join(self.tmp, "o.json"), "--providers", pf, "--color", "vert")
            self.assertEqual(rc, 2, name + so)
            attempts += 1
        self.assertEqual(attempts, 50)
        self.assertEqual(s.seen, [], "something reached the proxy")
        print("\nA13 %d tentatives, %d requetes recues par le proxy, %d secrets plantes trouves: 0" % (attempts, len(s.seen), len(planted)))


# ------------------------------------------------------------------ key store (DPAPI) and A16
@unittest.skipUnless(os.name == "nt", "DPAPI: Windows only")
class KeyStoreDPAPI(Base):
    def test_roundtrip_file_is_not_plaintext(self):
        ks = connect.keystore(self.home)
        key = "srk-" + secrets.token_hex(24)
        ks.set("groq", key, "api.groq.com")
        self.assertEqual(ks.get("groq"), key)
        with open(os.path.join(self.home, "keys", "groq.dpapi"), "rb") as f:
            self.assertNotIn(key.encode(), f.read())
        ks.delete("groq")
        self.assertIsNone(ks.get("groq"))

    def test_a16_key_invisible_in_logs_args_ledger_and_repo(self):
        key = "srk-" + secrets.token_hex(24)
        connect.keystore(self.home).set("alpha", key, "127.0.0.1")
        s = self.server()
        pf = providers_file(self.tmp, [provider("alpha", s.url, access="key")])
        src = self.file("journal.log", BIG)
        out = os.path.join(self.tmp, "out.txt")
        args = [sys.executable, RELAIS, "run", "--task", "commit", "--in", src, "--out", out, "--providers", pf, "--color", "vert", "--slug", "demo"]
        p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=self.env(), cwd=self.tmp, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(s.seen[0]["headers"].get("Authorization"), "Bearer " + key)   # it did reach the provider
        haystacks = {"stdout": p.stdout, "stderr": p.stderr, "argv": " ".join(args).encode()}
        rc2, so2, se2 = self.cli("status")
        haystacks["status"] = (so2 + se2).encode()
        for dp, _d, fs in os.walk(self.tmp):          # relay home + sealed mission (ledger) + inputs and outputs
            for fn in fs:
                with open(os.path.join(dp, fn), "rb") as f:
                    haystacks[os.path.relpath(os.path.join(dp, fn), self.tmp)] = f.read()
        self.assertTrue(any(k.endswith("ledger.sqlite") for k in haystacks))
        found = [k for k, v in haystacks.items() if key.encode() in v]
        self.assertEqual(found, [])
        g = subprocess.run(["git", "-C", ROOT, "grep", "--untracked", "-I", "-F", "-c", key], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(g.stdout.strip(), b"")
        print("\nA16 cle factice cherchee dans %d sources (sortie, erreurs, arguments, status, %d fichiers foyer+mission+grand livre, git grep): 0 occurrence"
              % (len(haystacks) + 1, len(haystacks) - 4))

    def test_disconnect_removes_the_key(self):
        connect.keystore(self.home).set("groq", "srk-" + secrets.token_hex(8), "api.groq.com")
        rc, so, _se = self.cli("disconnect", "groq")
        self.assertEqual(rc, 0, so)
        self.assertIsNone(connect.keystore(self.home).get("groq"))


class KeyStoreFallback(unittest.TestCase):
    def test_refuses_when_no_secure_store(self):
        with self.assertRaises(connect.NoSecureStore):
            connect.keystore(tempfile.gettempdir(), platform="plan9")

    def test_connect_flow_with_a_fake_store_and_fake_terminal(self):
        class Fake:
            def __init__(self):
                self.d, self.hosts = {}, {}

            def set(self, n, v, host):
                self.d[n] = v
                self.hosts[n] = host

            def get(self, n):
                return self.d.get(n)

            def delete(self, n):
                self.d.pop(n, None)
        st, printed = Fake(), []
        p = provider("alpha", "https://a.invalid/v1", access="key")
        ok = connect.connect_flow(p, store=st, ask=lambda prompt: "srk-test-value-123456", tty=True,
                                  probe=lambda prov, key: (True, "200"), out=printed.append)
        self.assertTrue(ok)
        self.assertEqual(st.get("alpha"), "srk-test-value-123456")
        self.assertEqual(st.hosts["alpha"], "a.invalid")             # the key is bound to the host it was tested on
        text = "\n".join(printed)
        self.assertIn("https://example.invalid/keys", text)
        self.assertIn("aucune retention", text)
        self.assertNotIn("srk-test-value", text)
        st2 = Fake()
        ok = connect.connect_flow(p, store=st2, ask=lambda prompt: "srk-bad", tty=True, probe=lambda prov, key: (False, "401"), out=printed.append)
        self.assertFalse(ok)
        self.assertIsNone(st2.get("alpha"))         # a key that fails the real call is not kept
        self.assertFalse(connect.connect_flow(p, store=st2, ask=lambda q: "x", tty=False, probe=None, out=printed.append))


class SecurityReview(Base):
    """One test per finding of the L6 security review (ecc:security-reviewer, 23/11/2026)."""

    def setUp(self):
        super().setUp()
        self.src = self.file("journal.log", BIG)

    def cmd(self, provs, *extra, task="commit", src=None, out=None):
        pf = providers_file(self.tmp, provs)
        return self.cli("run", "--task", task, "--in", src or self.src, "--out", out or os.path.join(self.tmp, "out.txt"), "--providers", pf, *extra)

    @unittest.skipUnless(os.name == "nt", "DPAPI: Windows only")
    def test_r1_key_is_bound_to_the_host_it_was_tested_on(self):
        key = "srk-" + secrets.token_hex(24)
        connect.keystore(self.home).set("groq", key, "api.groq.com")
        evil = self.server()
        rc, so, _se = self.cmd([provider("groq", evil.url, access="key")])     # forged providers file, same id, other host
        self.assertEqual(evil.seen, [], "the key was sent to another host")
        self.assertEqual(rc, 3)

    def test_r2_trailing_dot_host_is_still_excluded(self):
        with self.assertRaises(relais.Refused):
            relais.check_url("https://api.cerebras.ai./v1", relais.load_providers()["excluded"])

    def test_r3_model_code_never_runs_without_exec_and_green(self):
        s = self.server(answer=lambda b: json.dumps({"code": "print(1)"}))
        spec = json.dumps({"kind": "script", "stdin": "", "stdout": "1\n"})
        rc, so, _se = self.cmd([provider("alpha", s.url)], "--spec", spec, task="regex_sql_script")
        self.assertEqual(rc, 2, so)
        self.assertIn("--exec", so)
        self.assertEqual(s.seen, [])
        rc, so, _se = self.cmd([provider("alpha", s.url)], "--spec", spec, "--exec", task="regex_sql_script")
        self.assertEqual(rc, 2, so)                    # V3.1 lot 5 (CDC 11.4): --exec is not a sandbox; without a real one, never
        self.assertIn("bac a sable", so)
        self.assertEqual(s.seen, [])

    def test_r4_secret_scan_sees_every_occurrence(self):
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import guard_core
        real = secrets.token_hex(16)
        text = 'password = "your_password_here_xxxxxxxxxxxx"\n...\npassword = "%s"\n' % real
        self.assertIsNotNone(guard_core.secret_in(text))

    def test_r5_command_line_cannot_loosen_to_green_without_a_seal(self):
        shutil.rmtree(os.path.join(self.tmp, ".super-reprompt"))
        self.assertEqual(relais.effective_color(None, "vert"), "orange")
        self.assertEqual(relais.effective_color("vert", None), "vert")
        self.assertEqual(relais.effective_color("vert", "orange"), "orange")

    def test_r6_unreadable_seal_fails_closed(self):
        with open(os.path.join(self.mdir, "SCELLE.json"), "w", encoding="utf-8") as f:
            f.write("{pas du json")
        s = self.server()
        rc, so, _se = self.cmd([provider("alpha", s.url)])
        self.assertEqual(rc, 2, so)
        self.assertEqual(s.seen, [])
        with open(os.path.join(self.mdir, "SCELLE.json"), "w", encoding="utf-8") as f:
            json.dump({"color": "VIOLET"}, f)
        rc, so, _se = self.cmd([provider("alpha", s.url)])
        self.assertEqual(rc, 2, so)

    def test_r7_red_entries_are_resolved_paths(self):
        with open(os.path.join(self.mdir, "SCELLE.json"), "w", encoding="utf-8") as f:
            json.dump({"color": "vert", "red": ["./donnees/../clients.csv"]}, f)
        red = self.file("clients.csv", BIG)
        s = self.server()
        rc, so, _se = self.cmd([provider("alpha", s.url)], src=red)
        self.assertEqual(rc, 2, so)
        self.assertEqual(s.seen, [])

    def test_r8_spec_file_obeys_the_same_gate(self):
        p = self.file(".env", json.dumps({"note": "rien"}))
        s = self.server()
        rc, so, _se = self.cmd([provider("alpha", s.url)], "--spec", p)
        self.assertEqual(rc, 2, so)
        self.assertEqual(s.seen, [])

    def test_r8b_run_and_batch_enforce_never_delegated_without_plan(self):
        s = self.server()
        for extra in (("--desc", "revoir l'architecture du module"),
                      ("--spec", json.dumps({"consigne": "choisir la cryptographie des jetons"})),
                      ("--desc", "Decision d'ACCEPTATION finale")):
            rc, so, _se = self.cmd([provider("alpha", s.url)], *extra)
            self.assertEqual(rc, 2, so)
            self.assertIn("jamais delegue", so)
        pf = providers_file(self.tmp, [provider("alpha", s.url)])
        lot = self.file("lot8.ndjson", json.dumps({"id": "B1", "task": "commit", "in": self.src, "out": os.path.join(self.tmp, "b1.txt"),
                                                   "text": "trancher l'arbitrage entre deux options"}) + "\n")
        rc, so, _se = self.cli("batch", lot, "--providers", pf)
        self.assertIn("jamais delegue", so)
        self.assertEqual(s.seen, [], "a never-delegated task reached the provider")

    def test_r9_out_is_checked(self):
        s = self.server()
        rc, so, _se = self.cmd([provider("alpha", s.url)], out=self.src)                    # overwrite the input
        self.assertEqual(rc, 2, so)
        outside = os.path.join(tempfile.gettempdir(), "relais-hors-perimetre-%s.txt" % secrets.token_hex(4))
        rc, so, _se = self.cmd([provider("alpha", s.url)], out=outside)
        self.assertEqual(rc, 2, so)
        self.assertFalse(os.path.exists(outside))
        rc, so, _se = self.cmd([provider("alpha", s.url)], out=os.path.join(self.mdir, "SCELLE.json"))
        self.assertEqual(rc, 2, so)
        self.assertEqual(s.seen, [])

    def test_r10_module_name_cannot_escape_the_temp_dir(self):
        sys.path.insert(0, NET)
        import verify
        ok, _d = verify.check("code_repetitif", "x", "X = 1\n", {"module": "..\\..\\evade", "check": "import sys"})
        self.assertFalse(ok)

    def test_r11_build_command_must_appear_in_the_source_log(self):
        import verify
        cmd = [sys.executable, "-I", "-c", "import sys; sys.exit('boom')"]
        out = json.dumps({"command": cmd, "error_line": "boom", "explanation": "x"})
        self.assertFalse(verify.check("erreur_build", "journal sans la commande", out, {"allowed_commands": [cmd]})[0])
        self.assertTrue(verify.check("erreur_build", "$ " + " ".join(cmd) + "\nboom", out, {"allowed_commands": [cmd]})[0])

    def test_r12_endless_sql_is_stopped(self):
        import verify
        spec = {"kind": "sql", "setup": "", "expected": [[1]]}
        t0 = __import__("time").time()
        ok, _d = verify.check("regex_sql_script", "", "with recursive c(x) as (select 1 union all select x+1 from c) select count(*) from c", spec)
        self.assertFalse(ok)
        self.assertLess(__import__("time").time() - t0, 10)

    def test_r13_anonymisation_is_linear(self):
        t0 = __import__("time").time()
        relais.Anon(True).add("a-" * 8000 + " " + "b_" * 8000)
        self.assertLess(__import__("time").time() - t0, 2.0)
        big = self.file("enorme.log", "x" * (relais.MAX_INPUT_BYTES + 10))
        rc, so, _se = self.cmd([], src=big)
        self.assertEqual(rc, 2, so)

    def test_r14_receipt_carries_no_model_text(self):
        marker = "IGNORE-PREVIOUS-INSTRUCTIONS-" + secrets.token_hex(4)
        s = self.server(answer=lambda b: json.dumps({"text": marker}))
        rc, so, _se = self.cmd([provider("alpha", s.url)])
        self.assertEqual(rc, 3)
        self.assertNotIn(marker, so)
        import verify
        for typ, out in (("resume", json.dumps({"summary": "s", "quotes": [marker]})), ("labels", None)):
            if out:
                ok, det = verify.check(typ, "source", out, {"min_quotes": 1})
                self.assertFalse(ok)
                self.assertNotIn(marker, det)

    def test_r16_malformed_answers_do_not_crash(self):
        for ans in (lambda b: None, lambda b: 12):
            s = FakeServer(answer=ans)
            self.servers.append(s)
            rc, so, se = self.cmd([provider("alpha", s.url)])
            self.assertIn(rc, (3, 5), so + se)
            self.assertNotIn("Traceback", se)


if __name__ == "__main__":
    unittest.main()
