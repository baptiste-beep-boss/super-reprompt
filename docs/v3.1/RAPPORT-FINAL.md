# Super-Reprompt V3.1 — rapport final (§ 21.2 du cahier, 25/11/2026)

Branche `v3`, de la baseline `0da36a6` (lot 0) jusqu'au commit de ce rapport. Lots 1 à 10 réalisés dans l'ordre 1, 2, 3, puis 4, 6, 7, 8, puis 5, 9, 10. Chaque lot s'est clos sur :
- une mission réelle rejouable (`plugins/super-reprompt/dev/mission_lotN.py`) ;
- des tests écrits avant le code ;
- la suite complète et `dev/accept.py` ;
- un fichier de preuves (`docs/v3.1/PREUVES-LOTn.md`) ;
- un commit, puis le push de `v3` par la session de pilotage, CI GitHub Windows + Linux verte.

## 1. Résumé exécutif
**Ce qui fonctionne réellement.** Le cycle mission est raccordé de bout en bout et exécutable sans étape manuelle cachée :
- cadrage, puis `mission.py ready` : compilation de `PLAN.json` lié par empreinte à `ORDRE.md` et au scellé ;
- boucle `manager.py next` / `done` : reçus, reprise sans doublon, nouvelle tentative bornée ;
- Vigie graduée qui **arrête réellement** une tâche, avec dérogation journalisée ;
- Éclaireur sur 7 types de capacités, avec budget de contexte mesuré ;
- Relais par un contrat d'adaptateur commun ;
- comptabilité étiquetée et budget unique ;
- mémoire alimentée par script à chaque fin de phase et à la clôture ;
- barre de progression projetée depuis `PLAN.json` et `events.ndjson`.

Ce cycle est prouvé par 9 missions réelles scriptées, de 7 à 17 vérifications chacune, toutes au vert. La suite compte 556 tests, 0 échec.

**Gains observés.** Aucun gain de tokens. Sur le banc de 27 sessions (3 tâches × 3 bras × 3 répétitions), V3.1 consomme -1 % à **+22 %** de tokens médians de plus que Claude seul, à qualité égale aux tests. Ce n'est pas la réduction de 20 % visée. Sur la tâche difficile, c'est le bras le plus robuste (5/6 contre 2/6), mais l'écart tient à des tests de temps : signal faible.

**Cause centrale.** Sur une invite courte, le cycle V3.1 ne se déclenche pas : le plugin ajoute son contexte sans changer l'exécution (§ 10).

## 2. État initial et état final

| Rupture (audit `AUDIT-LOT0.md`) | Avant | Après (lot) |
|---|---|---|
| 1. Cadrage → plan | rien n'écrivait `PLAN.json` | `compile_plan.py`, appelé par `mission.py ready` ; `source_order_hash` (2) |
| 2. Plan → manager | plan non validé, cycles et dépendances inconnues acceptés, aucun hash | validation stricte, `plan_sha256` dans le scellé, `PLAN_MODIFIE` en dérive (2, 3) |
| 3. Relais | aucun `relais.json` produit | produit et transmis automatiquement par `next` ; contrat `ProviderAdapter` (3, 5) |
| 4. Archiviste et synthèse | jamais invoqués | rangement par script en fin de phase, `REPRISE.md` et brief de synthèse à la clôture (3, 7) |
| 5. Vigie | dérive vue par tâche seulement, `post` jamais appelé, garde budget morte | jalons 25/50/75/100 %, `post` après chaque exécution, gravités, blocage réel, budget 80/100/150 % (3, 6, 8) |
| 6. Éclaireur | skills seulement | 7 types, intégrité vérifiée, raisons, budget de contexte mesuré, raccordé au compilateur (4) |
| 7. vendor/ | intégrité vérifiée en test seulement | intégrité vérifiée à la sélection, pour tout le catalogue sélectionnable (4) |
| 8. Barre | liste séparée, alimentée à la main | projection `BAR.json` de `PLAN.json` et des événements, ETA observé (9) |
| 9. Événements et état | deux schémas de journal, 3 écritures atomiques, pas de machine à états | `contracts.py` : 5 contrats versionnés, une écriture atomique, `events.ndjson` dédupliqué, 9 états, reçus (1) |
| 10. Reprise | `done` non idempotent, pas de nouvelle tentative | `done` idempotent après crash, 2 tentatives au plus puis `blocked`, `status` (3) |

Responsabilités dédupliquées :
- **budget** : `econ.ndjson` seul, `PROGRESS.json` en est une projection ;
- **journal** : `events.ndjson` seul ;
- **écriture atomique** : `contracts` seul ;
- **liste de tâches** : `PLAN.json` seul, la barre en est une projection.

## 3. Fichiers

77 fichiers touchés jusqu'au lot 10 intermédiaire, puis ceux de ce rapport : 51 créés, 26 modifiés, aucun supprimé. Liste exacte : `git diff --name-status 0da36a6..HEAD`. Principaux fichiers et raison :

| Fichier | Statut | Raison |
|---|---|---|
| `scripts/contracts.py`, `schemas/` | créé | contrats, stockage, journal, états, reçus, migration (lot 1) |
| `scripts/compile_plan.py` | créé | ordre → plan, couverture, scellement (lot 2) |
| `scripts/manager.py` | modifié | boucle raccordée : reçus, reprise, Vigie, mémoire, Relais, barre (lots 3, 6, 7, 8, 9) |
| `scripts/eclaireur.py` | modifié | Éclaireur universel (lot 4) |
| `scripts/econ.py` | modifié | étiquettes, budget unique, routage comparatif, rapport (lot 6) |
| `scripts/memoire.py` | créé | rangement déterministe, `REPRISE.md`, étanchéité (lot 7) |
| `scripts/guard_core.py` | modifié | journal unique, écritures atomiques, `plan_sha256`, gravités, budget gradué, dérogations (lots 1, 2, 8) |
| `scripts/vault.py` | modifié | journal unique, verrou unique ; correctif `index --full` (lots 1, 7) |
| `scripts/progress.py` | créé | projection de la barre et ETA (lot 9) |
| `scripts/mission.py` | modifié | `ready` compile et scelle ; `spent` dans le journal unique (lots 2, 6) |
| `net/adapters.py` | créé | contrat ProviderAdapter, politique de repli, bac à sable déclaré absent (lot 5) |
| `net/relais.py` | modifié | passage par l'adaptateur ; exécution de code modèle coupée (lot 5) |
| `hooks/bar/register.tsx` (+ test) | modifié | la barre lit `BAR.json` (lot 9) |
| `agents/*.md` (6) | modifié | 5 en-têtes YAML illisibles corrigés ; fiches Vigie, super-manager et archiviste alignées (lots 1, 3, 7, 9) |
| `tests/test_*.py` (12 nouveaux) | créé | un fichier de tests par lot, plus les non-régressions |
| `dev/mission_lot1..9.py`, `dev/a24_v31*.py` | créé | missions réelles et banc du lot 10 |
| `docs/v3.1/PREUVES-LOT1..9.md`, ce rapport, `evals/v3-a24/v31/` | créé | preuves et résultats bruts |

## 4. Flux mission complet (reproductible)
```
# cadrage (skill super-reprompt) -> .super-reprompt/<slug>/STATE.json + ORDRE.md ; STATE.tasks pour le decoupage
py -3 scripts/mission.py ready <slug>                 # PLAN.json compile + SCELLE.json (empreintes ordre et plan)
py -3 scripts/manager.py next --project . --slug <slug>   # Vigie, relances, relais.json, dispatch -> running
py -3 scripts/manager.py done <T> --report r.txt --tokens N --project . --slug <slug>   # preuve, recu, Vigie, memoire, barre
py -3 scripts/manager.py status --project . --slug <slug>  # reprise
py -3 scripts/econ.py rapport .super-reprompt/<slug>      # cout : actual / estimated / projected
```
Démonstrations exécutables : `py -3 plugins/super-reprompt/dev/mission_lot3.py`, qui va du cadrage à « FIN » avec crash et nouvelle tentative, et `mission_lot8.py` pour un blocage réel.

## 5. Résultats de tests
- `py -3 -m unittest discover -s tests` (par `dev/accept.py`) : **556 tests, 0 échec, 1 sauté**, à comparer aux 469 de la baseline.
  - Le test sauté porte sur les liens symboliques (droits Windows).
  - Un échec intermittent a été vu une fois au lot 7 et ne s'est jamais reproduit. Cause non prouvée ; durcissement de l'écriture atomique.
- `claude plugin test` (mod de la barre) : 12/12. `claude plugin validate` : passe (avertissement : icône absente).
- Missions réelles : lot 1 11/11, lot 2 12/12, lot 3 17/17, lot 4 7/7, lot 5 8/8, lot 6 12/12, lot 7 13/13, lot 8 14/14, lot 9 8/8.
- CI GitHub, Windows et Linux, verte à chaque push (dernier run cité par la session de pilotage : 45649885556).
- Défauts trouvés en chemin, corrigés avec un test chacun :
  - perte d'écriture concurrente de `vault.py log` sous Windows ;
  - frontière du manager aveugle aux statuts compilés ;
  - faux `PLAN_MODIFIE`, sur `execution_mode` puis sur `blocked_by` ;
  - empreinte des skills multi-fichiers ;
  - `vault.py index --full` qui plantait ;
  - 5 fiches d'agents chargées sans leur `model` ;
  - `progress.py --help` qui créait un dossier ;
  - deux défauts du juge du banc.

## 6. Métriques et comparaison à la baseline
| Mesure | Baseline (lot 0, 24/11) | Final (25/11) |
|---|---|---|
| `accept.py` (24 critères v3) | vert 20, rouge 1, non mesuré 3 | vert 19, rouge 1, non mesuré 4 |
| Tests | 469, 0 échec | 556, 0 échec |
| Hook pare-feu, coût propre | +23 ms au-dessus du plancher | +10 ms en appel direct (mesure du 25/11) |
| Hook, commande réelle | 300 ms (machine chargée) | 192 ms au calme, 435 à 678 ms sous charge |
| Tokens V3 vs Claude seul (banc) | moyen +85 %, difficile +11 % (n = 1) | moyen -1 %, difficile +22 %, facile +8 % (n = 3, médianes) |
| Qualité aux tests cachés | 100 % pour tous les bras (n = 1) | 100 % pour tous les bras (n = 3) |
| Robustesse sur la tâche difficile | v3 1/4 (n = 1) | V3.1 5/6, Claude seul 2/6, v2.5 4/6 (n = 3) |

Notes de lecture :
- Le passage d'A10 de vert à « non mesuré » est une condition de machine : l'index du vault personnel est absent ici. A10 est mesuré par la mission du lot 7 (médiane 212 ms).
- **Coût réel** : 0 €, abonnement Pro, aucun fournisseur payant.
- **Coût estimé du banc** : environ 10 points de quota hebdomadaire pour 27 sessions, session de pilotage comprise.
- Tous les tokens viennent de l'usage réel de `claude -p`.

## 7. Critères A01 à A30
| ID | Verdict | Preuve |
|---|---|---|
| A01 Audit | PASS | `docs/v3.1/AUDIT-LOT0.md` |
| A02 Intégrité du dépôt | PASS | aucun nettoyage ni réinitialisation ; worktrees annexes non touchés (celui de la v2.5 seulement lu comme `--plugin-dir`) |
| A03 Contrats | PASS | `schemas/`, `test_contracts` (21), PREUVES-LOT1 |
| A04 Coût au repos | NOT MEASURED | seulement la mesure statique d'`accept.py` A4 ; `/context` avant/après non rejoué |
| A05 Compilation d'ordre | PASS | `mission.py ready`, PREUVES-LOT2 (12/12) |
| A06 Plan exécutable | PASS | validation au chargement, `test_orchestration`, PREUVES-LOT3 |
| A07 Cycle mission | PASS (boucle scriptée) | `mission_lot3.py` 17/17, du cadrage à FIN ; pas rejoué dans une session Claude Code interactive |
| A08 Barre | NOT MEASURED | capture dans l'app impossible depuis cette session ; procédure : `dev/show_bar.md` (§ V3.1) |
| A09 ETA | PASS | `progress.py`, `test_progress`, PREUVES-LOT9 |
| A10 Mémoire / Obsidian | FAIL (performance) | fonctionnel et mesuré : médiane 212 ms contre 150 ms visés, plancher de l'interpréteur 134 ms (PREUVES-LOT7) |
| A11 Archiviste | NOT MEASURED | raccordé (étape précise, sans doublon, partie mécanique en script) ; l'agent n'a jamais été exécuté |
| A12 Synthèse | NOT MEASURED | brief à la clôture fondé sur les reçus et `REPRISE.md` ; l'agent n'a jamais été exécuté |
| A13 Éclaireur universel | PASS | 5 types retenus dans un vrai plan (PREUVES-LOT4) |
| A14 Progressive disclosure | PASS | ≤ 6 000 tokens par tâche, mesurés (0,44 % du catalogue) |
| A15 Provenance vendor | PASS | intégrité de tout le catalogue sélectionnable vérifiée (`test_eclaireur_universel`) |
| A16 Relais sans fournisseur | PASS | PREUVES-LOT5 (repli local annoncé) |
| A17 ProviderAdapter | PASS | `test_adapters` (14), `health_check` |
| A18 Confidentialité | PASS | `test_relais.A13NoExfiltration` (0 sur 50), scan de secret sur le chemin de l'adaptateur |
| A19 Fallback | PASS | tentatives bornées, breaker, repli fini (`test_adapters`, `test_relais` A14) |
| A20 Latence des hooks | FAIL | médiane réelle 192 ms au calme ; plancher shell + Python de 121 ms, au-dessus de la cible à lui seul ; code du pare-feu +10 ms ; lanceur +71 ms à instruire (PREUVES-LOT8) |
| A21 Reprise | PASS | crash simulé puis reprise sans doublon (`mission_lot3.py`, `test_orchestration`) |
| A22 CI | PASS | CI GitHub Windows + Linux réellement exécutée et verte à chaque lot (runs cités dans les rapports de lot) |
| A23 Tests | PASS | 556 tests, 0 échec ; seul échec non reproduit : intermittent documenté (PREUVES-LOT7) |
| A24 Benchmark | PASS (protocole exécuté) | 27 sessions, n = 3, tests cachés + batterie étendue re-jugée, tokens, durées (`evals/v3-a24/v31/`) ; pas de juge LLM ; n = 3 reste faible |
| A25 Économie | PASS | étiquettes séparées, routage tracé (PREUVES-LOT6) |
| A26 Vigie | PASS | jalons, avant dispatch, après exécution, budget (PREUVES-LOT8) |
| A27 Sécurité | PASS (en test) | blocage avant et après l'action ; code du modèle jamais exécuté ; aucune prétention de bac à sable |
| A28 Portabilité | PASS (Windows, Linux) | CI deux OS ; chemins avec espaces et accents dans toutes les missions ; macOS NOT MEASURED |
| A29 Documentation | PASS | README (§ « The V3.1 mission cycle »), `schemas/README.md`, `net/RELAIS.md`, `dev/show_bar.md`, preuves par lot |
| A30 Clôture | PASS | ce rapport |

Bilan sur 30 : **24 PASS, 2 FAIL (A10 en performance, A20), 4 NOT MEASURED (A04, A08, A11, A12).**

Quatre PASS portent une réserve écrite dans la ligne :
- A07 et A27 n'ont pas été rejoués en session interactive ;
- A24 n'a pas de juge LLM et reste à n = 3 ;
- A28 ne couvre pas macOS.

## 8. Limites restantes, risques, opérations non exécutées
- **Non exécuté**, avec la raison :
  - capture de la barre dans l'app (A08) : à faire par l'utilisateur ;
  - agents archiviste, synthèse et Vigie en session réelle : coût et session interactive ;
  - fournisseur externe du Relais : connexion réservée à l'utilisateur, budget 0 € ;
  - juge LLM du banc : quota ;
  - `/context` au repos (A04) ;
  - macOS.
- **Risques** :
  - les seuils de l'Éclaireur (0,5) et le modèle de coût du routage sont des hypothèses non calibrées (n = 0) ;
  - les dérogations reposent sur une attribution déclarative (`--by`), comme les avenants ;
  - les tests de robustesse du banc sont sensibles à la charge (d'où le re-jugement) ;
  - le lanceur `hooks/run.sh` coûte environ 71 ms par appel.

## 9. Fournisseurs externes (facultatif, aucun secret dans le dépôt)
L'utilisateur, et lui seul, connecte un fournisseur gratuit avec `py -3 plugins/super-reprompt/net/relais.py connect <id>`. La clé est saisie au terminal et stockée par DPAPI sous Windows. La liste et l'état des fournisseurs sont dans `net/providers.json`, la procédure dans `net/RELAIS.md`. Sans fournisseur, tout fonctionne en local, et le dit.

## 10. Recommandation Go / No-Go
- **No-Go sur la promesse de performance.** La cible de −20 % de tokens médians à qualité non inférieure n'est pas atteinte. À n = 3, V3.1 coûte de -1 % à +22 % de plus que Claude seul, pour une qualité égale aux tests cachés. Aucune release et aucune annonce d'économie ne sont justifiées.
- **Go pour garder V3.1 comme base de travail** sur `v3`. Le cycle est enfin cohérent, testé, reprenable et gouverné : il bloque réellement, ne ment pas sur les coûts et ne déclare pas de bac à sable fictif. La qualité n'est pas inférieure à celle de la v2.5 ni de Claude seul.

Priorités de la prochaine itération, dans l'ordre :
1. **Engager le cycle de lui-même sur une tâche de code.** Constat central du banc : sur une invite courte (« Réalise le projet décrit dans ENONCE.md »), V3.1 ne cadre pas, ne compile pas de plan et n'utilise ni la Vigie ni le Relais. Il ajoute du contexte sans changer l'exécution. Il faut un déclencheur qui reconnaisse une tâche de code non triviale et lance le cycle compact, quick puis `ready` puis boucle, sans attendre une demande de cadrage. Il faut ensuite rejouer le banc.
2. **La contre-épreuve adverse comme levier de qualité** (`evals/v3-a24/ANALYSE.md`, § 4) : seule méthode à 8/8 en robustesse aux deux essais, pour environ 3 fois plus de tokens. Elle est à intégrer comme option du cycle pour les tâches difficiles, avec mesure du gain contre le surcoût.
3. Relais : sans fournisseur connecté, aucune économie n'est possible. À mesurer avec un fournisseur gratuit réel, si l'utilisateur en connecte un.
4. A20 : instruire les 71 ms du lanceur `hooks/run.sh`.
5. A08 (capture de la barre), puis A11 et A12 (agents exécutés en session réelle), puis A04 (`/context` au repos).
6. Calibrer les seuils de l'Éclaireur et le modèle de coût du routage sur des reçus réels, et ajouter un juge LLM aveugle au banc.
