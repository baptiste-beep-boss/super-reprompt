# -*- coding: utf-8 -*-
"""The only package allowed to open a network connection (invariant I2).

Nothing under scripts/, dev/ or hooks/ may import socket, urllib, http or any HTTP client, and no hook
ever calls a module of this package. Even here, only the standard library (urllib) is allowed (I3).
Lot L6 adds the Relay: relais.py (CLI), verify.py (18 deterministic verifiers), connect.py (key store),
bench.py (frozen bench set), tasks.json and providers.json. See RELAIS.md.
"""
