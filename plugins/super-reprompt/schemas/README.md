# Contrats V3.1 (lot 1)

Une seule implémentation : `scripts/contracts.py` (bibliothèque standard, aucun réseau).

| Contrat | Version | Fichier de mission | Règle |
|---|---|---|---|
| `state` | 1 | `STATE.json` | slug, statut, exigences, vérification |
| `plan` | 2 | `PLAN.json` | IDs uniques, dépendances connues, pas de cycle ; en strict : `source_order_hash`, critères et commande de preuve par tâche |
| `seal` | 1 | `SCELLE.json` | `body_sha`, périmètre, avenants chaînés, `plan_sha256` facultatif |
| `event` | 1 | `events.ndjson` | `event_id`, `mission_id`, horodatage UTC, `event_type` pointé, acteur parmi `core manager agent user provider system`, `correlation_id`, `payload` |
| `receipt` | 1 | `receipts/<tâche>/<run>.json` | annexe A.3 du cahier ; tout champ inconnu vaut `null` ou `"unavailable"`, jamais une valeur inventée |

États de tâche : `proposed → ready → running → review → done`, plus `blocked`, `failed`, `cancelled`, `skipped`.
`done` exige un reçu `ok` avec au moins une preuve ; `failed → ready` est une nouvelle tentative (`attempt` + 1).
Les statuts historiques `todo` et `echec` sont lus comme `ready` et `failed`, et refusés en mode strict.

Invariants de stockage : écriture atomique (temporaire unique, `fsync`, `os.replace`) ; lecture stricte (un fichier
illisible lève une erreur, il n'est jamais écrasé) ; ajout au journal sous verrou ; une ligne tronquée par un arrêt
brutal est ignorée à la lecture et refermée avant l'ajout suivant ; `dedup_key` rend un événement rejouable sans doublon.

Migration : `contracts.py migrate <dossier de mission>` convertit l'ancien `journal.ndjson` (schémas `vault.py` et
pare-feu) en événements `legacy`, de façon idempotente ; l'original n'est jamais modifié (retour arrière : supprimer
les événements `payload.legacy`).

Exemples : `examples/valid/*.json` et `examples/invalid/*.json`, vérifiés par `tests/test_contracts.py`.

```
py -3 scripts/contracts.py validate plan .super-reprompt/<slug>/PLAN.json --strict
py -3 scripts/contracts.py events .super-reprompt/<slug> --tail 20
```
