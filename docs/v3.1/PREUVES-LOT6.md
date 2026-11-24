# Lot 6 — Économie (preuves, 24/11/2026)

## Livré (budget dupliqué, garde-budget morte)

**Un seul journal de dépense : `econ.ndjson`.** Chaque ligne porte une étiquette `actual`, `estimated`, `projected` ou `unavailable`, plus une source, le modèle, le fournisseur, le coût et la devise.
- Une dépense `unavailable` garde des tokens à `null` : rien n'est inventé.
- `manager done` étiquette `actual` si `--tokens` est fourni, `unavailable` sinon. Avant, il écrivait une ligne à 0 marquée « estimée ».
- Les anciennes lignes (`estime`) sont relues avec leur étiquette.

**Un seul budget.**
- `PROGRESS.json` est désormais une **projection** recalculée à chaque dépense. Auparavant il était lu par la Vigie et jamais écrit. La garde `BUDGET_DEPASSE` de `guard drift` fonctionne donc pour la première fois.
- `mission.py spent` écrit dans `econ.ndjson` ; `STATE.spent_est_k` reste comme projection.
- Le budget mission du scellé (`SCELLE.budget.max_tokens`) est appliqué par `manager next` : alerte à 80 % et arrêt à 150 %, avec les événements `budget.alert` et `budget.stop`. Les budgets de phase continuent de venir du plan.

**Routage comparatif tracé.** `econ.decide` compare quatre voies : session, spécialiste, sous-manager, Relais. Pour chacune, il distingue les tokens du contexte principal, les tokens totaux et les tokens externes.
- Chaque option porte `label: estimated`, `confiance: faible (n = 0)` et sa source : le modèle de coût déclaré dans `econ.py`, constitué d'hypothèses et non de mesures.
- `manager next` journalise chaque décision avec ses alternatives (`routing.decision`).

**Rapport reproductible** : `econ.py rapport <dossier de mission> [--json]`. Il donne les totaux par étiquette, le statut mission, les phases et les postes. Les étiquettes ne sont jamais additionnées sans le dire.

## Mission réelle
`py -3 dev/mission_lot6.py` : **12/12 PASS**.
- `ready` avec un budget mission de 100 000 tokens.
- Cadrage : 30 k `estimated`.
- T1, sans compteur : `unavailable`.
- T2 (spécialiste Sonnet) : 52 000 `actual`.
- Alerte à 80 % : 82 000 / 100 000.
- Le rapport sépare `actual 52000 | estimated 30000`. Deux passages donnent un JSON identique.
- Trois décisions de routage, chacune avec ses quatre options. Exemple pour T2 : la session coûterait 90 000 au contexte principal, le spécialiste 2 100 (100 100 au total).
- Après T3 (70 000), arrêt à 152 000 / 100 000 (code 3, question posée), et la Vigie relève `BUDGET_DEPASSE 152000 > 100000`.

## Tests
- `test_economie` : 8 tests, rouge vu avant implémentation. Les trois échecs du premier passage au vert venaient des données de test (modèle explicite exigé pour un spécialiste, plan absent du disque) ; ce sont les tests qui ont été corrigés, pas le code.
- `py -3 dev/accept.py` : A1 = 526 tests, 0 échec, 1 sauté. Bilan : vert 19, rouge 1 (A20, médiane 199 ms), non mesuré 4.

## Critères V3.1
- A25 Économie : **PASS**. `actual` et `estimated` sont séparés, et chaque décision de routage est tracée et justifiable.

## Limites (non vérifié)
- Le modèle de coût du routage repose sur des hypothèses (amorçage d'un agent : 8 000 tokens ; coordination : 4 000), non mesurées. Il faudra les remplacer par des médianes observées une fois que les reçus porteront des tokens réels.
- `--tokens` est déclaré par l'agent et n'est pas relu dans le transcript.
- Aucun coût monétaire réel : aucun fournisseur payant, budget 0 €.
- La garde de la Vigie ne déclenche qu'au-delà de 100 % ; la réponse graduée est prévue au lot 8.
