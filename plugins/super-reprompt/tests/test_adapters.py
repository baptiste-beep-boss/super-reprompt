# -*- coding: utf-8 -*-
"""Lot 5 V3.1 : contrat ProviderAdapter commun (CDC 11.1), reponses normalisees, health_check, mapping d'erreurs,
retries bornes avec backoff et jitter, circuit breaker par fournisseur, repli fini jusqu'au local, mode sans fournisseur
sur, aucune execution de code modele sans vrai bac a sable."""
import os
import sys
import unittest

from _t import ROOT

sys.path.insert(0, os.path.join(ROOT, "net"))
import adapters as A  # noqa: E402
import relais  # noqa: E402

CONTRACT = ("provider_id", "capabilities", "models", "availability", "estimate_cost", "execute", "health_check", "timeout",
            "cancel", "usage_metadata", "error_mapping")
RESPONSE = ("status", "text", "tokens_in", "tokens_out", "model", "latency_ms", "cost", "provider", "provider_request_id",
            "error", "error_class", "retryable")


def cfg(pid="alpha", **kw):
    p = {"id": pid, "name": pid, "enabled": True, "base_url": "http://127.0.0.1:9/v1", "max_color": "vert",
         "models": [{"id": "m1", "context": 8000, "price_in": 0, "price_out": 0}], "currency": "EUR", "verified": "2026-11-23"}
    p.update(kw)
    return p


class Contract(unittest.TestCase):
    def test_both_adapters_expose_the_whole_contract(self):
        for ad in (A.OpenAICompatAdapter(cfg()), A.MockAdapter(cfg("mock"), script=[{"text": "ok"}])):
            for k in CONTRACT:
                self.assertTrue(hasattr(ad, k), "%s : %s" % (type(ad).__name__, k))

    def test_response_is_normalised(self):
        ad = A.MockAdapter(cfg("mock"), script=[{"text": "bonjour", "tokens_in": 12, "tokens_out": 3}])
        r = ad.execute("m1", [{"role": "user", "content": "x"}])
        self.assertEqual(set(RESPONSE) - set(r), set())
        self.assertEqual((r["status"], r["text"], r["tokens_in"], r["model"], r["provider"]), ("ok", "bonjour", 12, "m1", "mock"))
        self.assertEqual(r["cost"]["label"], "estimated")

    def test_error_mapping(self):
        ad = A.OpenAICompatAdapter(cfg())
        self.assertEqual(ad.error_mapping({"status": 429, "error": "HTTP 429"}), ("rate_limit", True))
        self.assertEqual(ad.error_mapping({"status": 401, "error": "HTTP 401"}), ("auth", False))
        self.assertEqual(ad.error_mapping({"status": 503, "error": "HTTP 503"}), ("server", True))
        self.assertEqual(ad.error_mapping({"status": 0, "error": "reseau ou reponse illisible: URLError"}), ("network", True))
        self.assertEqual(ad.error_mapping({"status": 200, "error": "tronquee (finish_reason: length)"}), ("truncated", False))

    def test_cost_never_invented(self):
        ad = A.OpenAICompatAdapter(cfg(models=[{"id": "m1", "context": 8000}]))
        c = ad.estimate_cost("m1", 1000, 100)
        self.assertEqual((c["amount"], c["label"]), (None, "unavailable"))
        c = A.OpenAICompatAdapter(cfg()).estimate_cost("m1", 1000, 100)
        self.assertEqual((c["amount"], c["label"], c["currency"]), (0.0, "estimated", "EUR"))
        self.assertIn("2026-11-23", c["source"])

    def test_availability_needs_config_and_key(self):
        self.assertFalse(A.OpenAICompatAdapter(cfg(enabled=False)).availability(key=None)["available"])
        self.assertFalse(A.OpenAICompatAdapter(cfg(access="key")).availability(key=None)["available"])
        self.assertTrue(A.OpenAICompatAdapter(cfg(access="key")).availability(key="k")["available"])

    def test_health_check_on_an_unreachable_provider_is_false_not_a_crash(self):
        h = A.OpenAICompatAdapter(cfg(), excluded=relais.load_providers()["excluded"]).health_check(key=None, timeout=2)
        self.assertFalse(h["ok"])
        self.assertTrue(h["error"])

    def test_cancel_is_declared_unsupported(self):
        self.assertEqual(A.OpenAICompatAdapter(cfg()).cancel("x")["supported"], False)


class Policy(unittest.TestCase):
    def test_bounded_retries_with_backoff_then_success(self):
        slept = []
        ad = A.MockAdapter(cfg("a"), script=[{"status_code": 503}, {"status_code": 503}, {"text": "ok"}])
        out = A.execute_with_policy([ad], "m1", [{"role": "user", "content": "x"}], breaker=relais.Breaker({}), max_attempts=3,
                                    sleep=slept.append, rand=lambda: 0.5)
        self.assertEqual(out["result"]["status"], "ok")
        self.assertEqual([x["error_class"] for x in out["attempts"]], ["server", "server", None])
        self.assertEqual(len(slept), 2)
        self.assertLess(slept[0], slept[1])                       # exponential backoff (with jitter)

    def test_non_retryable_error_goes_to_next_provider(self):
        a = A.MockAdapter(cfg("a"), script=[{"status_code": 401}])
        b = A.MockAdapter(cfg("b"), script=[{"text": "ok"}])
        out = A.execute_with_policy([a, b], "m1", [], breaker=relais.Breaker({}), max_attempts=3, sleep=lambda s: None)
        self.assertEqual((out["result"]["provider"], len(a.calls)), ("b", 1))

    def test_finite_fallback_ends_local(self):
        bad = [A.MockAdapter(cfg(p), script=[{"status_code": 500}] * 5) for p in ("a", "b")]
        out = A.execute_with_policy(bad, "m1", [], breaker=relais.Breaker({}), max_attempts=2, sleep=lambda s: None)
        self.assertIsNone(out["result"])
        self.assertEqual(out["fallback"], "local")
        self.assertEqual(len(out["attempts"]), 4)                   # 2 providers x 2 attempts, never more

    def test_open_breaker_is_skipped(self):
        br = relais.Breaker({})
        br.trip("a", 300)
        a = A.MockAdapter(cfg("a"), script=[{"text": "ok"}])
        b = A.MockAdapter(cfg("b"), script=[{"text": "ok"}])
        out = A.execute_with_policy([a, b], "m1", [], breaker=br, sleep=lambda s: None)
        self.assertEqual((out["result"]["provider"], len(a.calls)), ("b", 0))
        self.assertIn("ouvert", out["attempts"][0]["skipped"])

    def test_rate_limit_trips_the_breaker(self):
        br = relais.Breaker({})
        a = A.MockAdapter(cfg("a"), script=[{"status_code": 429, "headers": {"retry-after": "60"}}])
        A.execute_with_policy([a], "m1", [], breaker=br, sleep=lambda s: None)
        self.assertEqual(br.state("a"), "ouvert")

    def test_no_provider_mode_is_safe_and_says_so(self):
        out = A.execute_with_policy([], "m1", [], breaker=relais.Breaker({}), sleep=lambda s: None)
        self.assertEqual((out["result"], out["fallback"]), (None, "local"))
        self.assertIn("aucun fournisseur", out["reason"])


class Sandbox(unittest.TestCase):
    def test_no_real_sandbox_means_no_model_code_execution(self):
        ok, why = A.sandbox_available()
        self.assertFalse(ok)
        self.assertIn("bac a sable", why)


if __name__ == "__main__":
    unittest.main()
