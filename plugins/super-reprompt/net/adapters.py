# -*- coding: utf-8 -*-
"""adapters.py : contrat ProviderAdapter commun du Relais (lot 5 V3.1, CDC 11.1). Bibliotheque standard ; le reseau
reste dans net/ (invariant I2) et passe par relais.call_provider (pas de redirection suivie, scan de secret, plafond).

Contrat : provider_id, capabilities, models, availability(key), estimate_cost(model, in, out), execute(model, messages),
health_check(key), timeout, cancel(run), usage_metadata(raw), error_mapping(raw).
Reponse normalisee : status ok|error, text, tokens_in, tokens_out, model, latency_ms, cost {amount, currency, label,
source}, provider, provider_request_id, error, error_class, retryable (+ `raw` : le dict historique de call_provider).

execute_with_policy : par fournisseur, tentatives bornees avec backoff exponentiel et jitter sur les seules erreurs
recuperables ; circuit breaker par fournisseur (un 429 l'ouvre) ; repli FINI : fournisseur suivant, puis "local"
(Haiku / session, decide par l'appelant). Aucun fournisseur : repli local immediat, dit tel quel.
sandbox_available : aucun bac a sable reel n'est fourni ; l'execution de code produit par un modele reste donc coupee.
"""
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import relais  # noqa: E402

RETRYABLE = {"rate_limit": True, "server": True, "network": True, "timeout": True, "auth": False, "client": False,
             "bad_response": False, "truncated": False, "empty": False, "refused": False}


def sandbox_available():
    """No real sandbox (isolated FS, no network, no secrets, CPU/RAM/time limits) ships with the plugin. A child process or a
    --exec flag is NOT one (CDC 11.4, 16.1). Returns (False, reason) until a real one is plugged in and tested."""
    return False, "aucun bac a sable reel configure (CDC 11.4) : l'execution de code produit par un modele est desactivee"


class ProviderAdapter(object):
    timeout = 90

    def __init__(self, conf, excluded=None, verified=None):
        self.conf = conf
        self.provider_id = conf.get("id")
        self.models = list(conf.get("models") or [])
        self.capabilities = {"chat": True, "json_mode": bool(conf.get("json_mode")), "max_color": conf.get("max_color", "vert"),
                             "streaming": False, "cancel": False}
        self.excluded = excluded if excluded is not None else {}
        self.verified = conf.get("verified") or verified

    def availability(self, key=None):
        if not self.conf.get("enabled"):
            return {"available": False, "reason": "desactive dans providers.json (%s)" % (self.conf.get("state") or "non configure")}
        if self.conf.get("access") in ("key", "account") and not key:
            return {"available": False, "reason": "cle absente : `relais.py connect %s` par l'utilisateur" % self.provider_id}
        if not self.models:
            return {"available": False, "reason": "aucun modele declare"}
        return {"available": True, "reason": "configure (sante non verifiee : health_check)"}

    def estimate_cost(self, model, tokens_in, tokens_out):
        m = next((x for x in self.models if x.get("id") == model), None) or {}
        if "price_in" not in m or "price_out" not in m:
            return {"amount": None, "currency": None, "label": "unavailable", "source": "aucun tarif declare pour %s" % model}
        amt = (float(m["price_in"]) * tokens_in + float(m["price_out"]) * tokens_out) / 1e6
        return {"amount": round(amt, 6), "currency": self.conf.get("currency", "EUR"), "label": "estimated",
                "source": "providers.json, tarifs verifies le %s" % (self.verified or "?")}

    def cancel(self, run_id):
        return {"supported": False, "reason": "appel synchrone : l'annulation n'existe pas, le delai (timeout) borne l'appel"}

    def usage_metadata(self, raw):
        return {"tokens_in": int(raw.get("tokens_in") or 0), "tokens_out": int(raw.get("tokens_out") or 0),
                "request_id": (raw.get("headers") or {}).get("x-request-id"),
                "quota_remaining": (raw.get("headers") or {}).get("x-ratelimit-remaining-requests")}

    def error_mapping(self, raw):
        st, err = int(raw.get("status") or 0), str(raw.get("error") or "")
        if raw.get("ok"):
            return None, False
        if st == 429:
            c = "rate_limit"
        elif st in (401, 403):
            c = "auth"
        elif st >= 500:
            c = "server"
        elif 400 <= st < 500:
            c = "client"
        elif "tronquee" in err:
            c = "truncated"
        elif "vide" in err:
            c = "empty"
        elif ("mal formee" in err) or ("illisible" in err and st):
            c = "bad_response"
        elif "timeout" in err.lower():
            c = "timeout"
        elif "secret" in err:
            c = "refused"
        else:
            c = "network"
        return c, RETRYABLE[c]

    def _normalise(self, raw, model):
        cls, retry = self.error_mapping(raw)
        u = self.usage_metadata(raw)
        return {"status": "ok" if raw.get("ok") else "error", "text": raw.get("content") or "", "tokens_in": u["tokens_in"],
                "tokens_out": u["tokens_out"], "model": model, "latency_ms": int(round(1000 * float(raw.get("duration") or 0))),
                "cost": self.estimate_cost(model, u["tokens_in"], u["tokens_out"]), "provider": self.provider_id,
                "provider_request_id": u["request_id"], "error": raw.get("error") or None, "error_class": cls, "retryable": retry,
                "retry_after": (raw.get("headers") or {}).get("retry-after"), "raw": raw}

    def health_check(self, key=None, timeout=10):
        if not self.models:
            return {"ok": False, "latency_ms": None, "error": "aucun modele"}
        t0 = time.time()
        r = self.execute(self.models[0]["id"], [{"role": "user", "content": "Reponds OK."}], key=key, max_tokens=16, timeout=timeout)
        return {"ok": r["status"] == "ok", "latency_ms": int((time.time() - t0) * 1000), "error": r["error"], "error_class": r["error_class"]}


class OpenAICompatAdapter(ProviderAdapter):
    """Every provider of providers.json speaks the OpenAI-compatible /chat/completions."""

    def execute(self, model, messages, key=None, max_tokens=None, timeout=None, raise_refused=False):
        try:
            raw = relais.call_provider(self.conf, model, key, messages, self.excluded, max_tokens=max_tokens or relais.MAX_OUT_TOKENS,
                                       timeout=timeout or self.timeout)
        except relais.Refused as e:
            if raise_refused:                 # privacy refusal is not a provider failure: the caller keeps its own semantics
                raise
            raw = {"ok": False, "status": 0, "content": "", "error": "refus : %s" % e, "headers": {}, "duration": 0}
            if "secret" in str(e):
                raw["error"] = "secret dans la requete"
        return self._normalise(raw, model)


class MockAdapter(ProviderAdapter):
    """Scripted adapter for tests: each item is {text, tokens_in, tokens_out} or {status_code, headers}."""

    def __init__(self, conf, script=(), **kw):
        ProviderAdapter.__init__(self, conf, **kw)
        self.script, self.calls = list(script), []

    def execute(self, model, messages, key=None, max_tokens=None, timeout=None):
        self.calls.append(model)
        it = self.script.pop(0) if self.script else {"status_code": 500}
        if "text" in it:
            raw = {"ok": True, "status": 200, "content": it["text"], "tokens_in": it.get("tokens_in", 0), "tokens_out": it.get("tokens_out", 0),
                   "headers": {}, "duration": 0.01, "error": ""}
        else:
            raw = {"ok": False, "status": it["status_code"], "content": "", "headers": it.get("headers", {}), "duration": 0.01,
                   "error": "HTTP %d" % it["status_code"]}
        return self._normalise(raw, model)


def adapter_for(conf, excluded=None, verified=None):
    return OpenAICompatAdapter(conf, excluded=excluded, verified=verified)


def execute_with_policy(adapters, model, messages, breaker, keys=None, max_attempts=2, base_delay=0.5, sleep=time.sleep,
                        rand=random.random, model_for=None):
    """Bounded and traced. -> {result (normalised response or None), attempts [...], fallback None|'local', reason}."""
    attempts = []
    if not adapters:
        return {"result": None, "attempts": attempts, "fallback": "local", "reason": "aucun fournisseur configure : repli local (Haiku / session)"}
    for ad in adapters:
        pid = ad.provider_id
        st = breaker.state(pid)
        if st == "ouvert":
            attempts.append({"provider": pid, "skipped": "circuit ouvert", "error_class": None})
            continue
        m = model_for(ad) if model_for else model
        for i in range(max_attempts):
            r = ad.execute(m, messages, key=(keys or {}).get(pid))
            attempts.append({"provider": pid, "model": m, "attempt": i + 1, "status": r["status"], "error_class": r["error_class"],
                             "latency_ms": r["latency_ms"], "tokens_in": r["tokens_in"], "tokens_out": r["tokens_out"]})
            if r["status"] == "ok":
                breaker.success(pid)
                return {"result": r, "attempts": attempts, "fallback": None, "reason": "ok via %s" % pid}
            if r["error_class"] == "rate_limit":
                ra = r.get("retry_after")
                breaker.trip(pid, int(ra) if str(ra or "").isdigit() else breaker.COOLDOWN)
                break
            breaker.failure(pid)
            if not r["retryable"] or breaker.state(pid) == "ouvert" or i == max_attempts - 1:
                break
            sleep(base_delay * (2 ** i) * (0.5 + rand()))          # exponential backoff with jitter
    return {"result": None, "attempts": attempts, "fallback": "local",
            "reason": "%d fournisseur(s), %d tentative(s) bornee(s) en echec : repli local" % (len(adapters), sum(1 for x in attempts if "attempt" in x))}
