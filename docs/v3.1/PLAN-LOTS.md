# Plan de réalisation V3.1 (proposé après le lot 0, à valider)

Principe : relier avant d'ajouter. Chaque lot se termine par une mission réelle qui traverse le code modifié, des tests
ciblés, la suite complète, `accept.py`, et une preuve dans `docs/v3.1/PREUVES-LOTx.md`. Aucun déplacement de fichiers
cosmétique : les neuf pôles du §4 sont documentés comme une carte des modules existants, pas imposés par un `src/`.

| Lot | Contenu, sur l'existant | Ruptures traitées | Sortie |
|---|---|---|---|
| 1 Contrats | `scripts/contracts.py` (stdlib) : schémas versionnés STATE/PLAN/SCELLE/événement/reçu, validateur, écriture atomique unique (remplace les 3 copies et couvre SCELLE/derives), journal `events.ndjson` unique avec `event_id` dédupliqué ; migration de `journal.ndjson` ; statuts proposed/ready/running/review/done + blocked/failed/cancelled/skipped | 9, 10 (base) | tests de contrats, exemples valides/invalides, migration testée sur copie |
| 2 Compilateur | `scripts/compile_plan.py` : ORDRE+STATE validés → PLAN.json (IDs stables, dépendances, critères, `source_order_hash`) ; scellement appelé automatiquement ; PLAN haché dans le scellé ; skill modifié pour l'appeler | 1, 2 | intake → ordre → plan → scellé testé de bout en bout |
| 3 Orchestration | `manager.py` : validation du plan, statut `running`, `done` idempotent, retry borné de `failed`, reçus conservés (`receipts/`), Vigie aux jalons 25/50/75/100 %, archiviste groupé en fin de phase, synthèse à la clôture, `relais plan` produit et transmis automatiquement quand la tâche est éligible | 3, 4, 5, 10 | une mission réelle exécutée sans étape manuelle cachée ; crash simulé et reprise sans doublon |
| 4 Éclaireur universel | types étendus à agent/commande/hook/règle/script/schéma ; fusion de `eclaireur plan` et `scout trouver` en un seul classement ; appel depuis le compilateur (plan de capacités par tâche) ; coût de contexte mesuré | 6 | tests de sélection par type ; budget de contexte mesuré |
| 5 Relais | contrat ProviderAdapter commun, health_check, circuit breaker et retries bornés déjà présents → alignés sur le contrat ; exécution de code externe désactivée faute de sandbox réel | 3 | tests par mocks ; réel seulement si tu connectes un fournisseur |
| 6 Économie | `econ.ndjson` étiqueté actual/estimated/projected/unavailable ; un seul budget (fusion mission.spent / PROGRESS / econ / SCELLE) ; décision de routage comparative tracée | budget dupliqué, garde-budget mort | rapport de coût reproductible |
| 7 Mémoire | archiviste et synthèse raccordés (lot 3) ; brief de reprise ; contrôle inter-projets | 4 | mémoire alimentée à la clôture, relue à la reprise |
| 8 Vigie | `post` raccordé, budget réel, réponse graduée info/avertissement/blocage, dérogations journalisées ; A20 : mesure + justification documentée (plancher Windows) | 5 | blocage réel en test et en session réelle |
| 9 Progression | la barre lit PLAN.json + events (plus de liste séparée) ; ETA à partir des durées observées ; capture réelle dans l'app | 8 | capture + test de synchronisation (si tu relances la barre) |
| 10 Évaluation | corpus simple/moyen/complexe avec tâches où Claude seul échoue, batterie étendue figée, ≥ 3 répétitions, juge aveugle, coût total ; bras : Claude seul, v2.5, V3.1 locale, V3.1 + contre-épreuve adverse, V3.1 + Relais (si fournisseur) | benchmark faible | rapport Go/No-Go |

Séquence : 1 → 2 → 3 (socle), puis 4, 6, 7, 8 (indépendants, fichiers disjoints), 5, 9, 10.
Le banc du lot 10 est préparé dès le lot 1 et rejoué en version courte après le lot 3.
