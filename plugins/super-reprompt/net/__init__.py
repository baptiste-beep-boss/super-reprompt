# -*- coding: utf-8 -*-
"""The only package allowed to open a network connection (invariant I2).

Nothing under scripts/, dev/ or hooks/ may import socket, urllib, http or any HTTP client, and no hook
ever calls a module of this package. Even here, only the standard library (urllib) is allowed (I3).
Empty on purpose in lot L1: the Relay and the Scout arrive in later lots.
"""
