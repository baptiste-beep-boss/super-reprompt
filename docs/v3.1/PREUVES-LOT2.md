# Lot 2 — Compilateur de plan (preuves, 24/11/2026)

## Livré (ruptures 1 et 2 de l'audit)
- `scripts/compile_plan.py` transforme `ORDRE.md` et `STATE.json` validés en `PLAN.json` schéma 2, validé en strict.
  - **Source des tâches** : `STATE.tasks`, le découpage rédigé au cadrage. À défaut, une tâche par exigence (`T-<R>`) plus `T-VERIF`, qui dépend de toutes les autres et couvre les critères.
  - **IDs stables** : recompiler redonne les mêmes identifiants.
  - **Statuts initiaux** : `ready` sans dépendance, `proposed` sinon.
  - **Preuves** : chaque `V<n>` est résolu vers sa commande.
  - **Lien à l'ordre** : `source_order_hash` est le SHA-256 de `ORDRE.md`.
  - **Couverture** : toute exigence et tout critère doivent être couverts par une tâche, sinon refus nommé et rien n'est écrit.
  - **Recompilation** : même structure, rien ne change et les statuts sont conservés. Structure différente alors qu'une tâche a démarré : refus, un avenant est requis.
- `contracts.plan_structure_sha` hache ce que le plan promet (tâches, dépendances, couverture, preuves), pas sa progression.
- `guard.py seal` inscrit `plan_sha256` dans le scellé. `guard.py drift` signale `PLAN_MODIFIE` (code non nul) quand le plan est restructuré, mais pas quand les statuts avancent.
- `mission.py ready`, à la fin du cadrage, enchaîne sans étape manuelle :
  1. compilation de `PLAN.json` ;
  2. passage de l'état à `ready` ;
  3. scellement, avec les options lues dans `STATE.seal` et le budget pris sur l'estimation haute.
- Événements journalisés : `plan.compiled` et `seal.written`.
- `manager._run` accepte une commande de preuve sous forme de chaîne (exécutée par le shell).
- `econ.frontier` lit les statuts compilés : `ready`, et `proposed` dont les dépendances sont faites.
- Skill : en P4, `STATE.tasks` ; en P7, `ready` compile et scelle. `SKILL.md` fait 3 945 tokens, sous le plafond de 4 950.

## Défaut trouvé par la mission réelle
Avant correction, `manager next` sur un plan compilé affichait `FIN : aucune tache prete (T1=ready, T2=proposed)`. La frontière ne connaissait que `todo` : la rupture plan → manager était encore là. Elle est corrigée par TDD (`FrontierReadsCompiledStatuses`, vu rouge puis vert).

## Mission réelle
`py -3 dev/mission_lot2.py` : **12/12 PASS**. Le projet jetable a un chemin avec espaces et accents. La mission enchaîne :
- `validate_order` ;
- `mission.py ready` : les empreintes d'ordre et de plan se retrouvent dans le scellé ;
- `guard drift` : aucun écart ;
- `manager next` : T1 prête ;
- `manager done T1` : la preuve compilée est exécutée et sort avec le code 0 ;
- `guard drift` : aucun écart ;
- ajout d'une tâche en douce : `PLAN_MODIFIE` ;
- recompilation sans avenant : refus ;
- présence de `plan.compiled` et `seal.written` dans le journal.

## Tests
- `test_compile_plan` : 11 tests, rouge vu avant implémentation, dont un test de `mission.py ready` de bout en bout.
- `py -3 dev/accept.py` : A1 = 500 tests, 0 échec, 1 sauté. Bilan : vert 19, rouge 1, non mesuré 4.
  - A20 est rouge : médiane 328 ms pour un plancher de l'interpréteur à 226 ms, machine chargée. Prévu au lot 8.

## Critères V3.1
- A05 Compilation d'ordre : **PASS**. L'ordre validé devient `PLAN.json` automatiquement, lié par empreinte au scellé.
- A06 Plan exécutable : **PASS** pour le chargement et la validation des tâches et dépendances (cycles, dépendances inconnues, couverture). La boucle complète vient au lot 3.
- A03 Contrats : PASS, maintenu.

## Non vérifié
- CI Linux (pas de push).
- La forme de `STATE.tasks` produite par un vrai cadrage LLM n'a pas encore été exercée en session réelle.
