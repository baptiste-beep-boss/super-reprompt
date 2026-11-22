# -*- coding: utf-8 -*-
"""guard.py: the firewall hook of the Vigie (lot L4). NOT IMPLEMENTED in lot L1: this file only records the design rules.

Latency lesson measured in L0 (PREUVES.md, proof 4): `import json` pulls in `import re`, which alone costs
about 70-80 ms; the bare interpreter floor on the reference machine is 70-85 ms. The budget for a firewall hook
is 120 ms (criterion A20), so any Python firewall hook MUST:

  1. be launched as `py -3 -I -S guard.py` (isolated mode, no site import);
  2. avoid `json` and `re` on the hot path: fast filter on plain substrings, which lets harmless tools
     (Read, Glob, Grep, ...) through at once;
  3. load the full analysis (json, re) only for Bash, Write or Edit calls that the fast filter finds doubtful;
  4. fail CLOSED (exit code 2) on any corrupted input or internal error.

Measured in L0: full version 160-167 ms, fast variant 90-109 ms. Re-measure in L4 on the real hook launch.
"""

if __name__ == "__main__":
    print(__doc__)   # --help, or any call: the guard is not implemented yet (lot L4)
