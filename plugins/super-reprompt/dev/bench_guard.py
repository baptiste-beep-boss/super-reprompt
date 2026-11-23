# -*- coding: utf-8 -*-
"""A20: median latency of the real hook command `py -3 -I -S scripts/guard.py` (also reports the bare interpreter floor).
Usage: py -3 dev/bench_guard.py [--n 60]   (standard library only, no network)"""
import json
import os
import statistics
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tests"))
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("tg", os.path.join(os.path.dirname(HERE), "tests", "test_guard.py"))
tg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tg)


def timed(cmd, data, cwd, env=None):
    t = time.perf_counter()
    subprocess.run(cmd, input=data, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (time.perf_counter() - t) * 1000


def main():
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 60
    e = tg.Env()
    try:
        real = ["py", "-3", "-I", "-S", tg.GUARD]
        direct = [sys.executable, "-I", "-S", tg.GUARD]
        mix = [tg.B(c) for c in tg.LEGIT_BASH] + [(t, i) for t, i in tg.LEGIT_TOOLS if "$SCRATCH" not in json.dumps(i)]
        payloads = [json.dumps({"tool_name": t, "tool_input": i, "cwd": e.root}).encode() for t, i in mix]
        floor = [timed(["py", "-3", "-I", "-S", "-c", "pass"], b"", e.root) for _ in range(20)]
        out_dir = os.path.dirname(e.top)
        outside = [timed(real, payloads[k % len(payloads)], out_dir) for k in range(20)]
        inside = [timed(real, payloads[k % len(payloads)], e.root) for k in range(n)]
        harmless = [timed(real, json.dumps({"tool_name": "Read", "tool_input": {"file_path": "README.md"}, "cwd": e.root}).encode(), e.root) for _ in range(20)]
        f = lambda x: "median %.0f ms  min %.0f  p90 %.0f  max %.0f" % (statistics.median(x), min(x), sorted(x)[int(len(x) * 0.9) - 1], max(x))
        dfloor = [timed([sys.executable, "-I", "-S", "-c", "pass"], b"", e.root) for _ in range(20)]
        dmix = [timed(direct, payloads[k % len(payloads)], e.root) for k in range(n)]
        print("DIRECT interpreter floor (python.exe -I -S): " + f(dfloor))
        print("DIRECT hook inside a mission, mix:           " + f(dmix))
        print("  -> hook overhead above the floor: %.0f ms (median)" % (statistics.median(dmix) - statistics.median(dfloor)))
        print("interpreter floor (py -3 -I -S -c pass): " + f(floor))
        print("hook outside a mission (I7, silent):       " + f(outside))
        print("hook inside a mission, harmless tool:      " + f(harmless))
        print("hook inside a mission, %d-action mix:      %s" % (len(mix), f(inside)))
        med = statistics.median(inside)
        print("A20 %s: median %.0f ms (limit 120 ms)" % ("OK" if med < 120 else "FAIL", med))
        return 0 if med < 120 else 1
    finally:
        e.close()


if __name__ == "__main__":
    sys.exit(main())
