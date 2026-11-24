# Lot 4 — Éclaireur universel (preuves, 24/11/2026)

## Livré (rupture 6 de l'audit)
- `eclaireur.capacites` interroge chaque type sélectionnable du catalogue : skill, agent, commande, hook, règle, script, schéma. Il passe par trois cercles :
  - cercle 0, l'index : le catalogue reste en mémoire et n'est jamais mis dans un prompt ;
  - cercle 1, la liste courte par type ;
  - cercle 2, le chargement des seules capacités retenues.
- Chaque capacité retenue ou écartée porte sa raison : seuil, quota par type, redondance de nom, intégrité ou budget.
- **Intégrité vérifiée** contre l'empreinte du catalogue, elle-même issue de `LOCK.json`. Trois cas :
  - fichier simple ;
  - skill de plusieurs fichiers : empreinte composite, identique à `catalog.sha_of` ;
  - entrée de `hooks.json` : conteneur vérifié, puis présence de l'entrée avec son empreinte dans `hooks.metadata.json`.
- **Budget de contexte explicite**, 6 000 tokens par tâche par défaut. Le coût est **mesuré** sur la taille du fichier ; à défaut, il est marqué « estimé ».
- Le classement par défaut (`scout`, skills seuls) est inchangé, donc A19 l'est aussi.
- `net/scout.py trouver` délègue déjà à `eclaireur.scout_plan`, auquel il ajoute un 3e cercle distant. Il n'y a qu'un seul classement : c'est la fusion demandée, constatée et documentée ici.
- **Raccordement** : `compile_plan` (P4) écrit un plan de capacités par tâche (`capabilities`) et un `context_budget` mesuré dans `PLAN.json`. Le résultat est déterministe : recompiler ne change pas l'empreinte.
- `econ.brief` donne au spécialiste les seules capacités retenues, par identifiant, à lire à la demande.
- Nouvelle commande `eclaireur.py capacites PLAN.json [--budget N]`.

## Défauts trouvés par la mission réelle (corrigés, avec tests de non-régression)
1. `manager next` écrit `execution_mode` sur la tâche, et ce champ entrait dans l'empreinte structurelle du plan. La Vigie levait donc `PLAN_MODIFIE` à tort après tout `next`. Le défaut datait du lot 3, que la mission du lot 3 n'appelait pas `drift` après `next`. Correctif : `execution_mode` rejoint les champs de progression.
2. L'Éclaireur écartait `ecc:skill:security-review` pour « empreinte différente ». Ce n'était pas une altération : pour un skill de plusieurs fichiers, l'empreinte est composite. Le contrôle a été corrigé.
3. Nouveau test : **tout le catalogue sélectionnable passe le contrôle d'intégrité**.

## Mission réelle
`py -3 dev/mission_lot4.py` : **7/7 PASS**. Cadrage de trois tâches de nature différente, puis `mission.py ready`.
- T1 (revue sécurité Python) : agent `python-reviewer`, règle `python/security`, commande `fastapi-review`, skill `security-bounty-hunter`.
- T2 (accessibilité) : skill `accessibility`, plus une commande, un agent et une règle.
- T3 (serveur MCP) : hook `pre:mcp-health-check` et skill `mcp-server-patterns`.
- Contexte chargé : **5 803 tokens au plus par tâche**, mesurés, pour un budget de 6 000. Le catalogue complet représente 1 318 454 tokens (estimation du catalogue), soit un ratio de 0,44 %.
- Le brief de T1 porte exactement ses capacités, et pas celles de T2.
- La Vigie ne relève aucune dérive après `next`.

## Tests
- `test_eclaireur_universel` : 11 tests, rouge vu avant implémentation. Le test du brief a été écrit après le code ; les deux tests de non-régression ont été rendus nécessaires par la mission.
- `py -3 dev/accept.py` : A1 = 518 tests, 0 échec, 1 sauté. A19 vert. Bilan : vert 19, rouge 1 (A20, médiane 218 ms), non mesuré 4.

## Critères V3.1
- A13 Éclaireur universel : **PASS**. Sélection de 5 types dans un vrai plan.
- A14 Progressive disclosure : **PASS**. Contexte limité, mesuré et explicite.
- A15 Provenance vendor : intégrité maintenant **vérifiée au chargement**, et plus seulement en test.

## Limites (non vérifié)
- Le seuil par type (0,5) et les poids ne sont pas calibrés (n = 0). Exemple : un hook peu pertinent (`plan-canvas-sessions`, adéquation 0,29) passe le seuil pour T1.
- Le vocabulaire fermé limite l'atteinte des hooks : « monitoring » ne trouve aucun hook, « mcp » si.
- Les instructions contradictoires entre capacités ne sont pas détectées.
- L'utilité réelle des capacités n'est pas encore mesurée : cercle 4, évaluation au lot 10.
