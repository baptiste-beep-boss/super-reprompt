# Acceptation super-reprompt v3 (dev/accept.py)

Genere le 2026-11-24 16:10.

| Critere | Intitule | Etat | Detail | Preuve |
|---|---|---|---|---|
| A1 | suite d'origine et tests v3 verts | ROUGE | 2/462 en echec : test_hooks.LauncherChain.test_chain_is_silent_and_exits_0_without_any_python, test_hooks.LauncherChain.test_chain_runs_a_working_launcher | `py -3 -m unittest discover -s tests` |
| A2 | plafonds v3, SKILL.md <= 4 950 | vert | code 0 : {'SKILL.md': 3877, 'quick.md': 1889, 'quick': 5765, 'standard': 16993, 'standard+research': 18079, 'max': 25169} | `py -3 dev/measure_loading.py --check` |
| A3 | silence sur demande triviale | vert | 19 tests OK | `unittest test_silence` |
| A4 | cout au repos <= 1 500 tokens | vert | 3 tests OK | `unittest test_l9_migration.A4CoutAuRepos (mesure statique ; /context avant-apres non rejoue)` |
| A5 | catalogue : 0 ecart, 0 non classe | vert | 7 tests OK | `unittest test_catalog.A5` |
| A6 | atteignabilite >= 95 % | vert | 3 tests OK | `unittest test_catalog.A6` |
| A7 | 40 elements executes >= 95 % | vert | 3 tests OK | `unittest test_catalog.A7 (relit catalog/a7-executions.json, executions reelles du lot L5)` |
| A8 | barre conforme a la photo, 7 etats | non mesure | barre en pause sur decision de l'utilisateur (23/11/2026) ; rendu dans l'app non capture | `captures dans l'app` |
| A9 | avancement monotone, erreur de temps | vert | 6 tests OK | `unittest test_bar` |
| A10 | recherche vault < 150 ms a froid (-I -S) | non mesure | index du vault absent sur cette machine (vault.py index, hors depot) | `5 x py -3 -I -S scripts/vault.py search, mediane` |
| A11 | vault.py lint : 0 orpheline creee | vert | 5 tests OK | `unittest test_vault.TestLint` |
| A12 | Relais : 18 types, deux sens | vert | 8 tests OK | `unittest test_relais_verify` |
| A13 | 50 tentatives : 0 secret sorti | vert | 1 tests OK | `unittest test_relais.A13NoExfiltration` |
| A14 | panne d'un puis de tous | vert | 2 tests OK | `unittest test_relais.EndToEnd.test_a14_*` |
| A15 | aucun fournisseur exclu joignable | vert | 2 tests OK | `unittest test_relais.Providers.test_a15_*` |
| A16 | cle invisible (logs, arguments, depot) | vert | 1 tests OK | `unittest test_relais.KeyStoreDPAPI (Windows)` |
| A17 | 40 attaques : 100 % bloquees ou detectees | vert | 2 tests OK | `unittest test_guard (A17)` |
| A18 | <= 3 faux positifs sur 100 | vert | 1 tests OK | `unittest test_guard (A18)` |
| A19 | Eclaireur >= 85 % et pieges arretes | vert | 6 tests OK | `unittest test_eclaireur.A19Besoins test_skillscan.Pieges` |
| A20 | hook < 120 ms en mediane | ROUGE | mediane 372 ms (plancher interpreteur 106 ms ; machine chargee) | `py -3 dev/bench_guard.py (mediane du hook dans une mission)` |
| A21 | licences et empreintes completes | vert | 7 tests OK | `unittest test_catalog.A21 test_v3_invariants.I6Lock` |
| A22 | Windows et Linux verts (CI GitHub) | non mesure | workflow Windows + Linux pret et relu ; CI reelle jamais executee (push = accord requis) ; Linux local : python3 absent de WSL | `workflow .github/workflows/ci.yml relu par script ; CI reelle = apres push (accord requis)` |
| A23 | desinstallation sans trace | vert | 2 tests OK | `unittest test_uninstall` |
| A24 | comparaison a 4 bras | non mesure | banc prepare, NON lance : cout eleve, accord ecrit de l'utilisateur requis (CDC §12) | `evals/v3-a24/PROTOCOLE.md ; py -3 dev/a24_manifest.py --check` |

Bilan : vert 18, rouge 2, non mesure 4 (sur 24)
