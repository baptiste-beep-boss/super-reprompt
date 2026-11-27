# -*- coding: utf-8 -*-
"""Implementation de reference de l'enonce semver (sert UNIQUEMENT a verifier que la batterie cachee est satisfiable
et juste ; jamais montree aux bras du banc)."""
import re

IDENT = r"[0-9A-Za-z-]+"
VRX = re.compile(r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(%s(?:\.%s)*))?(?:\+(%s(?:\.%s)*))?$" % (IDENT, IDENT, IDENT, IDENT))


class RangeError(ValueError):
    pass


def parse(v):
    if not isinstance(v, str):
        raise ValueError("version")
    m = VRX.match(v.strip())
    if not m:
        raise ValueError("version invalide: %r" % (v,))
    pre = m.group(4)
    if pre:
        for i in pre.split("."):
            if i.isdigit() and len(i) > 1 and i[0] == "0":
                raise ValueError("zero de tete")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), tuple(pre.split(".")) if pre else ())


def _pk(i):
    return (0, int(i), "") if i.isdigit() else (1, 0, i)


def key(v):
    a, b, c, pre = v
    return (a, b, c, 1 if not pre else 0, tuple(_pk(i) for i in pre))


def cmp(x, y):
    kx, ky = key(x), key(y)
    return (kx > ky) - (kx < ky)


def _partial(tok):
    m = re.match(r"^v?([0-9]+|[xX*])(?:\.([0-9]+|[xX*]))?(?:\.([0-9]+|[xX*]))?(?:-(%s(?:\.%s)*))?(?:\+%s(?:\.%s)*)?$" % (IDENT, IDENT, IDENT, IDENT), tok)
    if not m:
        raise RangeError("comparateur: %r" % tok)
    parts = []
    for g in m.groups()[:3]:
        if g is None or g in "xX*":
            parts.append(None)
        else:
            if len(g) > 1 and g[0] == "0":
                raise RangeError("zero de tete")
            parts.append(int(g))
    for i in range(3):
        if parts[i] is None and any(p is not None for p in parts[i + 1:]):
            raise RangeError("joker au milieu")
    pre = m.group(4)
    if pre and None in parts:
        raise RangeError("prerelease sur partielle")
    if pre:
        for i in pre.split("."):
            if i.isdigit() and len(i) > 1 and i[0] == "0":
                raise RangeError("zero de tete prerelease")
    return parts, tuple(pre.split(".")) if pre else ()


def _v(a, b, c, pre=()):
    return (a, b, c, pre)


def _lower(parts, pre):
    a, b, c = (p or 0 for p in parts)
    return _v(a, b, c, pre)


def _upper_excl(parts):
    a, b, c = parts
    if a is None:
        return None
    if b is None:
        return _v(a + 1, 0, 0)
    if c is None:
        return _v(a, b + 1, 0)
    return None


def _desugar(tok):
    """-> liste de (op, version)"""
    m = re.match(r"^(\^|~|>=|<=|>|<|=)?(.*)$", tok)
    op, rest = m.group(1) or "", m.group(2)
    if rest == "":
        raise RangeError("operande manquant")
    parts, pre = _partial(rest)
    full = None not in parts
    if op == "^":
        lo = _lower(parts, pre)
        a, b, c = parts
        if a is None:
            return [(">=", _v(0, 0, 0))]
        if a > 0 or b is None:
            hi = _v(a + 1, 0, 0)
        elif b > 0 or c is None:
            hi = _v(a, b + 1, 0)
        else:
            hi = _v(a, b, c + 1)
        return [(">=", lo), ("<", hi)]
    if op == "~":
        a, b, c = parts
        if a is None:
            return [(">=", _v(0, 0, 0))]
        lo = _lower(parts, pre)
        hi = _v(a, b + 1, 0) if b is not None else _v(a + 1, 0, 0)
        return [(">=", lo), ("<", hi)]
    if parts[0] is None:
        if op in ("", "="):
            return [(">=", _v(0, 0, 0))]
        if op in (">=", "<="):
            return [(">=", _v(0, 0, 0))]
        return [("<", _v(0, 0, 0))]   # > * ou < * : jamais satisfait
    if full:
        return [(op or "=", _v(parts[0], parts[1], parts[2], pre))]
    up = _upper_excl(parts)
    lo = _lower(parts, ())
    if op in ("", "="):
        return [(">=", lo), ("<", up)]
    if op == ">":
        return [(">=", up)]
    if op == ">=":
        return [(">=", lo)]
    if op == "<":
        return [("<", lo)]
    if op == "<=":
        return [("<", up)]
    raise RangeError("operateur")


def _block(text):
    text = re.sub(r"(>=|<=|>|<|=|\^|~)\s+", r"\1", text.strip())
    if re.search(r"\s-\s", text):
        m = re.match(r"^(\S+)\s+-\s+(\S+)$", text)
        if not m:
            raise RangeError("tiret")
        lo, lpre = _partial(m.group(1))
        hi, hpre = _partial(m.group(2))
        out = [(">=", _lower(lo, lpre))]
        if None in hi:
            up = _upper_excl(hi)
            if up:
                out.append(("<", up))
        else:
            out.append(("<=", _v(hi[0], hi[1], hi[2], hpre)))
        return out
    if text == "":
        return [(">=", _v(0, 0, 0))]
    out = []
    for tok in text.split():
        out += _desugar(tok)
    return out


def _ok(v, comp):
    op, w = comp
    c = cmp(v, w)
    return {">=": c >= 0, "<=": c <= 0, ">": c > 0, "<": c < 0, "=": c == 0}[op]


def satisfies(version, plage):
    v = parse(version)
    if not isinstance(plage, str):
        raise RangeError("plage")
    blocks = [_block(b) for b in plage.split("||")]
    for comps in blocks:
        if not all(_ok(v, c) for c in comps):
            continue
        if v[3]:
            if not any(w[:3] == v[:3] and w[3] for _o, w in comps):
                continue
        return True
    return False


def max_satisfying(versions, plage):
    best = None
    for s in versions:
        v = parse(s)
        if satisfies(s, plage) and (best is None or cmp(v, best[0]) > 0):
            best = (v, s)
    return best[1] if best else None
