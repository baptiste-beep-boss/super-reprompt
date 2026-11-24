# Lot 1 — Contrats (preuves, 24/11/2026)

## Livré
- `plugins/super-reprompt/scripts/contracts.py` (stdlib, sans réseau) regroupe :
  - les schémas versionnés `state` 1, `plan` 2, `seal` 1, `event` 1 et `receipt` 1 ;
  - un validateur, avec un mode strict pour les plans compilés ;
  - une écriture atomique unique : temporaire unique, `fsync`, `os.replace` ;
  - une lecture stricte : un fichier illisible n'est jamais écrasé ;
  - un verrou portable ;
  - le journal unique `events.ndjson`, avec `event_id` dédupliqué par `dedup_key` et ligne tronquée ignorée puis refermée ;
  - la machine à états `proposed → ready → running → review → done`, plus `blocked`, `failed`, `cancelled` et `skipped` ;
  - les reçus `receipts/<tâche>/<run>.json`, écrits une seule fois, avec les champs inconnus à `null` ;
  - la migration idempotente de l'ancien `journal.ndjson`, sans toucher à l'original.
- Exemples valides et invalides pour chaque contrat : `plugins/super-reprompt/schemas/examples/`, documentés dans `schemas/README.md`.
- Raccordements : ruptures 9 et 10 de l'audit, en partie.
  - Le pare-feu (`guard_core.journal`) écrit dans `events.ndjson`. La dérive lit l'ancien et le nouveau journal.
  - SCELLE, avenants, `derives.json` et FERME passent par l'écriture atomique.
  - `vault.py log` écrit dans `events.ndjson`. Son verrou est délégué à `contracts.Lock`.
  - `manager._save` passe par `save_checked` (plan validé avant écriture).
  - `econ.spend` passe par un ajout sous verrou.
  - `_lib.write_json` et `_lib.write_text` délèguent à `contracts`.
  - Les trois implémentations d'écriture atomique n'en font plus qu'une.

## Défaut trouvé et corrigé
Avec 30 `vault.py log` concurrents, une écriture était perdue dans 1 rejeu sur 3. Erreur observée :
`PermissionError: [Errno 13] ... locks\ec6c4d26.lock`.

Le verrou de `vault.py` ne traitait pas l'erreur que Windows lève quand un autre processus supprime le fichier de verrou. Après délégation à `contracts.Lock`, 5 rejeux sur 5 donnent 30/30 (`conc.py`, dans le bloc-notes de la session).

## Mission réelle
`py -3 dev/mission_lot1.py` : **11/11 PASS**. Elle tourne dans un projet jetable dont le chemin contient des espaces et des accents, et appelle de vrais sous-processus. Les étapes, dans l'ordre :
- `guard.py seal` ;
- `contracts.py validate` du scellé et de l'état ;
- le pare-feu refuse une écriture hors périmètre (code 2, `F07`), avec `TEMP` distinct du projet ;
- `vault.py log` ;
- `manager.py done T1` : preuve par script et plan réécrit par `save_checked` ;
- `contracts.py migrate` exécuté deux fois : 2 lignes migrées, puis 0 ;
- le journal contient `guard.deny`, `log.decision`, `log.vigie`, `log.tache` et les entrées `legacy` ;
- tous les événements valident le contrat `event` v1, avec des `event_id` uniques ;
- aucun temporaire ni verrou ne reste.

## Tests
- `py -3 -m unittest test_contracts` : 21 tests OK.
  - Le passage au rouge a été vu avant l'implémentation.
  - Ce passage a aussi révélé un vrai défaut : la ligne tronquée avalait l'écriture suivante.
- Premier passage de la suite complète : 534 tests, 2 échecs, causés tous deux par ce lot.
  - `contracts` était absent de la liste blanche stdlib de `test_scan_launch_plugin`.
  - `dev/mission_lot1.py` importait l'aide de test `_t`, refusée par `test_v3_invariants.I3Stdlib`.
  - Les deux sont corrigés.
- `py -3 dev/accept.py` : A1 = 489 tests, 0 échec, 1 sauté. Bilan : **vert 19, rouge 1, non mesuré 4**.
  - A20 est rouge : médiane 222 ms pour un plancher de l'interpréteur à 70 ms. Il était déjà rouge à la baseline et sera traité au lot 8.
  - Non mesurés : A8 (barre en pause), A10 (index du vault absent sur cette machine, condition de machine), A22 (le script ne lit pas la CI), A24 (banc complet du lot 10).

## Critères V3.1 touchés
- A03 Contrats : **PASS**. Schémas versionnés, validation, exemples, tests.
- A21 Reprise : partiel. La ligne tronquée est tolérée et les événements sont dédupliqués ; le `done` idempotent arrive au lot 3. **NOT MEASURED** pour l'instant.
- A23 Tests : **PASS**. Suite complète verte, 0 échec non expliqué.

## Non vérifié
- Linux : CI après le push.
- Migration sur une vraie mission historique : seule une copie de fixture a été migrée.
