# Lot 0 — Audit de départ (cahier des charges V3.1)

Date : 24/11/2026. Audit en lecture seule ; aucune modification du code. Méthode : relevé Git et environnement,
audit du code réel des 10 zones du §2.1 (agent d'exploration, puis contre-vérification manuelle de 4 affirmations clés),
rejeu de la baseline `dev/accept.py` (§2.3).

## 1. État du dépôt (A01, A02)
| Élément | Valeur |
|---|---|
| Branche / HEAD | `v3` / `a163ff08635ab67d9d674165f538645995e0f651` |
| Distant | `origin/v3` identique (0 en avance, 0 en retard) ; `main` = v2.5.0 |
| Arbre de travail | propre : aucune modification, aucun fichier non suivi, aucun stash |
| Worktrees annexes | 7 (`super-reprompt-l5…l10`, `-v25`) ; 4 portent `dev/CHARGEMENT-PAR-PALIER.md` modifié (fins de ligne seulement) — **préservés, non touchés** |
| Environnement | Windows 11, Git Bash (MSYS2), Python 3.13.14, Node 24.13.1, Git 2.53, Claude Code 2.1.310 (CLI) / 2.1.330 (app) |
| CI | GitHub Actions Windows + Linux, dernier passage vert (run 45435621865) |

## 2. Baseline (§2.3)
Voir section 6 (rejeu `accept.py` du 24/11/2026).

## 3. Les 10 ruptures du §2.1, revalidées sur le code
| # | Zone | Verdict | Preuve | Conséquence |
|---|---|---|---|---|
| 1 | Cadrage → PLAN.json | **Confirmé** | aucun code de production n'écrit PLAN.json ; le skill produit ORDRE.md + STATE.json (`skills/super-reprompt/SKILL.md:65-68`) ; aucun appel de `guard.py seal` hors du script lui-même | le cadrage n'alimente pas l'exécution |
| 2 | Plan → manager | **Partiel** | `scripts/manager.py:34-48` lit PLAN.json sans validation ; dépendance inconnue = tâche jamais prête, pas de détection de cycle ; aucun hash ORDRE↔PLAN (`guard_core.py:798,830` ne scelle que ORDRE.md) | un plan incohérent ou modifié passe |
| 3 | Relais | **Confirmé** | `relais plan --json` existe (`net/relais.py:995`) et `econ.decide` sait le lire (`econ.py:57`), mais `manager next` ne l'appelle que si l'option est passée ; personne ne génère `relais.json` | aucune tâche ne part au Relais sans geste manuel |
| 4 | Archiviste / Synthèse | **Confirmé** | `agents/sr-archiviste.md`, `sr-synthese.md` existent ; aucun script ni hook ne les invoque | fin de phase laissée au bon vouloir du modèle |
| 5 | Vigie | **Partiel** | `drift` déclenché seulement par `manager done` (`manager.py:111`) ; `post` jamais appelé ; jalons 25/50/75/100 % absents du code ; `PROGRESS.json` lu (`guard_core.py:902`) mais jamais écrit → garde-budget du scellé inopérante | dérive vue par tâche, jamais par jalon ; budget scellé mort |
| 6 | Éclaireur | **Confirmé** | `scripts/eclaireur.py:55` `TYPES = ("skill",)` alors que le catalogue contient agents (72), commandes (105), hooks (53), règles (121), schémas (17) ; Éclaireur appelé par personne | capacités non-skills jamais proposées |
| 7 | vendor/ | **Partiel** | provenance présente (`vendor/LOCK.json` : commit, licence, SHA-256 par fichier ; notices) ; aucune activation runtime ; hooks Ponytail non câblés ; LOCK non vérifié au chargement | dépendances dormantes ; intégrité vérifiée seulement en test |
| 8 | Barre | **Confirmé** | `hooks/bar/register.tsx` alimentée par l'outil `mcp__super-reprompt__project` et `$.store`, jamais par PLAN.json | deux listes de tâches à synchroniser à la main |
| 9 | Événements / état | **Partiel** | journal `journal.ndjson` écrit par deux schémas (`vault.py log`, `guard_core.journal`) ; `econ.ndjson` sans verrou ; écritures atomiques en 3 implémentations, aucune pour SCELLE.json/derives.json ; statuts de tâche `todo/done/echec` seulement ; reçus vérifiés mais non conservés | pas de journal unifié, pas de machine à états, pas de reçu |
| 10 | Reprise | **Partiel** | `next` rejouable ; `done` non idempotent (dépense et journal dupliqués, escalade de dérive faussée `guard_core.py:923-936`) ; tâche `echec` sortie de la frontière sans retry ni signal | reprise correcte pour `next`, fausse pour `done`/`echec` |

## 4. Points d'entrée utilisateur réels
- Skill unique `super-reprompt` (+ 12 références). Aucune commande déclarée.
- Hooks : UserPromptSubmit (suggestion), SessionStart compact|resume (rappel), Stop (porte de fin de mission), PreToolUse (pare-feu, silencieux hors mission scellée). Module `hooks/bar/register.tsx`.
- Agents : 14 fiches, **aucune lancée par du code**.
- Scripts CLI : 4 cités par le skill (`scan_capabilities`, `validate_order`, `mission`, `launch`) ; tous les autres (`guard`, `manager`, `econ`, `eclaireur`, `relais`, `catalog`, `vault`…) uniquement manuels ou cités par les fiches d'agents.

## 5. Responsabilités dupliquées
1. Recherche de capacités : `eclaireur.py plan`, `net/scout.py trouver`, `catalog.py search`, `scan_capabilities.py`.
2. Vérification : `hook_stop.py` (STATE.verification) vs `manager done` (PLAN.preuve) vs `mission.py verify` vs `guard drift`.
3. Budget : `mission.py spent` vs `econ.ndjson` vs PROGRESS.json (jamais écrit) vs `budget.py` vs `SCELLE.budget`.
4. Liste de tâches : barre (`$.store`) vs PLAN.json vs STATE.json vs `mission.py status`.
5. Journal : deux schémas dans `journal.ndjson` + `hook.log`.
6. Arbitrage de délégation : `econ.decide` vs `relais.run_plan` vs consignes des fiches d'agents.
7. Écriture atomique : trois implémentations, aucune pour la Vigie.

## 6. Baseline rejouée (`dev/accept.py`, 24/11/2026 17:57, HEAD a163ff0)
**Vert 20, rouge 1, non mesuré 3 sur 24** (la référence du §2.3 était 18 / 2 / 4 avec 462 tests et 2 échecs).
- A1 : 469 tests, 0 échec, 1 sauté (lien symbolique : droits Windows).
- A20 **rouge** : médiane 191 ms, plancher interpréteur 65 ms, machine chargée. Mesure séparée du même jour : vraie
  commande du hook 300 ms, plancher shell + Python 221 ms, code du pare-feu +23 ms.
- Non mesurés : A8 (barre en pause), A22 (le script ne lit pas la CI réelle — la CI GitHub a pourtant tourné et est
  verte, run 45435621865), A24 (banc complet non lancé ; un banc réduit n = 1 et une contre-épreuve n = 2 ont tourné,
  voir `plugins/super-reprompt/evals/v3-a24/`).
- A4 « vert » est une mesure statique ; le coût au repos réel (`/context`) n'est pas rejoué : à mesurer (A04 V3.1).
Écart avec la référence : +2 critères verts (A1, A10), dus aux correctifs du lanceur de hooks et à l'index du vault.

## 7. Risques principaux
| Risque | Gravité | Parade proposée |
|---|---|---|
| Ajouter des couches sans relier le cycle (répéter V3) | élevée | lots 1-3 d'abord ; chaque lot doit faire passer une mission réelle de bout en bout |
| Benchmark non concluant (effet plafond, n faible) | élevée | corpus avec tâches où Claude seul échoue ; ≥ 3 répétitions ; batterie étendue figée |
| Quota hebdomadaire Pro | moyenne | lots courts ; benchmark par paliers ; mesure `get_usage` avant/après |
| Hooks sous Windows (latence, interpréteur) | moyenne | lanceur commun déjà corrigé ; A20 justifiée par mesure du plancher shell+Python |
| Relais sans fournisseur | moyenne | mode sans provider pleinement fonctionnel ; bras Relais seulement si l'utilisateur connecte un fournisseur |
| Barre (pause décidée par l'utilisateur le 22/11) | à décider | voir décisions à valider |
