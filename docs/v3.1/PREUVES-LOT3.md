# Lot 3 — Orchestration (preuves, 24/11/2026)

## Livré (ruptures 3, 4, 5 et 10 de l'audit)
`scripts/manager.py` est raccordé au cycle V3.1, sans nouveau module.

**`next`**
- Valide `PLAN.json` au chargement (`contracts`) : un cycle ou une dépendance inconnue donne un refus, code 2.
- Relance les tâches `failed`, avec une limite de 2 tentatives. Au-delà, la tâche passe `blocked` et la question remonte à l'utilisateur.
- Quand une tâche typée est prête, **produit seul le plan du Relais** (`net/relais.py plan --json`). Le résultat est écrit dans `relais.json`, transmis à `econ.decide` et journalisé (`relais.planned`).
- Passe chaque tâche dispatchée en `running`, une seule fois.

**`done`**
- Écrit un **reçu** `receipts/<tâche>/<run>.json` par tentative ; les échecs sont conservés.
- Fait suivre à la tâche les transitions validées `running → review → done | failed`.
- Est **idempotent**. S'il est rejoué après un crash, la preuve n'est pas réexécutée : le reçu fait foi. La dépense est dédupliquée par `run_id` et l'événement `task.done` aussi.
- Déclenche la **Vigie aux jalons 25/50/75/100 %** : `vigie.milestone` puis `guard drift`, et `sr-vigie` signalé si la dérive est grave.
- Écrit le **brief de l'archiviste** groupé en fin de phase (≤ 3 000 tokens, une fois par phase).
- Écrit le **brief de la synthèse** à la clôture, une seule fois.

**`status`** : avancement, tâches à reprendre et tâches prêtes.

**Contrat** : `failed → blocked` est ajouté (tentatives épuisées). Le vocabulaire canonique `failed` remplace `echec` ; l'attente de `test_econ` est mise à jour en conséquence.

**Fiche `sr-super-manager`** : mise à jour pour la nouvelle boucle.

## Mission réelle
`py -3 dev/mission_lot3.py` : **17/17 PASS**. Elle va du cadrage (`mission.py ready`) jusqu'à « FIN » par la seule boucle `next`/`done`. Le chemin du projet contient espaces et accents. Déroulé :
1. T1 est dispatchée, puis un crash est simulé après l'écriture du reçu (code 9).
2. `status` explique la reprise.
3. La reprise passe T1 à done sans rejouer la preuve.
4. T2, tâche typée : le plan du Relais est produit automatiquement. Comme aucun fournisseur n'est connecté, la tâche est gardée en local.
5. T2 échoue, puis réussit à la tentative 2/2 ; la fin de phase P1 lance le brief `sr-archiviste`.
6. T3 termine la mission ; le brief `sr-synthese` est écrit.
7. « FIN ».

Contrôles finaux :
- jalons 25/50/75/100, une fois chacun ;
- 3 `task.done` et 4 lignes de dépense (une par run) ;
- 4 reçus valides, dont l'échec `T2-a1` ;
- aucun artefact orphelin : chaque reçu de succès est référencé par le plan.

## Tests
- `test_orchestration` : 8 tests, rouge vu avant implémentation.
  - Le passage au vert a révélé que la transition `failed → blocked` manquait au contrat ; elle est corrigée.
  - Couverture : plan invalide, `running` une seule fois, reçu idempotent, crash et reprise, nouvelle tentative bornée, jalons et mémoire, Relais automatique, `status`.
- `py -3 dev/accept.py` : A1 = 508 tests, 0 échec, 1 sauté. Bilan : vert 19, rouge 1, non mesuré 4.
  - A20 rouge : médiane 201 ms pour un plancher de l'interpréteur à 72 ms (lot 8).
  - A10 non mesuré : index du vault absent sur cette machine.

## Critères V3.1
- A06 Plan exécutable : **PASS**. Le manager charge, valide et ordonne le plan.
- A07 Cycle mission : **PASS en script**. La mission complète s'exécute sans étape manuelle cachée. Pas encore rejouée dans une vraie session Claude Code : cela viendra avec le banc du lot 10.
- A21 Reprise : **PASS**. Crash simulé, reprise sans doublon ni perte.
- A11 Archiviste et A12 Synthèse : **raccordés**, avec étape précise, brief et événement dédupliqué. L'exécution réelle des agents est **NOT MEASURED** : elle demande une session et un vault.
- A26 Vigie : jalons réellement déclenchés en script. **PASS partiel**, complété au lot 8.

## Non vérifié
- Exécution des agents `sr-archiviste` et `sr-synthese` dans une vraie session.
- Délégation effective par le Relais : aucun fournisseur n'est connecté, donc tout reste local.
- CI Linux, après le push de la session mère.
