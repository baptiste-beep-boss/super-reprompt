# -*- coding: utf-8 -*-
"""Fixed bench set of the Relay: one case per task type, with a known good and a known bad output.

Used twice: by `relais bench` (the source and spec go to each model, the verifier scores the answer) and by the A12
tests (each verifier must accept `good` and reject `bad`). Frozen on purpose: change it and the history of scores no
longer compares. No network here.
"""
import json
import os
import sys

PY = sys.executable
SRC_TEXT = ("Le serveur a redemarre a 03:12. La cause est une fuite memoire dans le cache. "
            "Trois requetes ont echoue. Le correctif ajoute une limite de 512 entrees.")
CALC = "def add(a, b):\n    return a + b\n\n\ndef is_pos(x):\n    return x > 0\n"
APP = "def main():\n    pass\n\n\ndef helper():\n    return 1\n"


def J(o):
    return json.dumps(o, ensure_ascii=False)


def cases(root):
    """-> [(type, src, good_out, bad_out, spec)] for the 18 types. Writes two small files into `root`."""
    with open(os.path.join(root, "app.py"), "w", encoding="utf-8") as f:
        f.write(APP)
    with open(os.path.join(root, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n")
    build_cmd = [PY, "-I", "-c", "import sys; sys.stderr.write('NameError: name x is not defined\\n'); sys.exit(1)"]
    return [
        ("resume", SRC_TEXT,
         J({"summary": "Redemarrage du a une fuite memoire; limite ajoutee.", "quotes": ["une fuite memoire dans le cache"]}),
         J({"summary": "Panne reseau.", "quotes": ["la base de donnees a explose"]}), {"max_ratio": 0.8, "min_quotes": 1}),
        ("extraction", "host = api.local\nport = 8080\nuser = svc", J({"host": "api.local", "port": 8080}),
         J({"host": "api.prod", "port": 9090}), {"required": ["host", "port"], "types": {"port": "int"}}),
        ("classement", "a: crash au demarrage\nb: ajouter un bouton", J({"a": "bug", "b": "feature"}),
         J({"a": "bug", "b": "urgent"}), {"labels": ["bug", "feature"], "items": ["a", "b"]}),
        ("docstrings", CALC,
         'def add(a, b):\n    """Somme."""\n    # addition\n    return a + b\n\n\ndef is_pos(x):\n    """Vrai si positif."""\n    return x > 0\n',
         'def add(a, b):\n    """Somme."""\n    return a - b\n\n\ndef is_pos(x):\n    return x > 0\n', {}),
        ("doc", APP, "# App\nLancer `main()` ; voir [le guide](guide.md).\n",
         "# App\nLancer `start_server()` ; voir [le guide](missing.md).\n", {"root": root}),
        ("traduction", J({"hello": "Hello {name}", "n": "%d files"}), J({"hello": "Bonjour {name}", "n": "%d fichiers"}),
         J({"hello": "Bonjour", "n": "%d fichiers"}), {}),
        ("code_repetitif", "DTO Point(x, y)",
         "from dataclasses import dataclass\n\n@dataclass\nclass Point:\n    x: int\n    y: int\n",
         "class Point(:\n    pass\n", {"module": "dto", "check": "from dto import Point\nassert Point(1, 2).y == 2\n"}),
        ("tests_unitaires", CALC,
         "import unittest\nfrom calc import add, is_pos\n\nclass T(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
         "    def test_pos(self):\n        self.assertTrue(is_pos(1))\n        self.assertFalse(is_pos(0))\n",
         "import unittest\nimport calc\n\nclass T(unittest.TestCase):\n    def test_nothing(self):\n        self.assertTrue(True)\n",
         {"module": "calc"}),
        ("conversion", J([{"id": "1", "nom": "a"}, {"id": "2", "nom": "b"}]), "id,nom\n1,a\n2,b\n", "id,nom\n1,a\n", {"from": "json", "to": "csv"}),
        ("regex_sql_script", "Une date ISO 8601 (AAAA-MM-JJ), rien d'autre.", r"^\d{4}-\d{2}-\d{2}$", r"\d+",
         {"kind": "regex", "match": ["2026-11-23"], "nomatch": ["23/11/2026", "2026-11-23x"]}),
        ("migration", "import os\np = os.path.join('a', 'b')\nq = os.path.join('c', 'd')\nprint(p)\n",
         "import posixpath\np = posixpath.join('a', 'b')\nq = posixpath.join('c', 'd')\nprint(p)\n",
         "print('tout reecrit')\n", {"max_changed_lines": 3, "module": "mig"}),
        ("revue", APP, J([{"file": "app.py", "line": 2, "msg": "pass vide"}]),
         J([{"file": "app.py", "line": 99, "msg": "x"}, {"file": "nope.py", "line": 1, "msg": "y"}]), {"root": root}),
        ("commit", "diff --git a/net/relais.py: ajoute le disjoncteur", "feat(relais): ajoute le disjoncteur", "Added some stuff to the code", {}),
        ("donnees_test", "Deux clients avec nom et email.", J([{"nom": "Alice Test", "email": "alice@example.com"}]),
         J([{"nom": "Alice", "email": "alice.martin@orange.fr"}]), {"required": ["nom", "email"]}),
        ("lecture_doc", J({"https://docs.python.org/3/library/sqlite3.html": "SQLite is a C library that provides a lightweight disk-based database."}),
         J({"answer": "Base sur disque legere.", "citations": [{"url": "https://docs.python.org/3/library/sqlite3.html", "quote": "lightweight disk-based database"}]}),
         J({"answer": "x", "citations": [{"url": "http://evil.invalid/", "quote": "invented sentence"}]}), {}),
        ("fiche_catalogue", "---\nname: tdd-guide\ndescription: Guide TDD\n---\n",
         J({"id": "ecc/skill/tdd-guide", "name": "tdd-guide", "kind": "skill", "description": "Guide TDD"}) + "\n",
         J({"id": "x", "name": "ghost-skill"}) + "\n", {}),
        ("erreur_build", "$ " + " ".join(build_cmd) + "\nNameError: name x is not defined",
         J({"command": build_cmd, "error_line": "NameError: name x is not defined", "explanation": "variable x absente"}),
         J({"command": [PY, "-c", "print(1)"], "error_line": "SyntaxError", "explanation": "?"}), {"allowed_commands": [build_cmd]}),
        ("reformulation", "Le lot coute 0 euro, prend 12 minutes et couvre 18 types.",
         "Couvre 18 types en 12 minutes, pour 0 euro.", "Couvre 20 types en 12 minutes.", {}),
    ]
