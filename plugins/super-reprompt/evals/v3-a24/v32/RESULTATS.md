# Banc V3.2 « semver » — résultats (27/11/2026)

**Question.** Le déclencheur automatique de contre-épreuve (lot 11) améliore-t-il la qualité d'une tâche de code où Claude seul est le plus susceptible d'échouer, et à quel coût ?

**Réponse mesurée : non, sur cette tâche. Aucun gain de qualité, un surcoût net.** Résultat honnête, publié tel quel.

## Protocole (figé avant les essais)
- **Tâche** : `semver` (`projets/semver/`), la plus difficile du corpus : résolveur de plages semver avec caret, tilde, tiret, jokers, union, règle des prereleases bloc par bloc, `max_satisfying`. Énoncé de 40 lignes, 22 tests cachés dont chaque phrase de l'énoncé est la source.
- **Batterie vérifiée avant les essais** : une implémentation de référence (`ref/semver_ref.py`) passe 22/22 ; quatre implémentations fautives volontaires (sans règle des prereleases, ordre lexical des identifiants, caret 0.x traité comme 1.x, borne haute du tiret partielle en zéros) sont chacune rejetées par au moins un test ; deux mutants se sont révélés équivalents.
- **Bras** : `nu` (Claude Code sans plugin), `v31` (plugin du lot 10, commit `7506057`), `v32` (plugin avec le déclencheur du lot 11, activé pour l'essai).
- **Conditions communes** : `claude -p` isolé (`dev/a24_run.py`, configuration dédiée sans hook ni `CLAUDE.md` personnel), dossier vierge, même invite (« Réalise le projet décrit dans ENONCE.md. »), effort medium, outil Agent autorisé dans tous les bras. Sonnet 5.5 puis Haiku 5.5.
- **Mesures** : tests cachés ; **tokens = somme de `modelUsage`**, qui inclut les sous-agents (le champ `usage` seul les ignore : constaté sur une sonde, 51 006 tokens de sous-agent absents) ; coût = équivalent au tarif API (`total_cost_usd`), **estimé, pas un débit sur l'abonnement**.
- **Données brutes** : `journal-sonnet.jsonl`, `journal-haiku.jsonl` (texte libre du modèle retiré). Reproduction : `py -3 dev/a24_run.py … --arms nu,v31,v32 --projects semver --agent-tool --n 3`.

## Résultats — Sonnet 5.5, 3 essais par bras
| Bras | Tests cachés | Tokens médians (min–max) | Équivalent API médian | Durée médiane | Sous-agents |
|---|---|---|---|---|---|
| nu | 22/22, 22/22, 22/22 | 728 k (578–923 k) | 0,43 $ | 138 s | 0 |
| v31 | 22/22 ×3 | 665 k (569–842 k) | 0,44 $ | 146 s | 0 |
| v32 | 22/22 ×3 | **1 041 k (967–1 595 k)** | **0,61 $** | 186 s | 2, 1, 1 |

## Résultats — Haiku 5.5, 3 essais par bras
| Bras | Tests cachés | Tokens médians (min–max) | Équivalent API médian | Durée médiane |
|---|---|---|---|---|
| nu | 22/22 ×3 | 1 074 k (900–1 360 k) | **0,13 $** | 221 s |
| v32 | 22/22 ×3 | **1 817 k (1 620–2 262 k)** | **0,35 $** | 287 s |

## Lecture
1. **Plafond de qualité.** Claude seul réussit 22/22 aux 6 essais « nu », avec Sonnet comme avec Haiku. La contre-épreuve n'a rien à corriger, donc aucun bras ne peut la dépasser. Cette tâche, pourtant la plus difficile du corpus et dont la batterie rejette des implémentations fautives, ne distingue aucune méthode.
2. **La contre-épreuve coûte cher pour rien ici.** Médiane : +43 % de tokens et +42 % d'équivalent API avec Sonnet ; +69 % de tokens et **+169 %** d'équivalent API avec Haiku. Elle ajoute aussi environ 30 à 35 % de durée (186 s contre 138 s avec Sonnet, 287 s contre 221 s avec Haiku).
3. **Le seul gain mesuré est un gain de coût, pas de qualité** : Haiku seul atteint la même qualité que Sonnet seul à **0,13 $ contre 0,43 $ en équivalent API (3,3 fois moins)**, en consommant plus de tokens (1,07 M contre 0,73 M) mais au tarif d'un modèle plus petit, et en mettant plus de temps (221 s contre 138 s). C'est un résultat à n = 3 sur une seule tâche : une piste, pas une règle.
4. **V3.1 n'est ni meilleur ni pire que Claude seul** sur cette tâche (665 k contre 728 k de tokens médians, écart dans la dispersion).

## Limites
- n = 3 par cellule, **une seule tâche**, un seul juge (tests déterministes) ; la batterie est de ma main, dérivée de l'énoncé.
- Le coût est un équivalent API estimé. Le quota réel d'un abonnement Pro ne suit pas proportionnellement ce tarif.
- Les essais Sonnet et Haiku n'ont pas eu lieu à la même heure : la durée est sensible à la charge de la machine.
- La contre-épreuve peut valoir son prix sur des tâches où l'auteur se trompe réellement (spécification ambiguë, grand code existant, bug caché). Ce banc ne contient aucune tâche de ce type : **non mesuré, pas réfuté**.

## Décision prise
Le déclencheur du lot 11 est **optionnel** : désactivé par défaut, activé par `SUPER_REPROMPT_ENGAGE=1` ou par une demande explicite dans l'invite (« avec contre-épreuve »), refusé par « sans contre-épreuve ». Il n'est pas défendable de l'activer par défaut sur la base de cette mesure.

## Pistes suivantes, par intérêt mesuré
1. **Routage par coût** : écrire avec le plus petit modèle suffisant, vérifier par tests déterministes, n'escalader qu'à l'échec. Seul levier ayant montré un gain (3,3 fois moins en équivalent API à qualité égale). À valider sur d'autres tâches, dont une où Haiku échoue.
2. **Un banc où Claude seul échoue** : spécification ambiguë, base de code existante de plusieurs fichiers, débogage d'un défaut caché. Sans lui, aucune méthode ne peut montrer de gain de qualité.
