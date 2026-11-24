# -*- coding: utf-8 -*-
"""Key store and connection flow of the Relay (CDC §8.7).

* Windows: DPAPI (CryptProtectData, current user) through ctypes; the blob lives in <relais home>/keys/<id>.dpapi.
* Linux: libsecret through `secret-tool`, the key written on its standard input (never an argument).
* Anything else (macOS included, for now): refusal. No plain-text fallback, ever.

The key is typed by the user, masked, in their own terminal (`getpass`). It is never an argument, never an environment
variable, never logged, never printed, never returned to the agent: the agent runs `relais` and only reads receipts.
The Vigie denies reads of `*.dpapi` (guard_core.is_secret_store).
"""
import json
import os
import shutil
import subprocess
import sys

ENTROPY = b"super-reprompt-relais/v1"


class NoSecureStore(Exception):
    pass


def host_of(url):
    import urllib.parse
    return (urllib.parse.urlsplit(url or "").hostname or "").lower().rstrip(".")


def _pack(secret, host):
    """The key travels with the host it was tested on: a forged providers file cannot redirect it (review #1)."""
    return json.dumps({"k": secret, "h": (host or "").lower().rstrip(".")}).encode("utf-8")


def _unpack(raw):
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return d if isinstance(d, dict) and d.get("k") and "h" in d else None


def _valid_id(name):
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        raise ValueError("identifiant de fournisseur invalide")
    return name


class DPAPIStore:
    def __init__(self, home):
        import ctypes
        from ctypes import wintypes
        self.ct, self.dir = ctypes, os.path.join(home, "keys")

        class BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
        self.BLOB = BLOB
        self.crypt32, self.kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
        self.kernel32.LocalFree.argtypes = [ctypes.c_void_p]

    def _blob(self, data):
        buf = self.ct.create_string_buffer(data, len(data))
        return self.BLOB(len(data), self.ct.cast(buf, self.ct.POINTER(self.ct.c_char))), buf

    def _call(self, fn, data):
        inp, _b1 = self._blob(data)
        ent, _b2 = self._blob(ENTROPY)
        out = self.BLOB()
        # same signature for CryptProtectData and CryptUnprotectData; 0x1 = CRYPTPROTECT_UI_FORBIDDEN
        if not fn(self.ct.byref(inp), None, self.ct.byref(ent), None, None, 0x1, self.ct.byref(out)):
            raise OSError("DPAPI a refuse l'operation")
        try:
            return self.ct.string_at(out.pbData, out.cbData)
        finally:
            self.kernel32.LocalFree(self.ct.cast(out.pbData, self.ct.c_void_p))

    def path(self, name):
        return os.path.join(self.dir, _valid_id(name) + ".dpapi")

    def set(self, name, secret, host):
        os.makedirs(self.dir, exist_ok=True)
        blob = self._call(self.crypt32.CryptProtectData, _pack(secret, host))
        tmp = self.path(name) + ".tmp"
        with open(tmp, "wb") as f:
            f.write(blob)
        os.replace(tmp, self.path(name))

    def has(self, name):
        return os.path.isfile(self.path(name))

    def record(self, name):
        if not self.has(name):
            return None
        with open(self.path(name), "rb") as f:
            return _unpack(self._call(self.crypt32.CryptUnprotectData, f.read()))

    def get(self, name):
        r = self.record(name)
        return r["k"] if r else None

    def delete(self, name):
        if self.has(name):
            os.remove(self.path(name))


class SecretToolStore:
    ATTR = ["service", "super-reprompt-relais", "provider"]

    def __init__(self, exe):
        self.exe = exe

    def _run(self, args, stdin=None):
        return subprocess.run([self.exe] + args, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30)

    def set(self, name, secret, host):
        p = self._run(["store", "--label=super-reprompt relais " + _valid_id(name)] + self.ATTR + [name], stdin=_pack(secret, host))
        if p.returncode != 0:
            raise OSError("libsecret a refuse l'enregistrement")

    def record(self, name):
        p = self._run(["lookup"] + self.ATTR + [_valid_id(name)])
        return _unpack(p.stdout) if p.returncode == 0 and p.stdout.strip() else None

    def get(self, name):
        r = self.record(name)
        return r["k"] if r else None

    def has(self, name):
        return self.record(name) is not None

    def delete(self, name):
        self._run(["clear"] + self.ATTR + [_valid_id(name)])


def interactive_terminal():
    """True only for a human's console. On Windows `NUL` claims isatty(): ask the console itself (GetConsoleMode)."""
    try:
        if not sys.stdin or not sys.stdin.isatty():
            return False
        if os.name == "nt":
            import ctypes
            import msvcrt
            mode = ctypes.c_uint32()
            return bool(ctypes.windll.kernel32.GetConsoleMode(msvcrt.get_osfhandle(sys.stdin.fileno()), ctypes.byref(mode)))
        return True
    except (OSError, ValueError, AttributeError):
        return False


def keystore(home, platform=None):
    plat = platform or sys.platform
    if plat == "win32":
        return DPAPIStore(home)
    if plat.startswith("linux") and shutil.which("secret-tool"):
        return SecretToolStore(shutil.which("secret-tool"))
    raise NoSecureStore("aucun magasin de cles sur (DPAPI, libsecret) sur cette machine : connexion refusee")


def connect_flow(p, store, ask, tty, probe, out=print):
    """Show the official address and the data policy, ask the key masked, test one real call, keep the key only if it works."""
    if not tty:
        out("REFUS : `relais connect` se tape dans VOTRE terminal (saisie masquee). Jamais par un agent, jamais en argument.")
        return False
    out("Fournisseur : %s" % p.get("name", p["id"]))
    out("Adresse officielle pour creer la cle : %s" % p.get("signup_url", "?"))
    out("Ce que le fournisseur fait des donnees : %s" % p.get("data_policy", "non documente"))
    out("Couleur maximale acceptee : %s ; entrainement sur les requetes : %s" % (p.get("max_color"), "oui" if p.get("trains_on_data") else "non"))
    key = ask("Cle (saisie masquee, rien ne s'affiche) : ")
    if not key or not key.strip():
        out("Aucune cle saisie : rien n'est enregistre.")
        return False
    key = key.strip()
    ok, detail = probe(p, key)
    if not ok:
        out("Appel de test en echec (%s) : la cle n'est PAS enregistree." % detail)
        return False
    store.set(p["id"], key, host_of(p.get("base_url")))
    out("Connecte : appel de test reussi (%s). Cle chiffree dans le magasin du systeme." % detail)
    return True
