# -*- coding: utf-8 -*-
"""uninstall.py : remove every trace the plugin left outside its own folder (A23). Standard library only, no network.

  py -3 scripts/uninstall.py          lists what would go; removes nothing
  py -3 scripts/uninstall.py --yes    removes the plugin state: ~/.claude/super-reprompt (logs, relay home with its
                                      DPAPI key files, vault index), RELAIS_HOME / SR_VAULT_DB if set elsewhere, and the
                                      relay keys kept by libsecret on Linux
Never touched: your projects' .super-reprompt/<slug>/ missions and your vault notes (they are your data; they are listed).
Then remove the plugin itself with `claude plugin uninstall super-reprompt`.
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _lib  # noqa: E402


def targets():
    home = os.path.normcase(os.path.abspath(os.path.expanduser("~")))
    out = []
    for p in (_lib.home_dir(), os.environ.get("RELAIS_HOME", "").strip(), os.environ.get("SR_VAULT_DB", "").strip()):
        if not p:
            continue
        p = os.path.abspath(p)
        n = os.path.normcase(p)
        # only the plugin's own state: never HOME, never a parent of HOME, never a folder not named after the plugin
        base = os.path.basename(n.rstrip(os.sep))
        is_state = any(k in base for k in ("super-reprompt", "relais", "vault-index"))
        if n == home or home.startswith(n.rstrip(os.sep) + os.sep) or not is_state:
            raise SystemExit("REFUS : %s n'est pas un dossier d'etat du plugin" % p)
        if p not in out:
            out.append(p)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    yes = "--yes" in argv
    try:
        ts = targets()
    except SystemExit as e:
        print(e)
        return 2
    found = [t for t in ts if os.path.exists(t)]
    for t in found:
        print("etat du plugin : %s" % t)
    secret_tool = shutil.which("secret-tool") if sys.platform.startswith("linux") else None
    if secret_tool:
        print("cles du Relais dans libsecret (service super-reprompt-relais)")
    mission = os.path.join(os.getcwd(), ".super-reprompt")
    if os.path.isdir(mission):
        print("conserve (vos donnees) : %s" % mission)
    print("conserve (vos donnees) : les notes du vault")
    if not yes:
        print("rien n'est supprime sans --yes")
        return 0
    for t in found:
        shutil.rmtree(t, ignore_errors=False) if os.path.isdir(t) else os.remove(t)
        parent = os.path.dirname(t)
        if os.path.basename(parent).lower() == ".claude" and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)          # ~/.claude created only by us: leave HOME as it was
    if secret_tool:
        subprocess.run([secret_tool, "clear", "service", "super-reprompt-relais"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("supprime : %d dossier(s) d'etat ; reste : `claude plugin uninstall super-reprompt`" % len(found))
    return 0


if __name__ == "__main__":
    sys.exit(main())
